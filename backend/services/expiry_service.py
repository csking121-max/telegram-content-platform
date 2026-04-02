"""
Expiry Service — proactively revokes expired memberships, passes, and ad-watch tokens.

Called by the expiry_worker on a schedule (e.g., every 5 minutes).
This satisfies the §9.1 requirement: "Access expiry must be enforced by a
scheduled background job — not lazily checked only on the next user request."
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.membership import Membership
from backend.models.ad_watch_token import AdWatchToken
from backend.models.payment_order import PaymentOrder

logger = logging.getLogger(__name__)


class ExpiryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def expire_memberships(self) -> int:
        """Delete expired memberships. Returns count expired."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            delete(Membership).where(
                Membership.expiry_at.isnot(None),
                Membership.expiry_at <= now,
            )
        )
        count = result.rowcount
        if count:
            await self.db.flush()
            logger.info("Deleted %d expired memberships", count)
        return count

    async def expire_ad_tokens(self) -> int:
        """Mark expired ad-watch tokens as used. Returns count."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            update(AdWatchToken)
            .where(
                AdWatchToken.activated == True,  # noqa: E712
                AdWatchToken.used == False,  # noqa: E712
                AdWatchToken.expires_at.isnot(None),
                AdWatchToken.expires_at <= now,
            )
            .values(used=True)
        )
        count = result.rowcount
        if count:
            await self.db.flush()
            logger.info("Marked %d expired ad-watch tokens as used", count)
        return count

    async def expire_payment_orders(self) -> int:
        """Expire stale payment orders. Returns count expired."""
        now = datetime.now(timezone.utc)
        result = await self.db.execute(
            select(PaymentOrder).where(
                PaymentOrder.status.in_(["pending", "utr_submitted"]),
                PaymentOrder.expires_at <= now,
            )
        )
        orders = list(result.scalars().all())
        for order in orders:
            order.status = "expired"
        if orders:
            await self.db.flush()
            logger.info("Expired %d stale payment orders", len(orders))
        return len(orders)

    async def run_all(self) -> dict[str, int]:
        """Run all expiry checks. Returns counts."""
        m = await self.expire_memberships()
        a = await self.expire_ad_tokens()
        p = await self.expire_payment_orders()
        return {"memberships": m, "ad_tokens": a, "payment_orders": p}
