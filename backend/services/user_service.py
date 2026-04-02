"""
User Service — CRUD + lookup for users.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.credit import Credit
from backend.models.user import User
from backend.schemas.user import UserCreate, UserUpdate

logger = logging.getLogger(__name__)


class UserService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_or_create(self, telegram_id: int, username: Optional[str] = None) -> tuple[User, bool]:
        """Return (user, created). Auto-provisions credit account."""
        user = await self.get_by_telegram_id(telegram_id)
        if user:
            user.last_active_at = datetime.now(timezone.utc)
            if username and user.username != username:
                user.username = username
            await self.db.flush()
            return user, False

        user = User(telegram_id=telegram_id, username=username)
        self.db.add(user)
        await self.db.flush()

        # Auto-provision credit account — check platform setting first, fallback to env
        default_credits = settings.DEFAULT_CREDIT_BALANCE
        try:
            from backend.models.platform_setting import PlatformSetting
            result = await self.db.execute(
                select(PlatformSetting).where(PlatformSetting.key == "default_credits_new_user")
            )
            setting = result.scalar_one_or_none()
            if setting and setting.value:
                default_credits = int(setting.value)
        except Exception:
            pass

        credit = Credit(user_id=user.id, balance=default_credits)
        self.db.add(credit)
        await self.db.flush()

        logger.info("Created user id=%s tg=%s default_credits=%s", user.id, telegram_id, default_credits)
        return user, True

    async def get_by_id(self, user_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def get_by_telegram_id(self, telegram_id: int) -> Optional[User]:
        result = await self.db.execute(
            select(User).where(User.telegram_id == telegram_id)
        )
        return result.scalar_one_or_none()

    async def update(self, user_id: int, data: UserUpdate) -> Optional[User]:
        user = await self.get_by_id(user_id)
        if not user:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(user, field, value)
        await self.db.flush()
        return user

    async def list_all(self, limit: int = 100, offset: int = 0) -> List[User]:
        result = await self.db.execute(
            select(User).order_by(User.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    async def count(self) -> int:
        result = await self.db.execute(select(func.count(User.id)))
        return result.scalar_one()

    async def block(self, user_id: int, until: datetime) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False
        user.blocked_until = until
        await self.db.flush()
        return True

    async def unblock(self, user_id: int) -> bool:
        user = await self.get_by_id(user_id)
        if not user:
            return False
        user.blocked_until = None
        await self.db.flush()
        return True