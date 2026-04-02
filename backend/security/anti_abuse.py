"""
Anti-abuse guard — credit fraud detection, suspicious behaviour flags.
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.models.credit_history import CreditHistory

logger = logging.getLogger(__name__)


class AntiAbuseGuard:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check_credit_fraud(self, user_id: int) -> bool:
        """
        Returns True if suspicious activity detected.
        Checks: too many deductions in a short window.
        """
        window = datetime.now(timezone.utc) - timedelta(
            seconds=settings.CREDIT_FRAUD_WINDOW_SECONDS
        )
        result = await self.db.execute(
            select(func.count(CreditHistory.id)).where(
                CreditHistory.user_id == user_id,
                CreditHistory.change_amount < 0,
                CreditHistory.created_at >= window,
            )
        )
        count = result.scalar_one()
        if count >= settings.CREDIT_FRAUD_MAX_DEDUCTIONS:
            logger.warning(
                "Credit fraud detected: user=%s had %d deductions in %ds",
                user_id,
                count,
                settings.CREDIT_FRAUD_WINDOW_SECONDS,
            )
            return True
        return False

    async def check_rapid_token_use(self, user_id: int, window_seconds: int = 5) -> bool:
        """
        Check if a user is spamming token validations (rapid /start commands).
        Uses Redis for speed.  Fails closed (returns True) if Redis is down.
        """
        try:
            from backend.redis_client import RedisClient

            redis = RedisClient.get()
            key = f"abuse:token_use:{user_id}"
            count = redis.incr_with_ttl(key, window_seconds)
            if count > 3:
                logger.warning("Rapid token use detected: user=%s count=%d", user_id, count)
                return True
            return False
        except Exception:
            logger.warning("Redis unavailable — failing closed for abuse check user=%s", user_id)
            return True