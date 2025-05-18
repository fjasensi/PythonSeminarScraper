import requests
import time
import logging

from seminar import Seminar


def hasDiscount(content):
    posDisc = content.find("descuento")

    if posDisc != -1:
        return True

    return False


def sendTelegramMessage(message):
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage?chat_id={chat_id}&text={message}"
    requests.get(url).json()


# Send request to unir, get new price and send telegram message
def runProcess(seminarList):
    # Send request and get new price
    for seminar in seminarList:
        try:
            r = requests.get(seminar.url)

            if r.status_code == 200:
                seminar.discount = hasDiscount(r.text)
            else:
                status_error = f"Response status code: {r.status_code}"

                logging.error(status_error)
                sendTelegramMessage(status_error)
        except:
            request_error = f"Error at get response from page: {seminar.url}. Seminar: {seminar.name}"

            logging.error(request_error)
            sendTelegramMessage(request_error)

        time.sleep(5)

    # Process results and send message
    for seminar in seminarList:
        sendMessage = False

        if seminar.discount:
            message = f'Seminar: {seminar.name} has discount'
            sendMessage = True
        else:
            message = f'Seminar: {seminar.name} has not discount'

        logging.info(message)

        if sendMessage==True:
            if mode == 'discord':
                requests.post(discord_webhook_url, json={'content': message})
            elif mode == 'telegram':
                sendTelegramMessage(message)
            elif mode == 'multiple':
                requests.post(discord_webhook_url, json={'content': message})
                sendTelegramMessage(message)



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
    bot_token = 'YOUR_BOT_TOKEN'
    chat_id = 'YOUR_CHAT_ID'
    discord_webhook_url= 'YOUR_DISCORD_WEBHOOK_URL'
    # mode = 'telegram'  # 'telegram' or 'discord' # mode = 'multiple'
    mode='discord'

    logging.basicConfig(format='%(message)s', level=logging.INFO, datefmt='%m/%d/%Y %I:%M:%S %p')

    filename = 'seminars.txt'

    seminarList = read_seminars_from_file(filename)

    # Run process
    while 1 == 1:
        runProcess(seminarList)

        # Wait 1 hour before the next execution
        time.sleep(3600)
