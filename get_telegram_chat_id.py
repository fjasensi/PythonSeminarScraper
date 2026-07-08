import argparse
import os
import sys

import requests

from env_loader import load_env_file

load_env_file()


def extract_chat(update):
    candidates = (
        "message",
        "edited_message",
        "channel_post",
        "edited_channel_post",
        "my_chat_member",
        "chat_member",
    )

    for key in candidates:
        payload = update.get(key)
        if isinstance(payload, dict) and isinstance(payload.get("chat"), dict):
            chat = payload["chat"]
            return {
                "id": chat.get("id"),
                "type": chat.get("type", "unknown"),
                "name": chat.get("title")
                or chat.get("username")
                or chat.get("first_name")
                or "unknown",
            }

    return None


def main():
    parser = argparse.ArgumentParser(
        description="Get Telegram chat IDs from getUpdates."
    )
    parser.add_argument(
        "--token",
        help="Telegram bot token. If omitted, TELEGRAM_BOT_TOKEN env var will be used.",
    )
    args = parser.parse_args()

    token = args.token or os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        print("Missing token. Use --token or set TELEGRAM_BOT_TOKEN.", file=sys.stderr)
        sys.exit(1)

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        response = requests.get(url, timeout=20)
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        print(f"Error calling Telegram API: {exc}", file=sys.stderr)
        sys.exit(1)

    if not data.get("ok"):
        print(f"Telegram API returned error: {data}", file=sys.stderr)
        sys.exit(1)

    chats = {}
    for update in data.get("result", []):
        chat = extract_chat(update)
        if chat and chat["id"] is not None:
            chats[chat["id"]] = chat

    if not chats:
        print("No chats found yet.")
        print("1) Open Telegram and send a message to your bot in the target chat.")
        print("2) Run this script again.")
        return

    print("Detected chats:")
    for chat in chats.values():
        print(f"- chat_id={chat['id']} | type={chat['type']} | name={chat['name']}")


if __name__ == "__main__":
    main()
