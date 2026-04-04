"""
Payment handler -- lets users browse plans, generate UPI QR, and submit UTR.

Commands:
  /plans or /buy  -> show available membership plans (inline keyboard)
  Callback: plan:<id>  -> generate QR code for that plan and send to user
  /pay <UTR>      -> submit UTR for an active order (also accepts plain text UTR)
  /mystatus       -> check current order status
"""

from __future__ import annotations

import base64
import logging

from aiogram import Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from telegram_gateway.http_client import api_get, api_post
from telegram_gateway.redis_state import (
    set_pending_order, get_pending_order, clear_pending_order,
    set_awaiting_utr, is_awaiting_utr, clear_awaiting_utr,
    set_awaiting_custom_credits, is_awaiting_custom_credits,
    clear_awaiting_custom_credits,
)

logger = logging.getLogger(__name__)
payment_router = Router(name="payment")

# In-memory fallback cache: telegram_id -> order_ref (used when backend is unreachable)
_user_pending_orders: dict[int, str] = {}


async def _safe_answer(callback: CallbackQuery, text: str = "", **kwargs) -> None:
    """Answer a callback query, silently ignoring expired-query errors."""
    try:
        await callback.answer(text, **kwargs)
    except TelegramBadRequest as e:
        if "query is too old" in str(e) or "query id is invalid" in str(e).lower():
            logger.debug("Stale callback query ignored: %s", e)
        else:
            raise


