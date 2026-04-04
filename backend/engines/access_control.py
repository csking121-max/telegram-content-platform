"""
Access Control Engine — central authority for TOKEN → PACK access decisions.

Input:  (telegram_id, token_string)
Output: AccessResponse (allowed / denied + reason + upgrade options)
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.content_pack import ContentPack
from backend.models.credit import Credit
from backend.models.membership import Membership
from backend.models.membership_plan import MembershipPlan
from backend.models.pack_item import PackItem
from backend.models.token import Token
from backend.models.user import User
from backend.schemas.access import AccessResponse
from backend.engines.credit_engine import CreditEngine

logger = logging.getLogger(__name__)


class AccessControlEngine:
    """Stateless -- instantiate per request with an async session."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def check(self, telegram_id: int, token_str: str) -> AccessResponse:
        """
        Full check pipeline:
        1. Token exists
        2. Token not expired
        3. Token single-use not exceeded
        4. Token user binding
        5. User exists & not blocked
        6. Ad-watch active access (free tier grant)
        7. Membership eligibility
        8. Credit balance
        """
        # 1. Token lookup
        token = await self._get_token(token_str)
        if token is None:
            logger.info("access_denied tg=%s token=%s… reason=not_found", telegram_id, token_str[:8])
            return AccessResponse(allowed=False, reason="Token does not exist.")

        # 2. Expiry
        if token.expires_at:
            expires = token.expires_at
            now = datetime.now(timezone.utc)
            # Normalise: if stored as naive assume UTC
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            if now > expires:
                logger.info("access_denied tg=%s token=%s… reason=expired", telegram_id, token_str[:8])
                return AccessResponse(allowed=False, reason="Token has expired.")

        # 3. Single-use
        if token.single_use and token.used_count > 0:
            logger.info("access_denied tg=%s token=%s… reason=already_used", telegram_id, token_str[:8])
            return AccessResponse(allowed=False, reason="Token has already been used.")

        # 4. User binding
        user = await self._get_user_by_tg(telegram_id)
        if user is None:
            logger.info("access_denied tg=%s reason=not_registered", telegram_id)
            return AccessResponse(allowed=False, reason="User not registered.")

        if token.bound_user_id and token.bound_user_id != user.id:
            logger.warning("access_denied tg=%s token=%s… reason=wrong_user_binding", telegram_id, token_str[:8])
            return AccessResponse(allowed=False, reason="Token is bound to another user.")

        # 5. Blocked
        if user.blocked_until:
            blocked = user.blocked_until
            if blocked.tzinfo is None:
                blocked = blocked.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) < blocked:
                logger.warning("access_denied tg=%s reason=blocked until=%s", telegram_id, blocked)
                return AccessResponse(allowed=False, reason="User is temporarily blocked.")

        # 6 & 7 & 8. Pack access rules
        pack = await self._get_pack(token.pack_id)
        if pack is None:
            return AccessResponse(allowed=False, reason="Content pack not found.")

        return await self._check_access_type(user, pack)

    # ── Internal helpers ─────────────────────────────

    async def _get_token(self, token_str: str) -> Optional[Token]:
        result = await self.db.execute(select(Token).where(Token.token == token_str))
        return result.scalar_one_or_none()

    async def _get_user_by_tg(self, telegram_id: int) -> Optional[User]:
        result = await self.db.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def _get_pack(self, pack_id: int) -> Optional[ContentPack]:
        result = await self.db.execute(select(ContentPack).where(ContentPack.id == pack_id))
        return result.scalar_one_or_none()

    async def _check_access_type(self, user: User, pack: ContentPack) -> AccessResponse:
        access = pack.access_type

        if access == "free":
            return AccessResponse(allowed=True, pack_id=pack.id)

        # Check if user has active ad-watch access (grants free-tier for any content)
        if await self._has_ad_watch_access(user.id):
            return AccessResponse(allowed=True, pack_id=pack.id)

        # "credits_only" — always requires credit payment, no membership bypass
        if access == "credits_only":
            return await self._charge_credits(user, pack)

        if access == "credits":
            # Members with ANY active membership get credits content for free
            if await self._has_any_active_membership(user.id):
                return AccessResponse(allowed=True, pack_id=pack.id)
            # Non-members must pay credits
            return await self._charge_credits(user, pack)

        # Any other access type (vip, premium, daily_pass, or custom) = tier-based membership check
        ok = await self._has_sufficient_membership(user.id, access)
        if ok:
            return AccessResponse(allowed=True, pack_id=pack.id)
        return AccessResponse(
            allowed=False,
            reason=f"Requires {access} membership.",
            upgrade_options=[access],
        )

    async def _charge_credits(self, user: User, pack: ContentPack) -> AccessResponse:
        """Deduct credits for a pack. Returns AccessResponse."""
        cost = await self._calc_credit_cost(pack)
        balance = await self._get_balance(user.id)
        if balance >= cost:
            credit_engine = CreditEngine(self.db)
            try:
                await credit_engine.deduct(
                    user_id=user.id,
                    amount=cost,
                    reason=f"Content access: {pack.title} (pack #{pack.id})",
                )
            except ValueError:
                return AccessResponse(
                    allowed=False,
                    reason="Credit deduction failed.",
                    credit_cost=cost,
                    upgrade_options=["buy_credits"],
                )
            return AccessResponse(
                allowed=True,
                pack_id=pack.id,
                credits_deducted=cost,
                credit_cost=cost,
            )
        return AccessResponse(
            allowed=False,
            reason=f"Insufficient credits (need {cost}, have {balance}).",
            credit_cost=cost,
            upgrade_options=["buy_credits"],
        )

    async def _has_any_active_membership(self, user_id: int) -> bool:
        """Return True if the user has at least one non-expired membership."""
        result = await self.db.execute(
            select(Membership.id).where(
                Membership.user_id == user_id,
                (Membership.expiry_at.is_(None)) | (Membership.expiry_at > func.now()),
            ).limit(1)
        )
        return result.scalar_one_or_none() is not None

    async def _has_sufficient_membership(self, user_id: int, required_access_type: str) -> bool:
        """Check if user has any active membership whose tier_level >= the required tier.

        Uses a single query with a subquery instead of 3 separate round-trips.
        """
        from sqlalchemy import func

        # Get the tier_level required for this access_type
        result = await self.db.execute(
            select(MembershipPlan.tier_level)
            .where(MembershipPlan.access_type == required_access_type, MembershipPlan.is_active == True)
            .order_by(MembershipPlan.tier_level.desc())
            .limit(1)
        )
        required_tier = result.scalar_one_or_none()
        if required_tier is None:
            # No plan defines this access_type — fall back to exact match
            return await self._has_active_membership(user_id, required_access_type)

        # Single query: join user's active memberships → plans → check max tier
        result = await self.db.execute(
            select(func.max(MembershipPlan.tier_level))
            .select_from(Membership)
            .join(MembershipPlan, MembershipPlan.access_type == Membership.membership_type)
            .where(
                Membership.user_id == user_id,
                (Membership.expiry_at.is_(None)) | (Membership.expiry_at > func.now()),
                MembershipPlan.is_active == True,
            )
        )
        user_max_tier = result.scalar_one_or_none()
        if user_max_tier is None:
            return False  # user has no active memberships at all

        return user_max_tier >= required_tier

    async def _has_active_membership(self, user_id: int, mtype: str) -> bool:
        result = await self.db.execute(
            select(Membership).where(
                Membership.user_id == user_id,
                Membership.membership_type == mtype,
                (Membership.expiry_at.is_(None)) | (Membership.expiry_at > func.now()),
            )
        )
        return result.scalar_one_or_none() is not None

    async def _has_ad_watch_access(self, user_id: int) -> bool:
        """Check if user has an active (non-expired) ad-watch token."""
        try:
            from backend.models.ad_watch_token import AdWatchToken
            from sqlalchemy import func
            result = await self.db.execute(
                select(AdWatchToken).where(
                    AdWatchToken.user_id == user_id,
                    AdWatchToken.activated == True,
                    AdWatchToken.expires_at > func.now(),
                ).limit(1)
            )
            return result.scalar_one_or_none() is not None
        except Exception:
            return False

    async def _get_balance(self, user_id: int) -> int:
        result = await self.db.execute(select(Credit).where(Credit.user_id == user_id))
        credit = result.scalar_one_or_none()
        return credit.balance if credit else 0

    async def _calc_credit_cost(self, pack: ContentPack) -> int:
        """Calculate total credit cost based on credit_mode."""
        mode = getattr(pack, 'credit_mode', 'per_item') or 'per_item'
        if mode == 'per_pack':
            # Flat cost for the entire pack
            return max(pack.credit_cost, 1)
        else:
            # per_item: cost per item * number of items
            per_item = getattr(pack, 'credit_per_item', 1) or 1
            item_count = await self._count_items(pack.id)
            return max(per_item * item_count, 1)

    async def _count_items(self, pack_id: int) -> int:
        from sqlalchemy import func as sa_func
        result = await self.db.execute(
            select(sa_func.count()).select_from(PackItem).where(PackItem.pack_id == pack_id)
        )
        return result.scalar() or 0