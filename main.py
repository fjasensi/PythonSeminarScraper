import os
import logging
import re
import time

import requests

from seminar import Seminar
from env_loader import load_env_file

load_env_file()

DISCOUNT_PATTERN = re.compile(r"(\d+(?:[.,]\d+)?)\s*%\s*de\s*descuento", re.IGNORECASE)


def hasDiscount(content):
    posDisc = content.find("descuento")

    if posDisc != -1:
        return True

    return False


def extractDiscountPercentage(content):
    matches = DISCOUNT_PATTERN.findall(content)
    if not matches:
        return None

    values = [float(value.replace(",", ".")) for value in matches]
    return max(values)


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


def evaluateSeminar(content, seminar):
    if discount_alert_mode == 'keyword':
        seminar.discount = hasDiscount(content)

        if seminar.discount:
            return True, f"Seminar: {seminar.name} has discount"

        return False, f"Seminar: {seminar.name} has not discount"

    current_discount_percentage = extractDiscountPercentage(content)
    previous_discount_percentage = seminar.last_discount_percentage
    seminar.last_discount_percentage = current_discount_percentage

    if current_discount_percentage is None:
        return False, f"Seminar: {seminar.name} no percentage discount found"

    if previous_discount_percentage is None:
        should_notify = current_discount_percentage > min_discount_percentage
        message = (
            f"Seminar: {seminar.name} discount is {formatPercentage(current_discount_percentage)}% "
            f"(threshold {formatPercentage(min_discount_percentage)}%)"
        )
        return should_notify, message

    if (
        current_discount_percentage > min_discount_percentage
        and current_discount_percentage > previous_discount_percentage
    ):
        message = (
            f"Seminar: {seminar.name} discount increased from "
            f"{formatPercentage(previous_discount_percentage)}% to "
            f"{formatPercentage(current_discount_percentage)}% "
            f"(threshold {formatPercentage(min_discount_percentage)}%)"
        )
        return True, message

    return (
        False,
        f"Seminar: {seminar.name} discount is {formatPercentage(current_discount_percentage)}% "
        f"(previous {formatPercentage(previous_discount_percentage)}%, "
        f"threshold {formatPercentage(min_discount_percentage)}%)"
    )


# Send request to unir, get new price and send telegram message
def runProcess(seminarList):
    for seminar in seminarList:
        try:
            r = requests.get(seminar.url)

            if r.status_code == 200:
                send_message, message = evaluateSeminar(r.text, seminar)

                logging.info(message)

                if send_message:
                    sendNotification(message)
            else:
                status_error = f"Response status code: {r.status_code}"

                logging.error(status_error)
                sendTelegramMessage(status_error)
        except Exception:
            request_error = f"Error at get response from page: {seminar.url}. Seminar: {seminar.name}"

            logging.error(request_error)
            sendTelegramMessage(request_error)

        time.sleep(5)



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
    actualPrice = 550.0
    bot_token = os.getenv('TELEGRAM_BOT_TOKEN', 'YOUR_BOT_TOKEN')
    chat_id = os.getenv('TELEGRAM_CHAT_ID', 'YOUR_CHAT_ID')
    discord_webhook_url = os.getenv('DISCORD_WEBHOOK_URL', 'YOUR_DISCORD_WEBHOOK_URL')
    mode = os.getenv('MODE', 'telegram').lower()
    discount_alert_mode = os.getenv('DISCOUNT_ALERT_MODE', 'keyword').lower()
    min_discount_percentage = float(os.getenv('MIN_DISCOUNT_PERCENTAGE', '20'))

    if mode not in {'telegram', 'discord', 'multiple'}:
        raise ValueError("MODE must be one of: telegram, discord, multiple")

    if discount_alert_mode not in {'keyword', 'increase_over_threshold'}:
        raise ValueError("DISCOUNT_ALERT_MODE must be one of: keyword, increase_over_threshold")

    if mode in {'telegram', 'multiple'} and (bot_token == 'YOUR_BOT_TOKEN' or chat_id == 'YOUR_CHAT_ID'):
        raise ValueError("TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID must be configured")

    if mode in {'discord', 'multiple'} and discord_webhook_url == 'YOUR_DISCORD_WEBHOOK_URL':
        raise ValueError("DISCORD_WEBHOOK_URL must be configured when MODE is discord or multiple")

    logging.basicConfig(format='%(message)s', level=logging.INFO, datefmt='%m/%d/%Y %I:%M:%S %p')

    filename = 'seminars.txt'

    seminarList = read_seminars_from_file(filename)

    # Run process
    while 1 == 1:
        runProcess(seminarList)

        # Wait 1 hour before the next execution
        time.sleep(3600)
