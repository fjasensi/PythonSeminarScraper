# Seminar scraper
This app gets seminar prices and sends alerts when a seminar has a discount.

# Configure with .env
1. Create your local config:
```bash
cp .env.example .env
```
2. Edit `.env` and set:
```dotenv
TELEGRAM_BOT_TOKEN=<YOUR_BOT_TOKEN>
TELEGRAM_CHAT_ID=<YOUR_CHAT_ID>
MODE=telegram
DISCOUNT_ALERT_MODE=keyword
MIN_DISCOUNT_PERCENTAGE=20
```

`DISCOUNT_ALERT_MODE` options:
- `keyword` (default): current behavior, sends alert if "descuento" exists in page content.
- `increase_over_threshold`: sends alert only when the detected `% de descuento` is at least `MIN_DISCOUNT_PERCENTAGE` and later increases.

# Telegram setup
If you forgot your credentials:

1. Recover or regenerate your bot token with `@BotFather`:
   - `/mybots` -> select your bot -> `API Token`
2. Send a message to your bot in the target chat.
3. Get chat IDs detected by the bot:
```bash
.venv/bin/python get_telegram_chat_id.py
```

The script reads `TELEGRAM_BOT_TOKEN` from `.env` (or env vars) and prints available `chat_id` values.

# Run locally
```bash
pip install -r requirements.txt
.venv/bin/python main.py
```

Example for your use case (alert if discount reaches 20% and later increases):
```dotenv
DISCOUNT_ALERT_MODE=increase_over_threshold
MIN_DISCOUNT_PERCENTAGE=20
```

# Seminars to check
Edit `seminars.txt` to add or remove seminars.

# Docker
## Build image
```bash
docker build -t seminar_scraper .
```

## Run container with .env
```bash
docker run -d --restart always --env-file .env seminar_scraper
```
