"""
SMS Webhook endpoint — receives forwarded SMS from Android SMS forwarder app.

Three methods:
 1. POST /sms/forward   — direct HTTP webhook with sender + body + api_key
 2. POST /sms/tg-proxy  — Telegram-compatible sendMessage proxy
 3. POST /sms/webhook   — universal webhook for SMS Forwarder apps (URL mode)

All paths: store → extract UTR → auto-match → auto-grant → notify user.
"""

from __future__ import annotations

import logging
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.dependencies import get_db
from backend.models.bot import Bot
from backend.models.payment_order import PaymentOrder
from backend.models.user import User
from backend.schemas.sms_log import SmsForward, SmsLogRead
from backend.services.payment_order_service import PaymentOrderService
from backend.services.platform_settings_service import PlatformSettingsService
from backend.services.sms_verification_service import SmsVerificationService

logger = logging.getLogger(__name__)
router = APIRouter()


# ── shared helper: process SMS → auto-match → auto-grant ────────────

async def _process_and_match(
    db: AsyncSession,
    sender: str,
    body: str,
    source_chat_id: Optional[int] = None,
) -> dict:
    """
    Core SMS processing pipeline.
    Returns dict with keys: sms, matched_telegram_id, verified
    """
    sms_svc = SmsVerificationService(db)
    sms = await sms_svc.process_sms(
        sender=sender,
        body=body,
        source_chat_id=source_chat_id,
    )
    await db.flush()

    # Also recheck any pending orders that submitted a UTR earlier
    order_svc = PaymentOrderService(db)
    _verified_count, recheck_user_ids = await order_svc.recheck_pending_orders()
    await db.flush()

    # Check if this SMS (or recheck) auto-matched an order
    matched_telegram_id: Optional[int] = None
    if sms.matched and sms.matched_order_id:
        result = await db.execute(
            select(PaymentOrder).where(PaymentOrder.id == sms.matched_order_id)
        )
        order = result.scalar_one_or_none()
        if order and order.status in ("pending", "utr_submitted"):
            await order_svc._grant_access(order.order_ref, order.user_id)
            user_result = await db.execute(
                select(User.telegram_id).where(User.id == order.user_id)
            )
            matched_telegram_id = user_result.scalar_one_or_none()

    await db.commit()

    logger.info(
        "SMS processed: utr=%s matched_order=%s notify_user=%s",
        sms.utr_extracted, sms.matched_order_id, matched_telegram_id,
    )

    # Collect all telegram_ids to notify (direct match + recheck matches)
    recheck_telegram_ids: list[int] = []
    if recheck_user_ids:
        tg_result = await db.execute(
            select(User.telegram_id).where(User.id.in_(recheck_user_ids))
        )
        recheck_telegram_ids = [r for r in tg_result.scalars().all() if r]

    return {
        "sms": sms,
        "matched_telegram_id": matched_telegram_id,
        "recheck_telegram_ids": recheck_telegram_ids,
    }


async def _notify_user_via_bot(db: AsyncSession, telegram_id: int) -> None:
    """Send payment verification notification to the user via the bot."""
    result = await db.execute(select(Bot).where(Bot.status == "active").limit(1))
    bot = result.scalar_one_or_none()
    if not bot:
        logger.warning("No active bot to send notification to user %s", telegram_id)
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.post(
                f"https://api.telegram.org/bot{bot.bot_token}/sendMessage",
                json={
                    "chat_id": telegram_id,
                    "text": "✅ *Payment Verified!*\n\nYour payment has been confirmed and access has been granted.",
                    "parse_mode": "Markdown",
                },
            )
            if resp.status_code == 200:
                logger.info("Notified user %s of verified payment", telegram_id)
            else:
                logger.warning("Failed to notify user %s: %s", telegram_id, resp.text[:200])
    except Exception:
        logger.exception("Error notifying user %s", telegram_id)


async def _forward_to_utr_group(db: AsyncSession, text: str, sender: str) -> None:
    """Forward SMS text to the UTR verification group for admin visibility."""
    settings_svc = PlatformSettingsService(db)
    group_id = await settings_svc.get("utr_group_chat_id", "")
    if not group_id:
        return

    result = await db.execute(select(Bot).where(Bot.status == "active").limit(1))
    bot = result.scalar_one_or_none()
    if not bot:
        return

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(
                f"https://api.telegram.org/bot{bot.bot_token}/sendMessage",
                json={
                    "chat_id": int(group_id),
                    "text": f"📩 SMS from {sender}:\n\n{text}",
                },
            )
    except Exception:
        logger.debug("Could not forward SMS to UTR group")


# ── Endpoint 1: Direct HTTP webhook ─────────────────────────────────

