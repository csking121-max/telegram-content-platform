"""
Referral Service — invite codes, usage tracking, reward granting.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.engines.credit_engine import CreditEngine
from backend.models.referral import Referral
from backend.utils.token_generator import generate_invite_code

logger = logging.getLogger(__name__)


class ReferralService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.credit_engine = CreditEngine(db)

    async def create_invite(self, referrer_user_id: int) -> Referral:
        """Generate a unique invite code for a user."""
        code = generate_invite_code()
        referral = Referral(invite_code=code, referrer_user_id=referrer_user_id)
        self.db.add(referral)
        await self.db.flush()
        logger.info("Created invite code=%s for user=%s", code, referrer_user_id)
        return referral

    async def use_invite(self, invite_code: str, user_id: int) -> Optional[Referral]:
        """
        Mark an invite code as used.
        Does NOT grant reward yet — reward is granted after first successful unlock.
        """
        result = await self.db.execute(
            select(Referral).where(Referral.invite_code == invite_code)
        )
        referral = result.scalar_one_or_none()
        if referral is None:
            return None
        if referral.used_by_user_id is not None:
            return None  # Already used
        if referral.referrer_user_id == user_id:
            return None  # Can't use own code

        referral.used_by_user_id = user_id
        await self.db.flush()
        return referral

    async def try_grant_reward(self, user_id: int) -> bool:
        """
        Check if user was referred and hasn't had reward granted yet.
        Called after a successful content unlock.
        Uses atomic UPDATE to prevent double-grant race condition.
        """
        # Atomic claim: only one concurrent call can flip reward_granted
        result = await self.db.execute(
            update(Referral)
            .where(
                Referral.used_by_user_id == user_id,
                Referral.reward_granted == False,  # noqa: E712
            )
            .values(reward_granted=True)
        )
        if result.rowcount == 0:
            return False

        # Re-fetch the referral to get referrer info
        ref_result = await self.db.execute(
            select(Referral).where(
                Referral.used_by_user_id == user_id,
                Referral.reward_granted == True,  # noqa: E712
            )
        )
        referral = ref_result.scalar_one_or_none()
        if referral is None:
            return False

        # Grant reward to referrer
        await self.credit_engine.add(
            referral.referrer_user_id,
            settings.REFERRAL_REWARD_CREDITS,
            f"referral_reward:{referral.invite_code}",
        )
        await self.db.flush()
        logger.info(
            "Granted referral reward to user=%s for code=%s",
            referral.referrer_user_id,
            referral.invite_code,
        )
        return True

    async def get_by_code(self, code: str) -> Optional[Referral]:
        result = await self.db.execute(select(Referral).where(Referral.invite_code == code))
        return result.scalar_one_or_none()

    async def get_user_referrals(self, user_id: int) -> List[Referral]:
        result = await self.db.execute(
            select(Referral).where(Referral.referrer_user_id == user_id)
        )
        return list(result.scalars().all())

    async def count_successful(self, user_id: int) -> int:
        result = await self.db.execute(
            select(func.count(Referral.id)).where(
                Referral.referrer_user_id == user_id,
                Referral.used_by_user_id.isnot(None),
            )
        )
        return result.scalar_one()