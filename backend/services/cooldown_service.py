"""
Cooldown Service — manages user cooldowns when they exceed link access limits.

Tracks access counts per user across all bots globally, and applies cooldown
when the configured limit is exceeded.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.cooldown import Cooldown
from backend.models.user import User
from backend.redis_client import RedisClient

logger = logging.getLogger(__name__)

# Redis key prefix for access count tracking (per user)
_REDIS_ACCESS_COUNT_PREFIX = "cooldown:access:"


class CooldownService:
    """Manage user cooldowns based on access count limits."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_cooldown_for_user(self, user_id: int) -> Optional[Cooldown]:
        """Get active cooldown for user, or None if not in cooldown."""
        result = await self.db.execute(
            select(Cooldown).where(
                Cooldown.user_id == user_id,
                Cooldown.cooldown_until > datetime.now(timezone.utc),
            )
            .order_by(Cooldown.cooldown_until.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def get_all_active_cooldowns(self) -> list[dict]:
        """Get all currently active cooldowns with user info."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Cooldown, User).join(User, User.id == Cooldown.user_id)
            .where(Cooldown.cooldown_until > now)
            .order_by(Cooldown.cooldown_until.desc())
        )
        rows = result.all()
        cooldowns = []
        for cooldown, user in rows:
            remaining_seconds = int(
                (cooldown.cooldown_until - now).total_seconds()
            )
            cooldowns.append({
                "id": cooldown.id,
                "user_id": user.id,
                "telegram_id": user.telegram_id,
                "username": user.username or f"User {user.telegram_id}",
                "access_count": cooldown.access_count,
                "exceeded_at": cooldown.exceeded_at.isoformat(),
                "cooldown_until": cooldown.cooldown_until.isoformat(),
                "remaining_seconds": max(remaining_seconds, 0),
                "reason": cooldown.reason,
            })
        return cooldowns

    async def increment_access_count(
        self, user_id: int, cooldown_links_limit: int, cooldown_seconds: int
    ) -> tuple[int, bool]:
        """
        Increment access count for user (stored in Redis).

        Returns: (new_count, should_apply_cooldown)

        When count exceeds limit, returns (count, True) — caller should apply cooldown.
        """
        try:
            redis = RedisClient.get()
            key = f"{_REDIS_ACCESS_COUNT_PREFIX}{user_id}"
            
            # Increment and get TTL (expire in 24 hours for tracking)
            new_count = redis.client.incr(key)
            if new_count == 1:
                # First access: set TTL
                redis.client.expire(key, 86400)  # 24 hours
            
            exceeded = new_count > cooldown_links_limit
            return new_count, exceeded
        except Exception as e:
            logger.error("Failed to increment access count for user %s: %s", user_id, e)
            # Fallback: don't apply cooldown on Redis error
            return 0, False

    async def apply_cooldown(
        self,
        user_id: int,
        cooldown_seconds: int,
        access_count: int,
        cooldown_links_limit: int,
    ) -> Cooldown:
        """
        Apply cooldown to user.

        Creates or updates cooldown record and resets Redis access counter.
        """
        now = datetime.now(timezone.utc)
        cooldown_until = now + timedelta(seconds=cooldown_seconds)
        reason = f"Exceeded {cooldown_links_limit} link(s) access limit"

        # Check if user already has an active cooldown
        existing = await self.get_cooldown_for_user(user_id)
        if existing:
            # Extend existing cooldown
            existing.cooldown_until = cooldown_until
            existing.access_count = access_count
            existing.exceeded_at = now
            existing.reason = reason
            await self.db.flush()
            cooldown = existing
        else:
            # Create new cooldown record
            cooldown = Cooldown(
                user_id=user_id,
                exceeded_at=now,
                cooldown_until=cooldown_until,
                access_count=access_count,
                reason=reason,
            )
            self.db.add(cooldown)
            await self.db.flush()

        # Reset Redis access counter
        try:
            redis = RedisClient.get()
            key = f"{_REDIS_ACCESS_COUNT_PREFIX}{user_id}"
            redis.client.delete(key)
        except Exception as e:
            logger.error("Failed to reset access count for user %s: %s", user_id, e)

        logger.warning(
            "Cooldown applied: user_id=%s until=%s reason=%s",
            user_id,
            cooldown_until,
            reason,
        )
        return cooldown

    async def remove_cooldown(self, cooldown_id: int) -> bool:
        """Remove/clear a cooldown. Returns True if removed, False if not found."""
        result = await self.db.execute(
            select(Cooldown).where(Cooldown.id == cooldown_id)
        )
        cooldown = result.scalar_one_or_none()
        if cooldown:
            await self.db.delete(cooldown)
            await self.db.flush()
            logger.info("Cooldown removed: id=%s user_id=%s", cooldown_id, cooldown.user_id)
            return True
        return False

    async def extend_cooldown(self, cooldown_id: int, additional_seconds: int) -> Optional[Cooldown]:
        """Extend an active cooldown by additional_seconds."""
        result = await self.db.execute(
            select(Cooldown).where(Cooldown.id == cooldown_id)
        )
        cooldown = result.scalar_one_or_none()
        if cooldown:
            cooldown.cooldown_until += timedelta(seconds=additional_seconds)
            await self.db.flush()
            logger.info(
                "Cooldown extended: id=%s user_id=%s new_until=%s",
                cooldown_id,
                cooldown.user_id,
                cooldown.cooldown_until,
            )
            return cooldown
        return None

    async def clear_expired_cooldowns(self) -> int:
        """Delete all expired cooldowns. Returns count deleted."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Cooldown).where(Cooldown.cooldown_until <= now)
        )
        expired = result.scalars().all()
        for cooldown in expired:
            await self.db.delete(cooldown)
        if expired:
            await self.db.flush()
            logger.info("Cleared %d expired cooldowns", len(expired))
        return len(expired)
