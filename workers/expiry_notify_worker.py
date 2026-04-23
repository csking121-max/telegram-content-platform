"""
Expiry Notification Worker — sends targeted Telegram messages to users whose
membership is expiring within a configurable number of days.

Runs periodically (every 30 minutes).  Each membership gets notified at most
once (tracked by ``expiry_notified_at``).
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.models.bot import Bot
from backend.models.membership import Membership
from backend.models.membership_plan import MembershipPlan
from backend.models.user import User
from backend.services.platform_settings_service import PlatformSettingsService

logger = logging.getLogger(__name__)

TELEGRAM_API = "https://api.telegram.org"

# Known Telegram errors that are normal and should be silently skipped.
_SILENT_ERRORS = frozenset({
    "chat not found",
    "bot was blocked by the user",
    "user is deactivated",
    "bot can't initiate conversation with a user",
    "have no rights to send a message",
})


class ExpiryNotifyWorker:
    """Periodically finds expiring memberships and notifies users."""

    def __init__(self, interval_seconds: int = 1800):
        self.interval = interval_seconds

    async def run(self) -> None:
        logger.info("ExpiryNotifyWorker started (interval=%ds)", self.interval)
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    await self._tick(db)
                    await db.commit()
            except Exception:
                logger.exception("ExpiryNotifyWorker error")

            await asyncio.sleep(self.interval)

    # ── Main tick ────────────────────────────────────

    async def _tick(self, db: AsyncSession) -> None:
        settings = PlatformSettingsService(db)
        enabled = (await settings.get("expiry_notify_enabled", "true")).lower() in (
            "true", "1", "yes",
        )
        if not enabled:
            return

        days_before = await settings.get_int("expiry_notify_days_before", 3)

        now = datetime.now(timezone.utc)
        cutoff = now + timedelta(days=days_before)

        # Find active memberships expiring within the window, not yet notified
        result = await db.execute(
            select(Membership)
            .where(
                Membership.expiry_at.isnot(None),
                Membership.expiry_at > now,
                Membership.expiry_at <= cutoff,
                Membership.expiry_notified_at.is_(None),
            )
            .limit(500)
        )
        memberships = list(result.scalars().all())
        if not memberships:
            return

        logger.info("Found %d memberships expiring within %d days", len(memberships), days_before)

        # Get bot token for sending messages (use first active bot)
        bot_result = await db.execute(
            select(Bot).where(Bot.status == "active").limit(1)
        )
        bot = bot_result.scalar_one_or_none()
        if not bot:
            logger.warning("No active bot found — cannot send expiry notifications")
            return

        # Build plan lookup for renewal links
        plan_result = await db.execute(
            select(MembershipPlan).where(MembershipPlan.is_active == True)
        )
        plans = {p.access_type: p for p in plan_result.scalars().all()}

        sent = 0
        failed = 0

        for membership in memberships:
            # Resolve telegram_id
            user_result = await db.execute(
                select(User.telegram_id).where(User.id == membership.user_id)
            )
            telegram_id = user_result.scalar_one_or_none()
            if not telegram_id:
                continue

            plan = plans.get(membership.membership_type)
            ok = await self._send_notification(
                bot.bot_token, telegram_id, membership, plan,
            )
            if ok:
                membership.expiry_notified_at = now
                sent += 1
            else:
                failed += 1

            # Rate limit: sleep every 25 messages
            if (sent + failed) % 25 == 0:
                await asyncio.sleep(1)

        if sent or failed:
            logger.info("Expiry notifications: sent=%d failed=%d", sent, failed)

    # ── Send a single notification ───────────────────

    async def _send_notification(
        self,
        bot_token: str,
        telegram_id: int,
        membership: Membership,
        plan: MembershipPlan | None,
    ) -> bool:
        expiry = membership.expiry_at
        if expiry and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)

        now = datetime.now(timezone.utc)
        remaining = (expiry - now) if expiry else timedelta()
        days_left = max(remaining.days, 0)
        hours_left = max(remaining.seconds // 3600, 0) if days_left == 0 else 0

        mtype = (membership.membership_type or "").upper()

        # Time remaining display
        if days_left > 0:
            time_str = f"{days_left} day{'s' if days_left != 1 else ''}"
        elif hours_left > 0:
            time_str = f"{hours_left} hour{'s' if hours_left != 1 else ''}"
        else:
            time_str = "less than an hour"

        # Build message (Markdown v1: *bold*, _italic_)
        text = (
            f"\u23f0 *Membership Expiry Reminder*\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
            f"Your *{_md_escape(mtype)}* membership expires in *{time_str}*!\n\n"
            f"Renew now to keep your access without interruption.\n\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"_Tap below to renew \u2b07\ufe0f_"
        )

        # Inline keyboard with renewal options
        buttons = []
        if plan:
            row = []
            row.append({
                "text": f"\U0001f4b3 Renew \u20b9{plan.price_inr}",
                "callback_data": f"plan:{plan.id}",
            })
            if plan.credit_price and plan.credit_price > 0:
                row.append({
                    "text": f"\U0001fa99 {plan.credit_price} Credits",
                    "callback_data": f"plan_credits:{plan.id}",
                })
            buttons.append(row)
        buttons.append([{
            "text": "\U0001f4cb View All Plans",
            "callback_data": "menu:plans",
        }])

        payload = {
            "chat_id": telegram_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": buttons},
        }

        return await self._tg_send(bot_token, "sendMessage", payload)

    # ── Telegram API helper ──────────────────────────

    async def _tg_send(self, token: str, method: str, payload: dict) -> bool:
        url = f"{TELEGRAM_API}/bot{token}/{method}"
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    return True
                body = resp.text[:300].lower()
                if any(err in body for err in _SILENT_ERRORS):
                    logger.debug("TG %s → %s (expected): %s", method, resp.status_code, body)
                else:
                    logger.warning("TG %s → %s: %s", method, resp.status_code, resp.text[:300])
        except Exception as e:
            logger.warning("TG %s failed: %s", method, e)
        return False


def _md_escape(text: str) -> str:
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


if __name__ == "__main__":
    logging.basicConfig(
        level="INFO",
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    asyncio.run(ExpiryNotifyWorker(interval_seconds=60).run())