def _md_escape(text: str) -> str:
    """Escape Telegram legacy Markdown (v1) special characters in dynamic strings."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text

# -- Helpers ----------------------------------------------------------


def _build_enter_utr_kb(order_ref: str) -> InlineKeyboardMarkup:
    """Build keyboard with Enter UTR + Check Status buttons."""
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Enter UTR", callback_data=f"enter_utr:{order_ref}")],
        [InlineKeyboardButton(text="Check Status", callback_data=f"check_order:{order_ref}")],
    ])


# -- /plans  or  /buy -------------------------------------------------

@payment_router.message(Command("plans"))
@payment_router.message(Command("buy"))
async def show_plans(message: Message) -> None:
    user = message.from_user
    if not user:
        return

    plans = await api_get("/payments/plans")
    if not plans:
        await message.answer("No plans are available right now. Try again later.")
        return

    # Fetch user's max tier for tier markers
    profile = await api_get(f"/access/profile/{user.id}")
    user_max_tier = profile.get("max_tier_level", 0) if profile else 0

    tier_icons = {0: "\u25ab\ufe0f", 1: "\U0001f7e2", 2: "\U0001f535", 3: "\U0001f7e1", 4: "\u2b50", 5: "\U0001f451"}

    text = (
        "\u2b50 **MEMBERSHIP PLANS** \u2b50\n"
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
        "Choose a plan to view details and purchase:\n\n"
    )
    buttons: list[list[InlineKeyboardButton]] = []

    for p in plans:
        tier = p.get("tier_level", 0)
        icon = tier_icons.get(tier, "\u2b50")
        pname = p.get("display_name") or p["name"]
        duration_parts = []
        if p.get("duration_days"):
            dd = p["duration_days"]
            duration_parts.append(f"{dd} Day{'s' if dd > 1 else ''}")
        if p.get("duration_hours"):
            hh = p["duration_hours"]
            duration_parts.append(f"{hh} Hour{'s' if hh > 1 else ''}")
        duration = " ".join(duration_parts) or "Unlimited"
        price_txt = f"\u20b9{p['price_inr']}"
        if p.get("credit_price") and p["credit_price"] > 0:
            price_txt += f" / {p['credit_price']} Credits"

        # Tier marker
        tier_marker = ""
        if tier > 0 and user_max_tier >= tier:
            tier_marker = " \u2705"

        text += (
            f"{icon} **{_md_escape(pname)}**{tier_marker}\n"
            f"    \u23f3 {_md_escape(duration)} \u2022 \U0001f4b0 {price_txt}\n\n"
        )

        btn_label = f"{icon} {pname}  \u2014  {price_txt}"
        if tier > 0 and user_max_tier >= tier:
            btn_label = f"\u2705 {pname}  (Active)"

        buttons.append([InlineKeyboardButton(
            text=btn_label,
            callback_data=f"planview:{p['id']}",
        )])

    text += "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n_Tap a plan to view details & buy_"

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


# -- Callback: buy plan with credits -----------------------------------

@payment_router.callback_query(lambda c: c.data and c.data.startswith("plan_credits:"))
async def handle_plan_credits_purchase(callback: CallbackQuery) -> None:
    user = callback.from_user
    if not user or not callback.data:
        return

    plan_id = int(callback.data.split(":")[1])
    await callback.answer("Processing credit purchase...")

    result = await api_post("/payments/buy-with-credits", {
        "telegram_id": user.id,
        "plan_id": plan_id,
    })

    if not result:
        await callback.message.answer("Failed to process credit purchase. Please try again.")  # type: ignore
        return

    if result.get("_error"):
        await callback.message.answer(f"Error: {result.get('message', 'Purchase failed')}")  # type: ignore
        return

    plan_name = result.get("plan_name", "Plan")
    credits_deducted = result.get("credits_deducted", 0)
    bonus = result.get("bonus_credits", 0)
    expiry = result.get("expiry_at", "")
    remaining = result.get("remaining_balance", "")

    # Format expiry nicely
    expiry_display = ""
    if expiry:
        try:
            from datetime import datetime as _dt
            exp_dt = _dt.fromisoformat(expiry)
            expiry_display = exp_dt.strftime("%d %b %Y, %I:%M %p")
        except Exception:
            expiry_display = expiry

    badge_map = {"free": "\U0001f7e2", "credits": "\U0001fa99", "vip": "\u2b50", "premium": "\U0001f451", "daily pass": "\U0001f535"}
    access_t = result.get("membership_type", result.get("access_type", "")).lower()
    badge = badge_map.get(access_t, "\U0001f3c6")

    text = (
        f"\U0001f389 **Welcome to the {_md_escape(plan_name)} Club!** {badge}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
        f"{badge} You're now a **{_md_escape(plan_name)}** member!\n\n"
        f"\U0001fa99 Credits deducted: **{credits_deducted}**\n"
    )
    if remaining != "":
        text += f"\U0001f4b0 Credit balance: **{remaining}**\n"
    if bonus > 0:
        text += f"\U0001f381 Bonus credits: **+{bonus}**\n"
    if expiry_display:
        text += f"\u23f3 Expires: {_md_escape(expiry_display)}\n"
    text += (
        f"\n\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
        f"_Enjoy your exclusive content! \U0001f680_"
    )

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="\u25c0\ufe0f Main Menu", callback_data="menu:main")],
    ])
    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")  # type: ignore


# -- Callback: plan selection -> generate QR ---------------------------

@payment_router.callback_query(lambda c: c.data and c.data.startswith("plan:"))
async def handle_plan_selection(callback: CallbackQuery) -> None:
    user = callback.from_user
    if not user or not callback.data:
        return

    plan_id = int(callback.data.split(":")[1])
    await callback.answer("Generating payment QR...")

    result = await api_post("/payments/create-order", {
        "telegram_id": user.id,
        "plan_id": plan_id,
    })

    if not result:
        await callback.message.answer("Failed to create payment order. Please try again.")  # type: ignore
        return

    order_ref = result["order_ref"]
    amount = result["amount"]
    plan_name = result.get("plan_name", "Plan")
    upi_link = result.get("upi_link", "")
    expires_at = result.get("expires_at", "")
    qr_data_url: str = result.get("qr_data_url", "")

    set_pending_order(user.id, order_ref)

    # Format expiry as human-readable
    expires_display = expires_at
    if expires_at:
        try:
            from datetime import datetime as _dt
            exp_dt = _dt.fromisoformat(expires_at)
            expires_display = exp_dt.strftime("%d %b %Y, %I:%M %p")
        except Exception:
            pass

    text = (
        f"**Payment Order Created**\n\n"
        f"Plan: **{_md_escape(plan_name)}**\n"
        f"Amount: **Rs.{amount}**\n"
        f"Order: `{order_ref}`\n\n"
        f"**How to pay:**\n"
        f"1. Scan the QR code below with any UPI app\n"
        f"2. Complete the payment\n"
        f"3. Tap **Enter UTR** below and send your reference number\n\n"
        f"This order expires at: {_md_escape(expires_display)}\n"
    )

    if upi_link:
        text += f"\nOr tap to pay: [Open UPI App]({upi_link})"

    kb = _build_enter_utr_kb(order_ref)

    if qr_data_url and qr_data_url.startswith("data:image"):
        try:
            b64part = qr_data_url.split(",", 1)[1]
            img_bytes = base64.b64decode(b64part)
            photo = BufferedInputFile(img_bytes, filename="payment_qr.png")
            await callback.message.answer_photo(  # type: ignore
                photo=photo,
                caption=text,
                reply_markup=kb,
                parse_mode="Markdown",
            )
            return
        except Exception:
            logger.exception("Failed to send QR image")

    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")  # type: ignore


# -- Callback: "Enter UTR" button -> ask user to type UTR -------------

@payment_router.callback_query(lambda c: c.data and c.data.startswith("enter_utr:"))
async def handle_enter_utr(callback: CallbackQuery) -> None:
    user = callback.from_user
    if not user or not callback.data:
        return

    order_ref = callback.data.split(":", 1)[1]
    set_pending_order(user.id, order_ref)
    set_awaiting_utr(user.id)
    await _safe_answer(callback)

    await callback.message.answer(  # type: ignore
        "**Enter your UTR / Transaction Reference Number**\n\n"
        "Just type the UTR number and send it (no commands needed).\n"
        "You can find it in your UPI app's transaction history.",
        parse_mode="Markdown",
    )


# -- Callback: "Check Status" button ----------------------------------

@payment_router.callback_query(lambda c: c.data and c.data.startswith("check_order:"))
async def handle_check_order(callback: CallbackQuery) -> None:
    user = callback.from_user
    if not user or not callback.data:
        return

    order_ref = callback.data.split(":", 1)[1]
    await _safe_answer(callback)

    result = await api_get(f"/payments/order/{order_ref}")
    if not result:
        await callback.message.answer("Could not retrieve order status.")  # type: ignore
        return

    status = result.get("status", "unknown")
    status_emoji = {
        "pending": "PENDING",
        "utr_submitted": "UTR SUBMITTED",
        "verified": "VERIFIED",
        "failed": "FAILED",
        "expired": "EXPIRED",
    }

    text = (
        f"**Order Status: {status_emoji.get(status, status.upper())}**\n\n"
        f"Order: `{order_ref}`\n"
        f"Amount: Rs.{result.get('amount', '?')}\n"
    )

    if result.get("utr_submitted"):
        text += f"UTR: `{result['utr_submitted']}`\n"

    kb = None
    if status == "verified":
        clear_pending_order(user.id)
        text += "\n\u2705 Payment verified! Your access has been granted."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u25c0\ufe0f Main Menu", callback_data="menu:main")],
        ])
    elif status in ("expired", "failed"):
        clear_pending_order(user.id)
        text += "\nThis order has " + ("expired." if status == "expired" else "failed.")
        text += "\nTap **Retry Payment** to try again with the same order."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f504 Retry Payment", callback_data=f"retry_pay:{order_ref}")],
            [InlineKeyboardButton(text="\U0001f195 New Order", callback_data="menu:plans")],
        ])
    elif status == "pending":
        text += "\nOrder is waiting for payment. Complete the UPI payment and submit your UTR."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="Enter UTR", callback_data=f"enter_utr:{order_ref}")],
            [InlineKeyboardButton(text="\U0001f504 Refresh", callback_data=f"check_order:{order_ref}")],
            [InlineKeyboardButton(text="\u25c0\ufe0f Main Menu", callback_data="menu:main")],
        ])
    elif status == "utr_submitted":
        text += "\nUTR submitted \u2014 waiting for verification. This usually takes a few minutes."
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\U0001f504 Refresh", callback_data=f"check_order:{order_ref}")],
            [InlineKeyboardButton(text="\u25c0\ufe0f Main Menu", callback_data="menu:main")],
        ])
    else:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="\u25c0\ufe0f Main Menu", callback_data="menu:main")],
        ])

    await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")  # type: ignore


# -- Callback: "Retry Payment" button ---------------------------------

@payment_router.callback_query(lambda c: c.data and c.data.startswith("retry_pay:"))
async def handle_retry_payment(callback: CallbackQuery) -> None:
    user = callback.from_user
    if not user or not callback.data:
        return

    order_ref = callback.data.split(":", 1)[1]
    await _safe_answer(callback, "Retrying payment...")

    result = await api_post("/payments/retry-order", {
        "telegram_id": user.id,
        "order_ref": order_ref,
    })

    if not result or result.get("_error"):
        msg = result.get("message", "Cannot retry this order.") if result else "Retry failed."
        await callback.message.answer(  # type: ignore
            f"Cannot retry: {msg}\n\nUse /plans to create a new order.",
        )
        return

    new_expires = result.get("expires_at", "")
    amount = result.get("amount", "?")
    set_pending_order(user.id, order_ref)

    kb = _build_enter_utr_kb(order_ref)
    await callback.message.answer(  # type: ignore
        f"\U0001f504 **Order Reactivated!**\n\n"
        f"Order: `{order_ref}`\n"
        f"Amount: **Rs.{amount}**\n"
        f"New expiry: {new_expires}\n\n"
        f"Please complete payment and tap **Enter UTR** below.",
        reply_markup=kb,
        parse_mode="Markdown",
    )


# -- /pay <UTR> -- submit UTR (command fallback) ----------------------

@payment_router.message(Command("pay"))
async def submit_utr_command(message: Message) -> None:
    user = message.from_user
    if not user:
        return

    parts = (message.text or "").split(maxsplit=1)
    if len(parts) < 2 or not parts[1].strip():
        await message.answer(
            "Please provide your UTR/Reference number:\n"
            "Just type the UTR number and send it.\n\n"
            "Or tap **Enter UTR** on your payment QR message.",
            parse_mode="Markdown",
        )
        return

    utr = parts[1].strip()
    await _process_utr_submission(message, user.id, utr)


# -- Custom Credits: "Custom Amount" button callback ------------------

@payment_router.callback_query(lambda c: c.data == "custom_buy:enter")
async def handle_custom_buy_enter(callback: CallbackQuery) -> None:
    user = callback.from_user
    if not user:
        return
    await _safe_answer(callback)

    # Fetch limits from public settings
    min_credits = 10
    max_credits = 0
    try:
        settings_data = await api_get("/settings/public")
        if isinstance(settings_data, list):
            for s in settings_data:
                key = s.get("key")
                val = s.get("value") or ""
                if key == "custom_credits_min":
                    min_credits = int(val or "10")
                elif key == "custom_credits_max":
                    max_credits = int(val or "0")
    except Exception:
        pass

    set_awaiting_custom_credits(user.id)
    clear_awaiting_utr(user.id)  # can't be in both states

    limits_line = f"📦 Minimum: **{min_credits:,} credits**"
    if max_credits > 0:
        limits_line += f"  ·  Max: **{max_credits:,} credits**"

    await callback.message.answer(  # type: ignore
        f"💰 **Custom Credits Purchase**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{limits_line}\n\n"
        "Enter the number of credits to see the amount and purchase:",
        parse_mode="Markdown",
    )


# -- Custom Credits: plain-text amount input --------------------------

def _parse_custom_settings(settings_data: list | None) -> tuple[float, int, int]:
    """Extract price_per_credit, min, max from public settings list."""
    price_per_credit = 1.0
    min_credits = 10
    max_credits = 0
    if isinstance(settings_data, list):
        for s in settings_data:
            key = s.get("key")
            val = s.get("value") or ""
            if key == "credits_per_inr":
                price_per_credit = float(val or "1")
            elif key == "custom_credits_min":
                min_credits = int(val or "10")
            elif key == "custom_credits_max":
                max_credits = int(val or "0")
    if price_per_credit <= 0:
        price_per_credit = 1.0
    return price_per_credit, min_credits, max_credits


@payment_router.message(
    lambda m: (
        m.text
        and not m.text.startswith("/")
        and m.from_user
        and is_awaiting_custom_credits(m.from_user.id)
    )
)
async def handle_custom_credits_amount(message: Message) -> None:
    """User typed credit amount — show price summary + Confirm button."""
    user = message.from_user
    if not user or not message.text:
        return

    text = message.text.strip()
    try:
        credits = int(text)
    except ValueError:
        await message.answer(
            "⚠️ Please send a plain number.\nExample: `500`",
            parse_mode="Markdown",
        )
        return

    # Fetch settings to validate and calculate
    settings_data = None
    try:
        settings_data = await api_get("/settings/public")
    except Exception:
        pass
    price_per_credit, min_credits, max_credits = _parse_custom_settings(settings_data)

    if credits < min_credits:
        await message.answer(f"⚠️ Minimum order is **{min_credits:,} credits**. Please enter a higher amount.", parse_mode="Markdown")
        return
    if max_credits > 0 and credits > max_credits:
        await message.answer(f"⚠️ Maximum order is **{max_credits:,} credits**.", parse_mode="Markdown")
        return

    amount = round(credits * price_per_credit, 2)

    # Stay in awaiting state so they can re-enter a different number
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"✅ Confirm — Pay ₹{amount:g}", callback_data=f"custom_confirm:{credits}")],
        [InlineKeyboardButton(text="◀️ Cancel", callback_data="menu:main")],
    ])
    await message.answer(
        f"🪙 **{credits:,} credits** = **₹{amount:g}**\n\n"
        "Tap **Confirm** to generate payment QR,\n"
        "or type a different number to change.",
        reply_markup=kb,
        parse_mode="Markdown",
    )


# -- Custom Credits: Confirm button → create order & show QR ---------

@payment_router.callback_query(lambda c: c.data and c.data.startswith("custom_confirm:"))
async def handle_custom_confirm(callback: CallbackQuery) -> None:
    """User confirmed the custom credits amount. Create order and show QR."""
    user = callback.from_user
    if not user:
        return
    await _safe_answer(callback)
    clear_awaiting_custom_credits(user.id)

    try:
        credits = int(callback.data.split(":", 1)[1])  # type: ignore[union-attr]
    except (ValueError, IndexError):
        await callback.message.answer("Something went wrong. Please try again from /menu.")  # type: ignore
        return

    result = await api_post("/credit-packages/buy-custom", {
        "telegram_id": user.id,
        "credits_amount": credits,
    })

    if not result or result.get("_error"):
        err_msg = result.get("message", "Failed to create order.") if result else "Service unavailable."
        await callback.message.answer(f"❌ {err_msg}\n\nTry again or use /menu to go back.")  # type: ignore
        return

    order_ref = result["order_ref"]
    amount = result["amount"]
    upi_link = result.get("upi_link", "")
    qr_data_url: str = result.get("qr_data_url", "")
    expires_at = result.get("expires_at", "")

    set_pending_order(user.id, order_ref)

    caption = (
        f"💳 **Custom Credits Order**\n"
        f"━━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"🪙 Credits: **{credits:,}**\n"
        f"💵 Amount: **₹{amount:g}**\n"
        f"🔖 Order: `{order_ref}`\n\n"
        "**How to pay:**\n"
        "1. Scan the QR code with any UPI app\n"
        "2. Complete the payment\n"
        "3. Tap **Enter UTR** and send your reference number\n\n"
        f"⏳ Expires: {expires_at}"
    )
    if upi_link:
        caption += f"\n\nOr: [Open UPI App]({upi_link})"

    kb = _build_enter_utr_kb(order_ref)

    if qr_data_url and qr_data_url.startswith("data:image"):
        try:
            b64part = qr_data_url.split(",", 1)[1]
            img_bytes = base64.b64decode(b64part)
            photo = BufferedInputFile(img_bytes, filename="payment_qr.png")
            await callback.message.answer_photo(photo=photo, caption=caption, reply_markup=kb, parse_mode="Markdown")  # type: ignore
            return
        except Exception:
            logger.exception("Failed to send QR image for custom credits")

    await callback.message.answer(caption, reply_markup=kb, parse_mode="Markdown")  # type: ignore


# -- Plain text UTR handler (for users who tapped "Enter UTR") --------

@payment_router.message(
    lambda m: (
        m.text
        and not m.text.startswith("/")
        and m.from_user
        and is_awaiting_utr(m.from_user.id)
    )
)
async def handle_plain_utr(message: Message) -> None:
    """Catch plain text UTR from users who tapped Enter UTR."""
    user = message.from_user
    if not user or not message.text:
        return

    utr = message.text.strip()

    # Basic validation: UTR should be mostly digits, 10-22 chars
    clean = utr.replace(" ", "").replace("-", "")
    if not clean.isdigit() or len(clean) < 10 or len(clean) > 22:
        await message.answer(
            "That doesn't look like a valid UTR.\n"
            "UTR is usually a 12-digit number from your UPI transaction.\n"
            "Please check and send again.",
        )
        return

    success = await _process_utr_submission(message, user.id, clean)
    if success:
        clear_awaiting_utr(user.id)
    # On failure, keep user in awaiting_utr so they can re-type


async def _process_utr_submission(message: Message, telegram_id: int, utr: str) -> bool:
    """Common logic to submit UTR to backend and handle response.

    Returns True if UTR was accepted (verified or pending_verification),
    False if it failed and user should retry.
    """
    order_ref = get_pending_order(telegram_id)

    # If no order_ref in state, try to find one from backend
    if not order_ref:
        try:
            pending = await api_get(f"/payments/my-pending/{telegram_id}")
            if pending and isinstance(pending, list) and len(pending) > 0:
                # Use the most recent pending order
                order_ref = pending[0].get("order_ref")
                if order_ref:
                    set_pending_order(telegram_id, order_ref)
        except Exception:
            pass

    if not order_ref:
        await message.answer(
            "No pending payment order found.\n"
            "Use /plans to start a new purchase."
        )
        return False

    result = await api_post("/payments/submit-utr", {
        "telegram_id": telegram_id,
        "order_ref": order_ref,
        "utr": utr,
    })

    if not result:
        await message.answer(
            "⚠️ Failed to submit UTR. Backend may be unavailable.\n"
            "Please try again — just re-type your UTR number.",
        )
        return False

    # Handle error responses from backend (4xx errors)
    if result.get("_error"):
        err_msg = result.get("message", "Unknown error")
        await message.answer(
            f"⚠️ Error: {err_msg}\n"
            "You can re-type your UTR to try again.",
        )
        return False

    status = result.get("status", "unknown")

    if status == "verified":
        clear_pending_order(telegram_id)
        plan_name = result.get("plan_name", "")
        badge_map = {"free": "\U0001f7e2", "credits": "\U0001fa99", "vip": "\u2b50", "premium": "\U0001f451", "daily pass": "\U0001f535"}
        access_t = result.get("access_type", "").lower()
        badge = badge_map.get(access_t, "\U0001f3c6")
        if plan_name:
            verified_text = (
                f"\U0001f389 **Payment Verified!** {badge}\n"
                f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
                f"{badge} Welcome to the **{_md_escape(plan_name)}** Club!\n\n"
                f"_Your access has been granted. Enjoy! \U0001f680_"
            )
        else:
            verified_text = (
                "\U0001f389 **Payment Verified!**\n\n"
                "Your access/credits have been granted!"
            )
        await message.answer(verified_text, parse_mode="Markdown")
        return True
    elif status == "pending_verification":
        await message.answer(
            "⏳ **UTR Submitted**\n\n"
            f"UTR: `{utr}`\n"
            "Waiting for bank confirmation. You'll be notified once verified.",
            parse_mode="Markdown",
        )
        return True
    else:
        msg = result.get("message", "Unknown error")
        await message.answer(
            f"Verification failed: {msg}\n"
            "Please double-check your UTR number and try again."
        )
        return False


# -- /mystatus -- check order status -----------------------------------

@payment_router.message(Command("mystatus"))
async def check_status(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    await _show_pending_orders(message, user.id)


async def _show_pending_orders(message: Message, telegram_id: int) -> None:
    """Fetch pending orders from backend and display with action buttons."""
    # Try backend first — source of truth
    pending: list[dict] | None = None
    try:
        pending = await api_get(f"/payments/my-pending/{telegram_id}")
    except Exception:
        pass

    if not pending or not isinstance(pending, list) or len(pending) == 0:
        # Also check in-memory as fallback
        order_ref = _user_pending_orders.get(telegram_id)
        if order_ref:
            result = await api_get(f"/payments/order/{order_ref}")
            if result and result.get("status") in ("pending", "utr_submitted"):
                pending = [result]

    if not pending:
        await message.answer(
            "📭 **No Pending Orders**\n\n"
            "You don't have any active payment orders.\n"
            "Use /plans or /buy to start a new purchase.",
            parse_mode="Markdown",
        )
        return

    text = "📋 **YOUR PENDING ORDERS**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"
    buttons: list[list[InlineKeyboardButton]] = []

    for i, order in enumerate(pending[:5], 1):  # Show max 5
        ref = order.get("order_ref", "?")
        amount = order.get("amount", "?")
        status = order.get("status", "pending")
        utr = order.get("utr_submitted")
        expires = order.get("expires_at", "")
        custom_credits = order.get("custom_credits")

        status_icon = "⏳" if status == "pending" else "📨"
        status_label = "Awaiting UTR" if status == "pending" else "UTR Submitted"

        text += f"{status_icon} **Order #{i}**\n"
        text += f"  🔖 `{ref}`\n"
        text += f"  💵 Amount: **₹{amount}**\n"
        if custom_credits:
            text += f"  🪙 Credits: **{custom_credits}**\n"
        text += f"  📌 Status: {status_label}\n"
        if utr:
            text += f"  🔢 UTR: `{utr}`\n"
        if expires:
            try:
                from datetime import datetime as _dt
                exp_dt = _dt.fromisoformat(expires.replace("Z", "+00:00"))
                hour = exp_dt.strftime("%I").lstrip("0") or "12"
                text += f"  ⏰ Expires: {exp_dt.day} {exp_dt.strftime('%b')}, {hour}:{exp_dt.strftime('%M %p')}\n"
            except Exception:
                pass
        text += "\n"

        # Store in memory for easy UTR submission
        if i == 1:
            _user_pending_orders[telegram_id] = ref

        if status == "pending":
            buttons.append([
                InlineKeyboardButton(text=f"✏️ Enter UTR — Order #{i}", callback_data=f"enter_utr:{ref}"),
            ])
        else:
            buttons.append([
                InlineKeyboardButton(text=f"🔍 Check Status — Order #{i}", callback_data=f"check_order:{ref}"),
            ])

    text += "━━━━━━━━━━━━━━━━━━━━━━\n_Tap a button below to submit UTR or check status_"
    buttons.append([InlineKeyboardButton(text="◀️ Main Menu", callback_data="menu:main")])
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")
