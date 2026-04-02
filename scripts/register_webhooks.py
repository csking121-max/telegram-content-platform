#!/usr/bin/env python3
"""
Register Telegram webhook URLs for all configured bots.

Reads TELEGRAM_BOTS from .env and sets the webhook URL for each bot
via the Telegram Bot API.

Usage:
    python scripts/register_webhooks.py --domain https://yourdomain.com
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import httpx
except ImportError:
    print("❌ httpx not installed. Run: pip install httpx")
    sys.exit(1)

from backend.config import settings  # noqa: E402


def register_webhook(bot_token: str, bot_username: str, domain: str) -> dict:
    """Call Telegram setWebhook API."""
    webhook_url = f"{domain}/webhook/{bot_username}"
    api_url = f"https://api.telegram.org/bot{bot_token}/setWebhook"

    response = httpx.post(api_url, json={
        "url": webhook_url,
        "allowed_updates": ["message", "callback_query"],
        "drop_pending_updates": True,
    })
    return response.json()


def main():
    parser = argparse.ArgumentParser(description="Register Telegram webhooks")
    parser.add_argument("--domain", required=True, help="Public domain (e.g., https://api.example.com)")
    parser.add_argument("--drop-pending", action="store_true", help="Drop pending updates")
    args = parser.parse_args()

    bots = settings.telegram_bots
    if not bots:
        print("❌ No bots configured. Set TELEGRAM_BOTS in .env")
        print("   Format: username:token:hmac_secret,username2:token2:secret2")
        sys.exit(1)

    print(f"🤖 Registering webhooks for {len(bots)} bot(s)...\n")

    for bot in bots:
        username = bot["username"]
        token = bot["token"]
        print(f"  @{username}:")

        result = register_webhook(token, username, args.domain)

        if result.get("ok"):
            print(f"    ✅ Webhook set → {args.domain}/webhook/{username}")
        else:
            print(f"    ❌ Failed: {result.get('description', 'Unknown error')}")

    print("\n✅ Done!")
    print("\nTo verify webhooks, run:")
    for bot in bots:
        print(f"  curl https://api.telegram.org/bot{bot['token']}/getWebhookInfo")


if __name__ == "__main__":
    main()