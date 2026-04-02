"""
UTR Group handler — monitors the UTR Verification Telegram group.

When the SMS forwarding app sends bank SMS to the group, this handler
picks up the message, forwards it to the backend for UTR extraction
and auto-matching against pending payment orders.
"""
from __future__ import annotations

import logging

import httpx
from aiogram import F, Router
from aiogram.types import Message

from telegram_gateway.http_client import BACKEND_URL

logger = logging.getLogger(__name__)
utr_group_router = Router(name="utr_group")


@utr_group_router.message(F.chat.type.in_({"group", "supergroup"}))
async def handle_group_message(message: Message) -> None:
    """
    Catches ALL messages in groups the bot is in.
    Extracts text content (including from forwarded messages)
    and forwards to backend for UTR matching.
    """
    chat_id = message.chat.id
    from_user = message.from_user
    from_name = (from_user.full_name if from_user else "unknown")
    from_id = (from_user.id if from_user else 0)
    is_bot = (from_user.is_bot if from_user else False)

    # Log EVERY group message for debugging
    logger.info(
        "GROUP MSG chat=%d from=%s(id=%d,bot=%s) text=%s caption=%s",
        chat_id, from_name, from_id, is_bot,
        repr((message.text or "")[:80]),
        repr((message.caption or "")[:80]),
    )

    # Extract text from any message type (plain, forwarded, caption)
    text = message.text or message.caption or ""
    text = text.strip()

    if not text or text.startswith("/"):
        return

    if len(text) < 6:
        return

    sender_name = from_name or "TG_GROUP"

    logger.info("UTR group msg in chat %d from %s: %s", chat_id, sender_name, text[:100])

    # Forward to backend for UTR extraction and matching
    try:
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=15) as client:
            resp = await client.post(
                "/payments/group-utr",
                json={
                    "chat_id": chat_id,
                    "message_text": text,
                    "sender_name": sender_name,
                    "message_id": message.message_id,
                },
            )
            if resp.status_code == 200:
                data = resp.json()
                utr = data.get("utr_extracted")
                matched = data.get("matched_order_id")
                matched_tg_id = data.get("matched_telegram_id")
                recheck_tg_ids = data.get("recheck_telegram_ids") or []
                if utr:
                    logger.info(
                        "UTR extracted: %s (matched_order=%s)", utr, matched,
                    )

                # Collect all unique telegram_ids to notify
                notify_ids: set[int] = set()
                if matched_tg_id:
                    notify_ids.add(int(matched_tg_id))
                for tg_id in recheck_tg_ids:
                    notify_ids.add(int(tg_id))

                for tg_id in notify_ids:
                    try:
                        await message.bot.send_message(
                            tg_id,
                            "✅ **Payment Verified!**\n\n"
                            "Your payment has been confirmed and access has been granted.",
                            parse_mode="Markdown",
                        )
                        logger.info("Notified user %s of auto-verified payment", tg_id)
                    except Exception:
                        logger.warning("Could not notify user %s", tg_id)
            elif resp.status_code == 403:
                logger.debug("Chat %d not authorized as UTR group", chat_id)
            else:
                logger.warning(
                    "Group UTR endpoint returned %d: %s",
                    resp.status_code,
                    resp.text[:200],
                )
    except Exception:
        logger.exception("Failed to forward group message for UTR extraction")
