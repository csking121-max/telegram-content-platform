"""
Credit Engine — ALL credit mutations go through here.

Every change is wrapped in an atomic transaction and recorded in credit_history.
"""
from __future__ import annotations
import asyncio
import logging
from datetime import datetime, timezone

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.credit import Credit
from backend.models.credit_history import CreditHistory

logger = logging.getLogger(__name__)


class CreditEngine:
    """Stateless — instantiate per request with an async session."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Queries ──────────────────────────────────────

    async def get_balance(self, user_id: int) -> int:
        result = await self.db.execute(select(Credit).where(Credit.user_id == user_id))
        credit = result.scalar_one_or_none()
        return credit.balance if credit else 0

    # ── Mutations (atomic) ───────────────────────────

    async def ensure_account(self, user_id: int, initial: int = 0) -> Credit:
        """Create credit row if it doesn't exist."""
        result = await self.db.execute(select(Credit).where(Credit.user_id == user_id))
        credit = result.scalar_one_or_none()
        if credit is None:
            credit = Credit(user_id=user_id, balance=initial)
            self.db.add(credit)
            await self.db.flush()
            logger.info("Created credit account user=%s initial=%s", user_id, initial)
        return credit

    async def deduct(self, user_id: int, amount: int, reason: str) -> int:
        """
        Deduct credits atomically.  Returns new balance.
        Raises ValueError if insufficient.
        """
        if amount <= 0:
            raise ValueError("Deduction amount must be positive")

        await self.ensure_account(user_id)

        # Atomic deduction: single UPDATE that checks balance in the WHERE clause
        result = await self.db.execute(
            update(Credit)
            .where(Credit.user_id == user_id, Credit.balance >= amount)
            .values(balance=Credit.balance - amount)
        )
        if result.rowcount == 0:
            # Re-fetch for the error message
            bal = await self.get_balance(user_id)
            raise ValueError(
                f"Insufficient credits: have {bal}, need {amount}"
            )

        self._record(user_id, -amount, reason)
        await self.db.flush()

        new_balance = await self.get_balance(user_id)
        logger.info("Deducted %s credits from user=%s reason=%s", amount, user_id, reason)

        # Track spend for daily streak
        try:
            from backend.engines.streak_engine import StreakEngine
            streak_engine = StreakEngine(self.db)
            await streak_engine.record_spend(user_id, amount)
        except Exception as exc:
            logger.warning("Streak tracking failed for user=%s: %s", user_id, exc)

        # Queue low-credit warning check
        try:
            from backend.redis_client import RedisClient
            rc = RedisClient.get()
            await asyncio.to_thread(rc.enqueue, "queue:low_credit_notify", {
                "user_id": user_id,
                "new_balance": new_balance,
            })
        except Exception as exc:
            logger.warning("Low-credit notify enqueue failed for user=%s: %s", user_id, exc)

        return new_balance

    async def add(self, user_id: int, amount: int, reason: str) -> int:
        """Add credits atomically.  Returns new balance."""
        if amount <= 0:
            raise ValueError("Addition amount must be positive")

        credit = await self.ensure_account(user_id)
        credit.balance += amount
        self.db.add(credit)
        self._record(user_id, amount, reason)
        await self.db.flush()
        logger.info("Added %s credits to user=%s reason=%s", amount, user_id, reason)

        # Clear low-credit notification flags so user can be re-notified next time
        try:
            from backend.redis_client import RedisClient
            rc = RedisClient.get()

            def _clear_flags() -> None:
                cursor = 0
                pattern = f"low_credit_notified:{user_id}:*"
                while True:
                    cursor, keys = rc.client.scan(cursor, match=pattern, count=100)
                    if keys:
                        rc.client.delete(*keys)
                    if cursor == 0:
                        break

            await asyncio.to_thread(_clear_flags)
        except Exception as exc:
            logger.warning("Failed to clear low-credit flags for user=%s: %s", user_id, exc)

        return credit.balance

    async def admin_set(self, user_id: int, new_balance: int, reason: str) -> int:
        """Admin override — set balance to exact value."""
        credit = await self.ensure_account(user_id)
        diff = new_balance - credit.balance
        credit.balance = new_balance
        self.db.add(credit)
        self._record(user_id, diff, f"admin_set: {reason}")
        await self.db.flush()
        return credit.balance

    # ── Internal ─────────────────────────────────────

    def _record(self, user_id: int, change: int, reason: str) -> None:
        entry = CreditHistory(
            user_id=user_id,
            change_amount=change,
            reason=reason,
        )
        self.db.add(entry)