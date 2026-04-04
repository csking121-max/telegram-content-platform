"""
Admin Notifications — manual triggers for notification workflows.
"""
from __future__ import annotations

import logging
from decimal import Decimal

import httpx
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.models.bot import Bot
from backend.models.credit import Credit
from backend.models.credit_package import CreditPackage
from backend.models.membership_plan import MembershipPlan
from backend.models.user import User
from backend.services.platform_settings_service import PlatformSettingsService

logger = logging.getLogger(__name__)
router = APIRouter()

TELEGRAM_API = "https://api.telegram.org"

_SILENT_ERRORS = frozenset({
    "chat not found",
    "bot was blocked by the user",
    "user is deactivated",
    "bot can't initiate conversation with a user",
    "have no rights to send a message",
})


@router.post("/trigger-low-credit")
async def trigger_low_credit_notifications(
    db: AsyncSession = Depends(get_db),
):
    """
    Manually trigger low-credit notifications for ALL users whose balance
    is at or below the configured thresholds.  Ignores Redis dedup flags
    so every qualifying user gets a message (useful for testing).
    """
    svc = PlatformSettingsService(db)

    # Parse thresholds
    raw_thresholds = await svc.get("low_credit_thresholds", "10,5,2")
    thresholds = sorted(
        [int(p.strip()) for p in raw_thresholds.split(",") if p.strip().isdigit()],
        reverse=True,
    )
    if not thresholds:
        return {"detail": "No thresholds configured", "sent": 0, "failed": 0}

    max_threshold = thresholds[0]  # highest threshold = widest net

    # Get bot token
    bot_result = await db.execute(
        select(Bot).where(Bot.status == "active").limit(1)
    )
    bot = bot_result.scalar_one_or_none()
    if not bot:
        return {"detail": "No active bot found", "sent": 0, "failed": 0}

    # Get all users with balance <= max threshold
    result = await db.execute(
        select(Credit.user_id, Credit.balance).where(Credit.balance <= max_threshold)
    )
    low_credit_users = result.all()

    if not low_credit_users:
        return {"detail": "No users below threshold", "sent": 0, "failed": 0}

    # Preload telegram_ids
    user_ids = [row.user_id for row in low_credit_users]
    user_result = await db.execute(
        select(User.id, User.telegram_id).where(User.id.in_(user_ids))
    )
    tg_map = {row.id: row.telegram_id for row in user_result.all()}

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

    # Price per credit
    credits_per_inr = await svc.get("credits_per_inr", "1")
    try:
        price_per_credit = Decimal(credits_per_inr)
    except Exception:
        price_per_credit = Decimal("1")

    sent = 0
    failed = 0

    import asyncio

    for user_id, balance in low_credit_users:
        telegram_id = tg_map.get(user_id)
        if not telegram_id:
            continue

        text = _build_message(balance, price_per_credit, packages, plans)
        buttons = _build_keyboard(packages)

        payload = {
            "chat_id": telegram_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": buttons},
        }

        ok = await _tg_send(bot.bot_token, "sendMessage", payload)
        if ok:
            sent += 1
        else:
            failed += 1

        # Rate limit: sleep every 25 messages
        if (sent + failed) % 25 == 0:
            await asyncio.sleep(1)

    logger.info(
        "Manual low-credit trigger: sent=%d failed=%d (threshold<=%d, users=%d)",
        sent, failed, max_threshold, len(low_credit_users),
    )
    return {
        "detail": f"Sent to {sent} users ({failed} failed) with balance ≤ {max_threshold}",
        "sent": sent,
        "failed": failed,
        "total_qualifying": len(low_credit_users),
    }


def _build_message(
    balance: int,
    price_per_credit: Decimal,
    packages: list,
    plans: list,
) -> str:
    text = (
        "\u26a0\ufe0f *Low Credits Warning*\n"
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
        f"Your credit balance is *{balance}* credits.\n"
        f"Price per credit: *\u20b9{price_per_credit}*\n\n"
    )

    if packages:
        text += "\U0001fa99 *Credit Packs Available:*\n"
        for pkg in packages[:5]:
            ppc = pkg.price_inr / pkg.credits if pkg.credits > 0 else pkg.price_inr
            text += f"  \u2022 {_md_escape(pkg.display_name)} \u2014 {pkg.credits} credits for \u20b9{pkg.price_inr} (\u20b9{ppc:.2f}/credit)\n"
        text += "\n"

    if plans:
        text += "\U0001f451 *Membership Plans:*\n"
        for plan in plans[:5]:
            text += f"  \u2022 {_md_escape(plan.display_name)} \u2014 \u20b9{plan.price_inr}"
            if plan.duration_days:
                text += f" for {plan.duration_days} days"
            text += "\n"
        text += "\n"

    text += (
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        "_Top up your credits to keep enjoying content! \u2b07\ufe0f_"
    )
    return text


def _build_keyboard(packages: list) -> list:
    buttons = []
    if packages:
        for pkg in packages[:3]:
            buttons.append([{
                "text": f"\U0001fa99 {pkg.display_name} \u2014 {pkg.credits} credits \u20b9{pkg.price_inr}",
                "callback_data": f"buy_credits:{pkg.id}",
            }])
    buttons.append([{
        "text": "\U0001f451 View Membership Plans",
        "callback_data": "menu:plans",
    }])
    buttons.append([{
        "text": "\U0001f4b3 Buy Custom Credits",
        "callback_data": "menu:buy_credits",
    }])
    return buttons


def _md_escape(text: str) -> str:
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text


async def _tg_send(token: str, method: str, payload: dict) -> bool:
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
