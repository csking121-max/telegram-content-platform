"""
Delivery worker — sends content-pack items to users via Telegram.

Reads from ``queue:delivery`` in Redis.
Each job contains: telegram_id, bot_token, pack_items (list of file_id / text).
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from backend.config import settings
from backend.redis_client import RedisClient

logger = logging.getLogger(__name__)

QUEUE = "queue:delivery"
POLL_INTERVAL = settings.WORKER_POLL_INTERVAL
TELEGRAM_API = "https://api.telegram.org/bot{token}"


class DeliveryWorker:
    async def run(self) -> None:
        rc = RedisClient.get()
        logger.info("DeliveryWorker listening on %s", QUEUE)

        while True:
            raw = rc.client.lpop(QUEUE)
            if not raw:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            try:
                job: dict[str, Any] = json.loads(raw)
                await self._deliver(job)
            except Exception as exc:
                logger.exception("DeliveryWorker error — sending job to DLQ")
                try:
                    rc.send_to_dlq(QUEUE, raw, error=str(exc))
                except Exception:
                    logger.warning("Failed to send job to DLQ")

    async def _deliver(self, job: dict[str, Any]) -> None:
        telegram_id = job["telegram_id"]
        bot_token = job.get("bot_token", "")
        items: list[dict] = job.get("items", [])

        if not bot_token:
            # Look up bot token from config
            bot_username = job.get("bot_username", "")
            for b in settings.telegram_bots:
                if b["username"] == bot_username:
                    bot_token = b["token"]
                    break

        if not bot_token:
            logger.error("No bot token for delivery job: %s", job)
            return

        base_url = TELEGRAM_API.format(token=bot_token)

        async with httpx.AsyncClient(timeout=30) as client:
            for item in items:
                msg_type = item.get("message_type", "text")
                file_id = item.get("file_id", "")
                text = item.get("text", "")
                caption = item.get("caption", "")

                try:
                    if msg_type == "photo":
                        await client.post(
                            f"{base_url}/sendPhoto",
                            json={"chat_id": telegram_id, "photo": file_id, "caption": caption},
                        )
                    elif msg_type == "video":
                        await client.post(
                            f"{base_url}/sendVideo",
                            json={"chat_id": telegram_id, "video": file_id, "caption": caption},
                        )
                    elif msg_type == "document":
                        await client.post(
                            f"{base_url}/sendDocument",
                            json={"chat_id": telegram_id, "document": file_id, "caption": caption},
                        )
                    elif msg_type == "audio":
                        await client.post(
                            f"{base_url}/sendAudio",
                            json={"chat_id": telegram_id, "audio": file_id, "caption": caption},
                        )
                    else:
                        # Plain text
                        await client.post(
                            f"{base_url}/sendMessage",
                            json={"chat_id": telegram_id, "text": text or caption or "(empty)"},
                        )

                    # Small delay to respect Telegram rate limits
                    await asyncio.sleep(0.05)
                except Exception:
                    logger.exception(
                        "Failed to send item to %d (type=%s)", telegram_id, msg_type,
                    )

        logger.info(
            "Delivered %d items to telegram_id=%d", len(items), telegram_id,
        )