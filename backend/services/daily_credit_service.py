"""
Daily Credit Service — handles auto-granting daily credits to all users.

Called by the daily_credit_worker on a schedule.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timezone

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.credit import Credit
from backend.models.credit_history import CreditHistory
from backend.models.user import User
from backend.services.platform_settings_service import PlatformSettingsService

logger = logging.getLogger(__name__)


class DailyCreditService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def grant_daily_credits(self) -> int:
        """
        Grant daily credits to ALL users who haven't received them today.
        Processes in batches to avoid loading all user IDs into memory.

        Returns the number of users who received credits.
        """
        svc = PlatformSettingsService(self.db)
        enabled = (await svc.get("daily_credits_enabled", "true")).lower() in ("true", "1", "yes")
        if not enabled:
            logger.info("Daily credits disabled, skipping")
            return 0

        amount = await svc.get_int("daily_credits_amount", 100)
        if amount <= 0:
            logger.info("Daily credit amount is 0, skipping")
            return 0

        today_str = date.today().isoformat()
        reason = f"daily_grant:{today_str}"

        # Subquery: users who already got today's grant
        already_subq = (
            select(CreditHistory.user_id)
            .where(CreditHistory.reason == reason)
            .scalar_subquery()
        )

        BATCH_SIZE = 500
        count = 0
        offset = 0

        while True:
            # Fetch a batch of user IDs that haven't received today's grant
            result = await self.db.execute(
                select(User.id)
                .where(User.id.not_in(already_subq))
                .order_by(User.id)
                .limit(BATCH_SIZE)
                .offset(offset)
            )
            batch_ids = list(result.scalars().all())
            if not batch_ids:
                break

            for uid in batch_ids:
                # Ensure credit account exists
                cr_result = await self.db.execute(select(Credit).where(Credit.user_id == uid))
                credit = cr_result.scalar_one_or_none()
                if credit is None:
                    credit = Credit(user_id=uid, balance=0)
                    self.db.add(credit)
                    await self.db.flush()

                credit.balance += amount
                self.db.add(CreditHistory(
                    user_id=uid,
                    change_amount=amount,
                    reason=reason,
                ))
                count += 1

            await self.db.flush()

            # If batch was smaller than BATCH_SIZE, we've processed everyone
            if len(batch_ids) < BATCH_SIZE:
                break
            # Don't increment offset — already-granted users are now excluded by subquery

        logger.info("Granted %d daily credits to %d users for %s", amount, count, today_str)
        return count
