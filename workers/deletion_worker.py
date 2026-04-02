"""
Deletion worker — deletes delivered messages after a configured delay.

Reads from ``queue:deletion`` in Redis.
Each job contains: telegram_id, bot_token, message_ids, delay_seconds.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import httpx

from backend.config import settings
from backend.database import AsyncSessionLocal
from backend.models.delivered_message import DeliveredMessage
from backend.redis_client import RedisClient
from sqlalchemy import select

logger = logging.getLogger(__name__)

QUEUE = "queue:deletion"
POLL_INTERVAL = settings.WORKER_POLL_INTERVAL
TELEGRAM_API = "https://api.telegram.org/bot{token}"


class DeletionWorker:
    async def run(self) -> None:
        rc = RedisClient.get()
        logger.info("DeletionWorker listening on %s", QUEUE)

        while True:
            raw = rc.client.lpop(QUEUE)
            if not raw:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            try:
                job: dict[str, Any] = json.loads(raw)
                await self._process(job)
            except Exception as exc:
                logger.exception("DeletionWorker error — sending job to DLQ")
                try:
                    rc.send_to_dlq(QUEUE, raw, error=str(exc))
                except Exception:
                    logger.warning("Failed to send job to DLQ")

    async def _process(self, job: dict[str, Any]) -> None:
        delay = job.get("delay_seconds", 0)
        if delay > 0:
            logger.info("Waiting %ds before deletion …", delay)
            await asyncio.sleep(delay)

        telegram_id = job["telegram_id"]
        bot_token = job.get("bot_token", "")
        message_ids: list[int] = job.get("message_ids", [])

        if not bot_token:
            bot_username = job.get("bot_username", "")
            for b in settings.telegram_bots:
                if b["username"] == bot_username:
                    bot_token = b["token"]
                    break

        if not bot_token or not message_ids:
            logger.warning("Skipping deletion job – missing token or message_ids")
            return

        base_url = TELEGRAM_API.format(token=bot_token)

        async with httpx.AsyncClient(timeout=15) as client:
            for mid in message_ids:
                try:
                    await client.post(
                        f"{base_url}/deleteMessage",
                        json={"chat_id": telegram_id, "message_id": mid},
                    )
                except Exception:
                    logger.warning("Failed to delete message %d for %d", mid, telegram_id)

        # Mark in DB as deleted
        async with AsyncSessionLocal() as db:
            for mid in message_ids:
                result = await db.execute(
                    select(DeliveredMessage).where(
                        DeliveredMessage.telegram_message_id == mid,
                    )
                )
                msg = result.scalar_one_or_none()
                if msg:
                    msg.deleted = True
            await db.commit()

        logger.info(
            "Deleted %d messages for telegram_id=%d", len(message_ids), telegram_id,
        )