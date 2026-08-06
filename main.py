import os
import html
import logging
import re
import time
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import unquote, urljoin, urlparse, urlunparse
from zoneinfo import ZoneInfo

import requests
from curl_cffi import requests as browser_requests

from seminar import Seminar
from env_loader import load_env_file

load_env_file()

DISCOUNT_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*%\s*de\s*descuento", re.IGNORECASE)
PRICE_PATTERN = re.compile(
    r"\bPrecio\s*:?\s*(\d+(?:[.,]\d{1,2})?)\s*€",
    re.IGNORECASE,
)
PAGE_REQUEST_TIMEOUT_SECONDS = 30
DEFAULT_CATALOG_URL = "https://escueladehumanidades.unir.net/oferta-academica/"


class CatalogLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            href = dict(attrs).get("href")
            if href:
                self.links.append(href)


class FirstHeadingParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.in_heading = False
        self.heading_parts = []

    def handle_starttag(self, tag, attrs):
        if tag == "h1" and not self.heading_parts:
            self.in_heading = True

    def handle_endtag(self, tag):
        if tag == "h1" and self.in_heading:
            self.in_heading = False

    def handle_data(self, data):
        if self.in_heading:
            self.heading_parts.append(data)

    @property
    def heading(self):
        value = " ".join(self.heading_parts)
        return re.sub(r"\s+", " ", value).strip() or None


class TimezoneFormatter(logging.Formatter):
    def __init__(self, *args, timezone_name, **kwargs):
        super().__init__(*args, **kwargs)
        self.timezone = ZoneInfo(timezone_name)

    def formatTime(self, record, datefmt=None):
        timestamp = datetime.fromtimestamp(record.created, self.timezone)
        return timestamp.strftime(datefmt) if datefmt else timestamp.isoformat()


def configureLogging(timezone_name):
    handler = logging.StreamHandler()
    handler.setFormatter(
        TimezoneFormatter(
            "%(asctime)s %(levelname)s %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S %Z",
            timezone_name=timezone_name,
        )
    )

    root_logger = logging.getLogger()
    root_logger.handlers.clear()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(handler)


def hasDiscount(content):
    return "descuento" in htmlToText(content).lower()


def htmlToText(content):
    plain_text = re.sub(r"<[^>]+>", " ", html.unescape(content))
    return re.sub(r"\s+", " ", plain_text).strip()


def extractDiscountPercentage(content):
    matches = DISCOUNT_PATTERN.findall(htmlToText(content))
    if not matches:
        return None

    values = [float(value.replace(",", ".")) for value in matches]
    return max(values)


def extractPrice(content):
    matches = PRICE_PATTERN.findall(htmlToText(content))
    if not matches:
        return None

    # The price can appear more than once in responsive page sections. If a sale
    # renders both the original and reduced values, the lower one is the useful
    # amount for the alert.
    values = [float(value.replace(",", ".")) for value in matches]
    return min(values)


def extractSeminarName(content):
    parser = FirstHeadingParser()
    parser.feed(content)
    return parser.heading


def normalizeSeminarUrl(url, base_url=DEFAULT_CATALOG_URL):
    parsed = urlparse(urljoin(base_url, url))
    path = parsed.path.rstrip("/") + "/"
    return urlunparse((parsed.scheme, parsed.netloc, path, "", "", ""))


def seminarNameFromUrl(url):
    slug = unquote(urlparse(url).path.rstrip("/").split("/")[-1])
    return slug.replace("-", " ").strip().title()


def extractCatalogSeminarUrls(content, catalog_url=DEFAULT_CATALOG_URL):
    parser = CatalogLinkParser()
    parser.feed(content)

    catalog = urlparse(catalog_url)
    catalog_path = catalog.path.rstrip("/") + "/"
    seminar_urls = []

    for href in parser.links:
        url = normalizeSeminarUrl(href, catalog_url)
        parsed = urlparse(url)
        if parsed.netloc != catalog.netloc:
            continue
        if not parsed.path.startswith(catalog_path) or parsed.path == catalog_path:
            continue
        if url not in seminar_urls:
            seminar_urls.append(url)

    return seminar_urls


