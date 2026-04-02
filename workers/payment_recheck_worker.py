"""
Payment Recheck Worker — periodically scans 'utr_submitted' orders
and re-tries matching against SMS logs.

If a match is found, grants access and notifies the user via Telegram.
This catches payments that were missed due to backend downtime or
timing issues between UTR submission and SMS arrival.

Runs every 60 seconds.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.models.bot import Bot
from backend.models.user import User
from backend.services.payment_order_service import PaymentOrderService

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"
POLL_INTERVAL = 60  # seconds


class PaymentRecheckWorker:
    """Periodically rechecks utr_submitted orders and notifies matched users."""

    def __init__(self, interval_seconds: int = POLL_INTERVAL):
        self.interval = interval_seconds

    async def run(self) -> None:
        logger.info("PaymentRecheckWorker started (interval=%ds)", self.interval)
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    await self._tick(db)
                    await db.commit()
            except Exception:
                logger.exception("PaymentRecheckWorker error")

            await asyncio.sleep(self.interval)

    async def _tick(self, db: AsyncSession) -> None:
        order_svc = PaymentOrderService(db)
        verified_count, verified_user_ids = await order_svc.recheck_pending_orders()
        await db.flush()

        if verified_count == 0:
            return

        logger.info(
            "PaymentRecheckWorker: %d order(s) auto-verified",
            verified_count,
        )

        # Resolve user_ids → telegram_ids and notify
        if verified_user_ids:
            result = await db.execute(
                select(User.telegram_id).where(User.id.in_(verified_user_ids))
            )
            telegram_ids = [r for r in result.scalars().all() if r]

            bot_token = await self._get_bot_token(db)
            if bot_token:
                for tg_id in telegram_ids:
                    await self._notify_user(bot_token, tg_id)

    async def _get_bot_token(self, db: AsyncSession) -> str | None:
        result = await db.execute(
            select(Bot.bot_token).where(Bot.status == "active").limit(1)
        )
        return result.scalar_one_or_none()

    async def _notify_user(self, bot_token: str, telegram_id: int) -> None:
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                resp = await client.post(
                    f"{TELEGRAM_API}/bot{bot_token}/sendMessage",
                    json={
                        "chat_id": telegram_id,
                        "text": (
                            "✅ *Payment Verified!*\n\n"
                            "Your payment has been confirmed and access has been granted."
                        ),
                        "parse_mode": "Markdown",
                    },
                )
                if resp.status_code == 200:
                    logger.info("Notified user %s of verified payment", telegram_id)
                else:
                    logger.warning(
                        "Failed to notify user %s: %s",
                        telegram_id,
                        resp.text[:200],
                    )
        except Exception:
            logger.exception("Error notifying user %s", telegram_id)
