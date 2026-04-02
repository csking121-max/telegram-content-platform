"""
Membership Engine — manages user membership lifecycle.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import List, Optional

from sqlalchemy import func as sa_func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.membership import Membership
from backend.models.membership_plan import MembershipPlan

logger = logging.getLogger(__name__)


class MembershipEngine:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_active(self, user_id: int) -> List[Membership]:
        """Return all active memberships for a user."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(Membership).where(
                Membership.user_id == user_id,
                (Membership.expiry_at.is_(None)) | (Membership.expiry_at > now),
            )
        )
        return list(result.scalars().all())

    async def has_type(self, user_id: int, membership_type: str) -> bool:
        """Check if user has a specific active membership type."""
        memberships = await self.get_active(user_id)
        return any(m.membership_type == membership_type for m in memberships)

    async def grant(
        self,
        user_id: int,
        membership_type: str,
        expiry_at: Optional[datetime] = None,
    ) -> Membership:
        """Grant a new membership."""
        membership = Membership(
            user_id=user_id,
            membership_type=membership_type,
            expiry_at=expiry_at,
        )
        self.db.add(membership)
        await self.db.flush()
        logger.info("Granted %s membership to user=%s", membership_type, user_id)
        return membership

    async def revoke(self, membership_id: int) -> bool:
        """Expire a membership immediately."""
        result = await self.db.execute(
            select(Membership).where(Membership.id == membership_id)
        )
        membership = result.scalar_one_or_none()
        if membership is None:
            return False
        membership.expiry_at = datetime.now(timezone.utc)
        await self.db.flush()
        return True

    async def get_by_id(self, membership_id: int) -> Optional[Membership]:
        result = await self.db.execute(
            select(Membership).where(Membership.id == membership_id)
        )
        return result.scalar_one_or_none()

    async def get_user_memberships(self, user_id: int) -> List[Membership]:
        """All memberships (including expired)."""
        result = await self.db.execute(
            select(Membership).where(Membership.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_user_max_tier_level(self, user_id: int) -> int:
        """Return the highest tier_level among user's active memberships, or 0."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(sa_func.coalesce(sa_func.max(MembershipPlan.tier_level), 0))
            .select_from(Membership)
            .join(
                MembershipPlan,
                MembershipPlan.access_type == Membership.membership_type,
            )
            .where(
                Membership.user_id == user_id,
                (Membership.expiry_at.is_(None)) | (Membership.expiry_at > now),
            )
        )
        return result.scalar() or 0