def discoverSeminars(browser_session, catalog_url=DEFAULT_CATALOG_URL):
    response = browser_session.get(
        catalog_url,
        timeout=PAGE_REQUEST_TIMEOUT_SECONDS,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Catalog response status code: {response.status_code}")

    return [
        Seminar(seminarNameFromUrl(url), url)
        for url in extractCatalogSeminarUrls(response.text, catalog_url)
    ]


def mergeSeminars(tracked_seminars, catalog_seminars, seminar_state):
    active_seminars = []
    active_urls = set()

    for candidate in [*tracked_seminars, *catalog_seminars]:
        url = normalizeSeminarUrl(candidate.url)
        if url in active_urls:
            continue

        if url not in seminar_state:
            candidate.url = url
            seminar_state[url] = candidate

        active_seminars.append(seminar_state[url])
        active_urls.add(url)

    return active_seminars


def formatPercentage(value):
    return f"{value:g}"


def sendTelegramMessage(message):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    requests.get(url, params={"chat_id": chat_id, "text": message}, timeout=15).json()


def sendNotification(message):
    if mode == 'discord':
        requests.post(discord_webhook_url, json={'content': message})
    elif mode == 'telegram':
        sendTelegramMessage(message)
    elif mode == 'multiple':
        requests.post(discord_webhook_url, json={'content': message})
        sendTelegramMessage(message)


def evaluateDiscount(content, seminar):
    if discount_alert_mode == 'keyword':
        seminar.discount = hasDiscount(content)

        if seminar.discount:
            return True, f"Seminar: {seminar.name} has discount {seminar.url}"

        return False, f"Seminar: {seminar.name} has not discount"

    current_discount_percentage = extractDiscountPercentage(content)
    previous_discount_percentage = seminar.last_discount_percentage
    seminar.last_discount_percentage = current_discount_percentage

    if current_discount_percentage is None:
        return False, f"Seminar: {seminar.name} no percentage discount found"

    if previous_discount_percentage is None:
        should_notify = current_discount_percentage >= min_discount_percentage
        message = (
            f"Seminar: {seminar.name} discount is {formatPercentage(current_discount_percentage)}% "
            f"(threshold {formatPercentage(min_discount_percentage)}%) {seminar.url}"
        )
        return should_notify, message

    if (
        current_discount_percentage >= min_discount_percentage
        and current_discount_percentage > previous_discount_percentage
    ):
        message = (
            f"Seminar: {seminar.name} discount increased from "
            f"{formatPercentage(previous_discount_percentage)}% to "
            f"{formatPercentage(current_discount_percentage)}% "
            f"(threshold {formatPercentage(min_discount_percentage)}%) {seminar.url}"
        )
        return True, message

    return (
        False,
        f"Seminar: {seminar.name} discount is {formatPercentage(current_discount_percentage)}% "
        f"(previous {formatPercentage(previous_discount_percentage)}%, "
        f"threshold {formatPercentage(min_discount_percentage)}%)"
    )


def evaluatePrice(content, seminar):
    current_price = extractPrice(content)
    previous_price = seminar.actual_price
    seminar.actual_price = current_price

    if current_price is None:
        return False, f"Seminar: {seminar.name} no price found"

    price_is_below_threshold = current_price < price_alert_threshold
    price_just_dropped = previous_price is None or current_price < previous_price

    if price_is_below_threshold and price_just_dropped:
        if previous_price is None:
            return (
                True,
                f"Seminar: {seminar.name} price is {current_price:g}€ "
                f"(below {price_alert_threshold:g}€) {seminar.url}",
            )

        return (
            True,
            f"Seminar: {seminar.name} price dropped from {previous_price:g}€ "
            f"to {current_price:g}€ (below {price_alert_threshold:g}€) {seminar.url}",
        )

    return (
        False,
        f"Seminar: {seminar.name} price is {current_price:g}€ "
        f"(threshold {price_alert_threshold:g}€)",
    )


def evaluateSeminar(content, seminar):
    discount_notification, discount_message = evaluateDiscount(content, seminar)
    price_notification, price_message = evaluatePrice(content, seminar)

    notification_messages = []
    if discount_notification:
        notification_messages.append(discount_message)
    if price_notification:
        notification_messages.append(price_message)

    if notification_messages:
        return True, "\n".join(notification_messages)

    return False, f"{discount_message}. {price_message}"


# Send request to unir, get new price and send telegram message
def runProcess(seminarList, browser_session):
    for seminar in seminarList:
        try:
            # UNIR's Akamai protection rejects the default TLS fingerprint used by
            # Python requests. curl_cffi sends the request with a browser-compatible
            # TLS/HTTP fingerprint while keeping the response API requests-like.
            r = browser_session.get(
                seminar.url,
                timeout=PAGE_REQUEST_TIMEOUT_SECONDS,
            )

            if r.status_code == 200:
                detected_name = extractSeminarName(r.text)
                if detected_name:
                    seminar.name = detected_name

                send_message, message = evaluateSeminar(r.text, seminar)

                logging.info(message)

                if send_message:
                    sendNotification(message)
            else:
                status_error = (
                    f"Seminar: {seminar.name} response status code: {r.status_code} "
                    f"{seminar.url}"
                )

                logging.error(status_error)
                sendTelegramMessage(status_error)
        except Exception:
            request_error = f"Error at get response from page: {seminar.url}. Seminar: {seminar.name}"

            logging.error(request_error)
            sendTelegramMessage(request_error)

        time.sleep(request_delay_seconds)



def read_seminars_from_file(filename):
    seminars = []

    with open(filename, 'r') as file:
        for line in file:
            data = line.strip().split(',')

            name = data[0]
            link = data[1]

            seminar = Seminar(name, link)

            seminars.append(seminar)
    return seminars


if __name__ == '__main__':
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID')
    discord_webhook_url = os.getenv('DISCORD_WEBHOOK_URL', 'YOUR_DISCORD_WEBHOOK_URL')
    mode = os.getenv('MODE', 'telegram').lower()
    discount_alert_mode = os.getenv('DISCOUNT_ALERT_MODE', 'keyword').lower()
    min_discount_percentage = float(os.getenv('MIN_DISCOUNT_PERCENTAGE', '20'))
    price_alert_threshold = float(os.getenv('PRICE_ALERT_THRESHOLD', '550'))
    catalog_url = os.getenv('CATALOG_URL', DEFAULT_CATALOG_URL)
    check_interval_seconds = int(os.getenv('CHECK_INTERVAL_SECONDS', '3600'))
    request_delay_seconds = float(os.getenv('REQUEST_DELAY_SECONDS', '5'))
    log_timezone = os.getenv('LOG_TIMEZONE', 'Europe/Madrid')

    if mode not in {'telegram', 'discord', 'multiple'}:
        raise ValueError("MODE must be one of: telegram, discord, multiple")

    if discount_alert_mode not in {'keyword', 'increase_over_threshold'}:
        raise ValueError("DISCOUNT_ALERT_MODE must be one of: keyword, increase_over_threshold")

    if mode in {'telegram', 'multiple'} and (bot_token == 'YOUR_BOT_TOKEN' or chat_id == 'YOUR_CHAT_ID'):
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured")

    if mode in {'discord', 'multiple'} and discord_webhook_url == 'YOUR_DISCORD_WEBHOOK_URL':
        raise ValueError("DISCORD_WEBHOOK_URL must be configured when MODE is discord or multiple")

    configureLogging(log_timezone)

    filename = 'seminars.txt'

    tracked_seminars = read_seminars_from_file(filename)
    seminar_state = {
        normalizeSeminarUrl(seminar.url): seminar
        for seminar in tracked_seminars
    }

    # Reuse one browser-compatible session so Akamai cookies and connections are
    # preserved across seminar checks.
    with browser_requests.Session(impersonate="chrome") as browser_session:
        while True:
            cycle_started_at = time.monotonic()

            try:
                catalog_seminars = discoverSeminars(browser_session, catalog_url)
                seminar_list = mergeSeminars(
                    tracked_seminars,
                    catalog_seminars,
                    seminar_state,
                )
                logging.info(
                    "Catalog contains %d seminars; checking %d unique seminars",
                    len(catalog_seminars),
                    len(seminar_list),
                )
            except Exception:
                logging.exception("Could not refresh the seminar catalog")
                seminar_list = mergeSeminars(tracked_seminars, [], seminar_state)
                sendTelegramMessage(
                    "Could not refresh the UNIR seminar catalog; checking tracked seminars only"
                )

            runProcess(seminar_list, browser_session)

            elapsed_seconds = time.monotonic() - cycle_started_at
            wait_seconds = max(0, check_interval_seconds - elapsed_seconds)
            logging.info(
                "Check complete in %.1f seconds; next check in %.1f seconds",
                elapsed_seconds,
                wait_seconds,
            )
            time.sleep(wait_seconds)
