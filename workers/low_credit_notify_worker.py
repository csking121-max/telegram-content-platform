"""
Low Credit Notification Worker — sends Telegram messages to users whose
credit balance drops below configurable thresholds.

Reads from ``queue:low_credit_notify`` in Redis.
Each job: {user_id, new_balance}.

Uses Redis flags ``low_credit_notified:{user_id}:{threshold}`` to ensure
each user is notified at most once per threshold crossing.  Flags are cleared
when credits are added back (see credit_engine.add).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import sys

import httpx

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from decimal import Decimal
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings as app_settings
from backend.database import AsyncSessionLocal
from backend.models.bot import Bot
from backend.models.credit_package import CreditPackage
from backend.models.membership_plan import MembershipPlan
from backend.models.user import User
from backend.redis_client import RedisClient
from backend.services.platform_settings_service import PlatformSettingsService

logger = logging.getLogger(__name__)

QUEUE = "queue:low_credit_notify"
POLL_INTERVAL = app_settings.WORKER_POLL_INTERVAL
TELEGRAM_API = "https://api.telegram.org"

# Known Telegram errors that should be silently skipped.
_SILENT_ERRORS = frozenset({
    "chat not found",
    "bot was blocked by the user",
    "user is deactivated",
    "bot can't initiate conversation with a user",
    "have no rights to send a message",
})


class LowCreditNotifyWorker:
    """Processes low-credit notification jobs from Redis queue."""

    async def run(self) -> None:
        rc = RedisClient.get()
        logger.info("LowCreditNotifyWorker listening on %s", QUEUE)

        while True:
            raw = rc.client.lpop(QUEUE)
            if not raw:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            try:
                job = json.loads(raw)
                user_id = job["user_id"]
                new_balance = job["new_balance"]

                async with AsyncSessionLocal() as db:
                    await self._process(db, rc, user_id, new_balance)

            except Exception:
                logger.exception("LowCreditNotifyWorker error processing job")

    async def _process(
        self, db: AsyncSession, rc: RedisClient, user_id: int, new_balance: int
    ) -> None:
        svc = PlatformSettingsService(db)

        # Check if feature is enabled
        enabled = (await svc.get("low_credit_warning_enabled", "true")).lower() in (
            "true", "1", "yes",
        )
        if not enabled:
            return

        # Parse thresholds (e.g. "10,5,2")
        raw_thresholds = await svc.get("low_credit_thresholds", "10,5,2")
        thresholds = []
        for part in raw_thresholds.split(","):
            part = part.strip()
            if part.isdigit():
                thresholds.append(int(part))
        thresholds.sort(reverse=True)  # highest first

        if not thresholds:
            return

        # Find the highest threshold that applies
        triggered_threshold = None
        for t in thresholds:
            if new_balance <= t:
                triggered_threshold = t
                break  # highest match wins

        if triggered_threshold is None:
            return

        # Check Redis dedup: already notified for this threshold?
        dedup_key = f"low_credit_notified:{user_id}:{triggered_threshold}"
        # Set with NX — only succeeds if not already set. TTL 24h.
        if rc.client.set(dedup_key, "1", nx=True, ex=86400) is None:
            return  # Already notified

        # Also mark all lower thresholds as notified so we don't double-notify
        for t in thresholds:
            if t >= triggered_threshold:
                continue
            lower_key = f"low_credit_notified:{user_id}:{t}"
            rc.client.set(lower_key, "1", nx=True, ex=86400)

        # Resolve telegram_id
        user_result = await db.execute(
            select(User.telegram_id).where(User.id == user_id)
        )
        telegram_id = user_result.scalar_one_or_none()
        if not telegram_id:
            return

        # Get bot token
        bot_result = await db.execute(
            select(Bot).where(Bot.status == "active").limit(1)
        )
        bot = bot_result.scalar_one_or_none()
        if not bot:
            logger.warning("No active bot — cannot send low-credit notification")
            return

        # Get credit packages
        pkg_result = await db.execute(
            select(CreditPackage)
            .where(CreditPackage.is_active == True)
            .order_by(CreditPackage.sort_order, CreditPackage.credits)
        )
        packages = list(pkg_result.scalars().all())

        # Get membership plans
        plan_result = await db.execute(
            select(MembershipPlan)
            .where(MembershipPlan.is_active == True)
            .order_by(MembershipPlan.sort_order, MembershipPlan.tier_level)
        )
        plans = list(plan_result.scalars().all())

        # Get price per credit
        credits_per_inr = await svc.get("credits_per_inr", "1")
        try:
            price_per_credit = Decimal(credits_per_inr)
        except Exception:
            price_per_credit = Decimal("1")

        # Build message
        text = (
            f"\u26a0\ufe0f *Low Credits Warning*\n"
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
            f"Your credit balance is *{new_balance}* credits.\n"
            f"Price per credit: *\u20b9{price_per_credit}*\n\n"
        )

        if packages:
            text += "\U0001fa99 *Credit Packs Available:*\n"
            for pkg in packages[:5]:
                ppc = pkg.price_inr / pkg.credits if pkg.credits > 0 else pkg.price_inr
                text += f"  \u2022 {_md_escape(pkg.display_name)} — {pkg.credits} credits for \u20b9{pkg.price_inr} (\u20b9{ppc:.2f}/credit)\n"
            text += "\n"

        if plans:
            text += "\U0001f451 *Membership Plans:*\n"
            for plan in plans[:5]:
                text += f"  \u2022 {_md_escape(plan.display_name)} — \u20b9{plan.price_inr}"
                if plan.duration_days:
                    text += f" for {plan.duration_days} days"
                text += "\n"
            text += "\n"

        text += (
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            f"_Top up your credits to keep enjoying content! \u2b07\ufe0f_"
        )

        # Build inline keyboard
        buttons = []
        if packages:
            for pkg in packages[:3]:
                buttons.append([{
                    "text": f"\U0001fa99 {pkg.display_name} — {pkg.credits} credits \u20b9{pkg.price_inr}",
                    "callback_data": f"buy_credits:{pkg.id}",
                }])
        if plans:
            buttons.append([{
                "text": "\U0001f451 View Membership Plans",
                "callback_data": "menu:plans",
            }])
        buttons.append([{
            "text": "\U0001f4b3 Buy Custom Credits",
            "callback_data": "menu:buy_credits",
        }])

        payload = {
            "chat_id": telegram_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": buttons},
        }

        await self._tg_send(bot.bot_token, "sendMessage", payload)
        logger.info(
            "Sent low-credit warning to user=%d (balance=%d, threshold=%d)",
            user_id, new_balance, triggered_threshold,
        )

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
    asyncio.run(LowCreditNotifyWorker().run())
