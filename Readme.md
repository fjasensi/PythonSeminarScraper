# Seminar scraper
This app gets seminar's prices and sends a telegram message if there are discounts.

# Setup
Open **main.py** file and configure with your own data these two values:
```
bot_token = 'YOUR_BOT_TOKEN'
chat_id = 'YOUR_CHAT_ID'
```

# Seminars to check
You have some examples of seminars that are being followed in **seminars.txt** file. You can add more.
# How to run in Docker
## Build docker image
```bash
docker build -t seminar_scraper .
```

## Run docker application
```bash
docker run -d --restart always seminar_scraper
```