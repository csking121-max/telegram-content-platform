"""
Ad-Watch Service — manages the full ad-watch token lifecycle.

Flow:
1. User clicks "Watch Ad" → start_session() creates an AdWatchToken
2. User completes each ad step → complete_step() increments ads_completed
3. After all ads done → activate() sets 12-hour access
4. AccessControlEngine checks for active ad-watch token before denying
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.ad_watch_token import AdWatchToken
from backend.models.user import User
from backend.services.platform_settings_service import PlatformSettingsService

logger = logging.getLogger(__name__)


class AdWatchService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def _get_settings(self) -> tuple[int, int]:
        """Return (ads_required, free_hours) from platform settings."""
        svc = PlatformSettingsService(self.db)
        ads_required = await svc.get_int("ad_watch_count", 4)
        free_hours = await svc.get_int("ad_watch_free_hours", 12)
        return ads_required, free_hours

    async def start_session(self, user_id: int) -> AdWatchToken:
        """Create a new ad-watch session for a user."""
        ads_required, _ = await self._get_settings()
        token_str = secrets.token_urlsafe(32)
        token = AdWatchToken(
            user_id=user_id,
            token=token_str,
            ads_required=ads_required,
            ads_completed=0,
        )
        self.db.add(token)
        await self.db.flush()
        logger.info("Created ad-watch session token=%s user=%s ads=%s", token_str[:8], user_id, ads_required)
        return token

    async def get_by_token(self, token_str: str) -> Optional[AdWatchToken]:
        result = await self.db.execute(
            select(AdWatchToken).where(AdWatchToken.token == token_str)
        )
        return result.scalar_one_or_none()

    async def complete_step(self, token_str: str, step: int) -> AdWatchToken:
        """Record completion of an ad step. Returns updated token."""
        token = await self.get_by_token(token_str)
        if not token:
            raise ValueError("Invalid ad-watch token")
        if token.used:
            raise ValueError("Token already used")
        if step != token.ads_completed + 1:
            raise ValueError(f"Expected step {token.ads_completed + 1}, got {step}")
        if step > token.ads_required:
            raise ValueError("All steps already completed")

        token.ads_completed = step
        await self.db.flush()
        logger.info("Ad step %d/%d completed for token=%s", step, token.ads_required, token_str[:8])
        return token

    async def activate(self, token_str: str) -> AdWatchToken:
        """Activate 12-hour free access after all ads are watched.

        Uses an atomic UPDATE ... WHERE to prevent double-activation from
        concurrent requests.
        """
        token = await self.get_by_token(token_str)
        if not token:
            raise ValueError("Invalid ad-watch token")
        if token.used:
            raise ValueError("Token already used")
        if token.ads_completed < token.ads_required:
            raise ValueError(f"Only {token.ads_completed}/{token.ads_required} ads completed")
        if token.activated:
            raise ValueError("Token already activated")

        _, free_hours = await self._get_settings()
        now = datetime.now(timezone.utc)
        expires = now + timedelta(hours=free_hours)

        # Atomic CAS: only activate if still not activated
        result = await self.db.execute(
            update(AdWatchToken)
            .where(
                AdWatchToken.token == token_str,
                AdWatchToken.activated == False,
                AdWatchToken.used == False,
            )
            .values(activated=True, activated_at=now, expires_at=expires, used=True)
        )
        if result.rowcount == 0:
            raise ValueError("Token already activated (concurrent request)")

        await self.db.refresh(token)
        logger.info(
            "Ad-watch token=%s activated for user=%s, expires=%s",
            token_str[:8], token.user_id, token.expires_at.isoformat(),
        )
        return token

    async def has_active_ad_access(self, user_id: int) -> Optional[AdWatchToken]:
        """Check if user has any active (non-expired) ad-watch access."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(AdWatchToken).where(
                AdWatchToken.user_id == user_id,
                AdWatchToken.activated == True,  # noqa: E712
                AdWatchToken.expires_at > now,
            ).order_by(AdWatchToken.expires_at.desc()).limit(1)
        )
        return result.scalar_one_or_none()

    async def get_user_sessions(self, user_id: int, limit: int = 10) -> list[AdWatchToken]:
        result = await self.db.execute(
            select(AdWatchToken)
            .where(AdWatchToken.user_id == user_id)
            .order_by(AdWatchToken.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
