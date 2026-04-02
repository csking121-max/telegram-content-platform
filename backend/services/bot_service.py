"""
Bot Service — CRUD + lookup for registered Telegram bots.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.bot import Bot
from backend.schemas.bot import BotCreate, BotUpdate

logger = logging.getLogger(__name__)


class BotService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register(self, data: BotCreate) -> Bot:
        bot = Bot(**data.model_dump())
        self.db.add(bot)
        await self.db.flush()
        logger.info("Registered bot @%s", data.bot_username)
        return bot

    async def get_by_id(self, bot_id: int) -> Optional[Bot]:
        result = await self.db.execute(select(Bot).where(Bot.id == bot_id))
        return result.scalar_one_or_none()

    async def get_by_username(self, username: str) -> Optional[Bot]:
        result = await self.db.execute(
            select(Bot).where(Bot.bot_username == username)
        )
        return result.scalar_one_or_none()

    async def update(self, bot_id: int, data: BotUpdate) -> Optional[Bot]:
        bot = await self.get_by_id(bot_id)
        if not bot:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(bot, field, value)
        await self.db.flush()
        return bot

    async def delete(self, bot_id: int) -> bool:
        bot = await self.get_by_id(bot_id)
        if not bot:
            return False
        # Check for pending deliveries before deletion
        from backend.models.delivered_message import DeliveredMessage
        pending = await self.db.execute(
            select(DeliveredMessage).where(
                DeliveredMessage.bot_id == bot_id,
                DeliveredMessage.deleted == False,  # noqa: E712
            ).limit(1)
        )
        if pending.scalar_one_or_none():
            raise ValueError(
                "Cannot delete bot with pending message deliveries. "
                "Wait for auto-deletion to complete or clear messages first."
            )
        await self.db.delete(bot)
        await self.db.flush()
        return True

    async def list_all(self) -> List[Bot]:
        result = await self.db.execute(select(Bot).order_by(Bot.id))
        return list(result.scalars().all())

    async def list_active(self) -> List[Bot]:
        result = await self.db.execute(
            select(Bot).where(Bot.status == "active").order_by(Bot.id)
        )
        return list(result.scalars().all())

    async def touch(self, bot_id: int) -> None:
        """Update last_used_at timestamp."""
        bot = await self.get_by_id(bot_id)
        if bot:
            bot.last_used_at = datetime.now(timezone.utc)
            await self.db.flush()