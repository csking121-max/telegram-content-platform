#!/usr/bin/env python3
"""
Simulate a webhook call from the Telegram gateway to the backend.

Signs the payload with HMAC and sends it to the local webhook endpoint.

Usage:
    python scripts/simulate_webhook.py --bot testbot --action access_check --token YOUR_TOKEN
    python scripts/simulate_webhook.py --bot testbot --action request_delivery --pack-id 1
"""
from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

try:
    import httpx
except ImportError:
    print("❌ httpx not installed. Run: pip install httpx")
    sys.exit(1)


def sign_payload(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def simulate(
    base_url: str,
    bot_username: str,
    hmac_secret: str,
    telegram_id: int,
    username: str,
    action: str,
    token: str | None,
    pack_id: int | None,
):
    payload = {
        "telegram_id": telegram_id,
        "username": username,
        "action": action,
    }
    if token:
        payload["token"] = token
    if pack_id is not None:
        payload["pack_id"] = pack_id

    body = json.dumps(payload).encode()
    signature = sign_payload(hmac_secret, body)

    url = f"{base_url}/webhook/{bot_username}"
    print(f"📤 POST {url}")
    print(f"   Payload: {json.dumps(payload, indent=2)}")
    print(f"   X-Signature: {signature[:16]}…")

    response = httpx.post(
        url,
        content=body,
        headers={
            "Content-Type": "application/json",
            "X-Signature": signature,
        },
    )

    print(f"\n📥 Response [{response.status_code}]:")
    try:
        print(json.dumps(response.json(), indent=2))
    except Exception:
        print(response.text)


def main():
    parser = argparse.ArgumentParser(description="Simulate webhook call")
    parser.add_argument("--url", default="http://localhost:8000", help="Backend base URL")
    parser.add_argument("--bot", required=True, help="Bot username")
    parser.add_argument("--secret", default="test_hmac_secret", help="HMAC secret for the bot")
    parser.add_argument("--tg-id", type=int, default=123456789, help="Telegram user ID")
    parser.add_argument("--username", default="testuser", help="Telegram username")
    parser.add_argument("--action", required=True, choices=["access_check", "request_delivery"], help="Action type")
    parser.add_argument("--token", default=None, help="Access token string")
    parser.add_argument("--pack-id", type=int, default=None, help="Content pack ID")
    args = parser.parse_args()

    simulate(
        base_url=args.url,
        bot_username=args.bot,
        hmac_secret=args.secret,
        telegram_id=args.tg_id,
        username=args.username,
        action=args.action,
        token=args.token,
        pack_id=args.pack_id,
    )


if __name__ == "__main__":
    main()