@router.post("/forward", response_model=SmsLogRead)
async def receive_sms(
    body: SmsForward,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive a forwarded SMS from the Android SMS forwarder app via HTTP.
    """
    expected_key = getattr(settings, "SMS_FORWARD_API_KEY", "") or settings.SECRET_KEY
    if body.api_key != expected_key:
        raise HTTPException(403, "Invalid API key")

    result = await _process_and_match(db, sender=body.sender, body=body.body)
    sms = result["sms"]

    if result["matched_telegram_id"]:
        await _notify_user_via_bot(db, result["matched_telegram_id"])
    for tg_id in result.get("recheck_telegram_ids", []):
        if tg_id != result.get("matched_telegram_id"):
            await _notify_user_via_bot(db, tg_id)

    return sms


# ── Endpoint 2: Telegram-compatible sendMessage proxy ────────────────

class TgProxyPayload(BaseModel):
    """Accepts the same fields as Telegram's sendMessage API."""
    chat_id: Optional[int | str] = None
    text: str
    parse_mode: Optional[str] = None


@router.post("/tg-proxy")
async def telegram_proxy(
    body: TgProxyPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Telegram-compatible proxy endpoint for SMS Forwarder apps.

    Instead of calling:
      https://api.telegram.org/bot<TOKEN>/sendMessage

    Configure the app to call:
      http://<SERVER>:8000/sms/tg-proxy

    This endpoint:
     1. Stores the SMS in the database
     2. Extracts UTR + amount and auto-matches pending orders
     3. Grants access if matched
     4. Notifies the user via bot
     5. Forwards the message to the UTR group for admin visibility
    """
    text = body.text.strip()
    if not text:
        raise HTTPException(400, "Empty text")

    # Get UTR group chat_id for source tracking
    settings_svc = PlatformSettingsService(db)
    group_id_str = await settings_svc.get("utr_group_chat_id", "")
    source_chat_id = int(group_id_str) if group_id_str else None

    result = await _process_and_match(
        db,
        sender="SMS_FORWARDER",
        body=text,
        source_chat_id=source_chat_id,
    )

    if result["matched_telegram_id"]:
        await _notify_user_via_bot(db, result["matched_telegram_id"])
    for tg_id in result.get("recheck_telegram_ids", []):
        if tg_id != result.get("matched_telegram_id"):
            await _notify_user_via_bot(db, tg_id)

    # Forward to UTR group for admin visibility
    await _forward_to_utr_group(db, text, "SMS Forwarder")

    sms = result["sms"]
    # Return Telegram-compatible response so the SMS Forwarder doesn't error
    return {
        "ok": True,
        "result": {
            "message_id": sms.id,
            "text": text,
            "chat": {"id": source_chat_id or 0},
        },
    }


# ── Endpoint 3: Universal SMS Forwarder Webhook ─────────────────────

@router.post("/webhook")
async def sms_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Universal webhook for SMS Forwarder apps in URL/Webhook mode.

    Accepts JSON or form data — handles field names from popular apps:
      - Text:   "text", "body", "message", "smsBody", "msg", "content"
      - Sender: "from", "sender", "number", "address", "phone", "sim"

    Configure your SMS Forwarder app URL to:
      http://<SERVER_IP>:8000/sms/webhook
    """
    # Parse body — support JSON, form data, and raw text
    content_type = request.headers.get("content-type", "")
    body: dict = {}

    if "application/json" in content_type:
        body = await request.json()
    elif "form" in content_type:
        form = await request.form()
        body = dict(form)
    else:
        # Try JSON first, fall back to treating raw body as SMS text
        raw = await request.body()
        try:
            import json
            body = json.loads(raw)
        except Exception:
            body = {"text": raw.decode("utf-8", errors="replace")}

    logger.info("SMS webhook raw payload: %s", {k: str(v)[:100] for k, v in body.items()})

    # Extract text from any common field name
    text = (
        body.get("text")
        or body.get("body")
        or body.get("message")
        or body.get("smsBody")
        or body.get("msg")
        or body.get("content")
        or ""
    )
    if isinstance(text, str):
        text = text.strip()
    else:
        text = str(text).strip()

    if not text:
        raise HTTPException(400, "No SMS text found in payload")

    if len(text) > 1600:
        raise HTTPException(400, "SMS body too long")

    # Extract sender from any common field name
    sender = (
        body.get("from")
        or body.get("sender")
        or body.get("number")
        or body.get("address")
        or body.get("phone")
        or body.get("sim")
        or "SMS_FORWARDER"
    )

    logger.info("SMS webhook received: sender=%s text=%s", sender, text[:100])

    settings_svc = PlatformSettingsService(db)
    group_id_str = await settings_svc.get("utr_group_chat_id", "")
    source_chat_id = int(group_id_str) if group_id_str else None

    result = await _process_and_match(
        db,
        sender=str(sender),
        body=text,
        source_chat_id=source_chat_id,
    )

    if result["matched_telegram_id"]:
        await _notify_user_via_bot(db, result["matched_telegram_id"])
    for tg_id in result.get("recheck_telegram_ids", []):
        if tg_id != result.get("matched_telegram_id"):
            await _notify_user_via_bot(db, tg_id)

    # Forward to UTR group for admin visibility
    await _forward_to_utr_group(db, text, str(sender))

    return {"status": "ok", "utr": result["sms"].utr_extracted, "matched": result["sms"].matched}
