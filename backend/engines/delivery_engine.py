"""
Delivery Engine — enqueues delivery jobs for content packs.

This engine does NOT call Telegram directly. It prepares delivery jobs
that workers pick up from the Redis queue.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.content_pack import ContentPack
from backend.models.delivered_message import DeliveredMessage
from backend.models.pack_item import PackItem
from backend.redis_client import RedisClient

logger = logging.getLogger(__name__)

DELIVERY_QUEUE = "queue:delivery"
DELETION_QUEUE = "queue:deletion"


class DeliveryEngine:
    """Stateless — instantiate with db + redis per request."""

    def __init__(self, db: AsyncSession, redis: Optional[RedisClient] = None) -> None:
        self.db = db
        self.redis = redis or RedisClient.get()

    async def enqueue_delivery(
        self,
        user_id: int,
        telegram_id: int,
        pack_id: int,
        bot_username: str,
    ) -> dict:
        """
        Fetch pack items in batches and enqueue delivery jobs.
        Items are streamed from DB in pages to avoid loading all into memory.
        Returns summary dict.
        """
        pack = await self._get_pack(pack_id)
        deletion_seconds = pack.deletion_seconds if pack else None
        batch_size = settings.DELIVERY_BATCH_SIZE

        total_items = 0
        batch_idx = 0
        offset = 0

        # First pass: count total items for metadata
        count_result = await self.db.execute(
            select(func.count(PackItem.id)).where(PackItem.pack_id == pack_id)
        )
        total_count = count_result.scalar_one()
        if total_count == 0:
            return {"error": "No items in content pack", "pack_id": pack_id}

        total_batches = (total_count + batch_size - 1) // batch_size

        while True:
            result = await self.db.execute(
                select(PackItem)
                .where(PackItem.pack_id == pack_id)
                .order_by(PackItem.order_index)
                .limit(batch_size)
                .offset(offset)
            )
            batch = list(result.scalars().all())
            if not batch:
                break

            job = {
                "user_id": user_id,
                "telegram_id": telegram_id,
                "bot_username": bot_username,
                "pack_id": pack_id,
                "batch_index": batch_idx,
                "total_batches": total_batches,
                "items": [
                    {
                        "pack_item_id": item.id,
                        "storage_chat_id": item.storage_chat_id,
                        "storage_message_id": item.storage_message_id,
                        "media_type": item.media_type,
                        "order_index": item.order_index,
                    }
                    for item in batch
                ],
                "deletion_seconds": deletion_seconds,
                "delay_ms": settings.DELIVERY_BATCH_DELAY_MS,
            }
            self.redis.enqueue(DELIVERY_QUEUE, job)

            total_items += len(batch)
            batch_idx += 1
            offset += batch_size

            if len(batch) < batch_size:
                break

        logger.info(
            "Enqueued %d batches (%d items) for user=%s pack=%s",
            batch_idx,
            total_items,
            user_id,
            pack_id,
        )
        return {
            "batches": batch_idx,
            "total_items": total_items,
            "pack_id": pack_id,
        }

    async def record_delivered(
        self,
        user_id: int,
        bot_id: int,
        telegram_message_id: int,
        chat_id: int,
        deletion_seconds: Optional[int],
    ) -> None:
        """Record a delivered message and optionally schedule deletion."""
        if deletion_seconds and deletion_seconds > 0:
            delete_at = datetime.now(timezone.utc) + timedelta(seconds=deletion_seconds)
        else:
            delete_at = datetime.max.replace(tzinfo=timezone.utc)

        msg = DeliveredMessage(
            user_id=user_id,
            bot_id=bot_id,
            telegram_message_id=telegram_message_id,
            chat_id=chat_id,
            delete_at=delete_at,
        )
        self.db.add(msg)
        await self.db.flush()

        # Schedule deletion job
        if deletion_seconds and deletion_seconds > 0:
            deletion_job = {
                "delivered_message_id": msg.id,
                "telegram_message_id": telegram_message_id,
                "chat_id": chat_id,
                "bot_id": bot_id,
                "delete_at": delete_at.isoformat(),
            }
            self.redis.enqueue(DELETION_QUEUE, deletion_job)

    async def get_messages_to_delete(self) -> List[DeliveredMessage]:
        """Fetch messages whose delete_at has passed and haven't been deleted."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(DeliveredMessage).where(
                DeliveredMessage.delete_at <= now,
                DeliveredMessage.deleted == False,  # noqa: E712
            )
        )
        return list(result.scalars().all())

    # ── Internals ────────────────────────────────────

    async def _get_ordered_items(self, pack_id: int) -> List[PackItem]:
        result = await self.db.execute(
            select(PackItem)
            .where(PackItem.pack_id == pack_id)
            .order_by(PackItem.order_index)
        )
        return list(result.scalars().all())

    async def _get_pack(self, pack_id: int) -> Optional[ContentPack]:
        result = await self.db.execute(
            select(ContentPack).where(ContentPack.id == pack_id)
        )
        return result.scalar_one_or_none()