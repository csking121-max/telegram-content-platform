"""
/start handler - entry-point for every user interaction.

Usage:
  /start              -> interactive main menu (browse, buy, profile)
  /start <token>      -> access check via backend
  /start adwatch_<t>  -> returning from ad-watch page, activate free access
"""

from __future__ import annotations

import asyncio
import logging
import math
import time

import base64

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.types import (
    BufferedInputFile,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from telegram_gateway.http_client import forward_to_backend, api_get, api_get_bytes, api_post
from telegram_gateway.handlers.payment import _build_enter_utr_kb, _show_pending_orders
from telegram_gateway.redis_state import set_pending_order
from telegram_gateway.redis_state import is_awaiting_bug_report as _is_bug_mode
from telegram_gateway.message_tracker import track

logger = logging.getLogger(__name__)


async def _safe_answer(callback: CallbackQuery, text: str = "", **kwargs) -> None:
    """Answer a callback query, silently ignoring expired-query errors."""
    try:
        await callback.answer(text, **kwargs)
    except TelegramBadRequest as e:
        if "query is too old" in str(e) or "query id is invalid" in str(e).lower():
            logger.debug("Stale callback query ignored: %s", e)
        else:
            raise


async def _tracked_answer(message: Message, *args, **kwargs) -> Message:
    """Thin wrapper — TrackingBot auto-tracks the outgoing message."""
    return await message.answer(*args, **kwargs)


def _md_escape(text: str) -> str:
    """Escape Telegram legacy Markdown (v1) special characters in dynamic strings."""
    for ch in ("_", "*", "`", "["):
        text = text.replace(ch, f"\\{ch}")
    return text
start_router = Router(name="start")


# -- Channel join verification --------------------------------
# Cache: (channel_id, user_id) → (result: bool, expires_at: float)
_join_cache: dict[tuple[str, int], tuple[bool, float]] = {}
_JOIN_CACHE_TTL = 300  # 5 minutes
_JOIN_CACHE_MAX = 10_000  # max entries before eviction

# -- Settings cache (shared across all handlers) --
_SETTINGS_CACHE_TTL = 60  # seconds
_settings_cache: dict[str, object] = {"data": None, "expires": 0.0}
_settings_lock = asyncio.Lock()


async def _get_settings_map() -> dict[str, str]:
    """Fetch public platform settings and return as {key: value} dict.

    Results are cached for 60 seconds to avoid repeated HTTP calls.
    Uses asyncio.Lock to prevent concurrent fetches (thundering herd).
    """
    now = time.monotonic()
    # Fast path: check cache without lock
    if (
        _settings_cache["data"] is not None
        and now < _settings_cache["expires"]  # type: ignore[operator]
    ):
        return _settings_cache["data"]  # type: ignore[return-value]

    async with _settings_lock:
        # Re-check after acquiring lock (another coroutine may have refreshed)
        now = time.monotonic()
        if (
            _settings_cache["data"] is not None
            and now < _settings_cache["expires"]  # type: ignore[operator]
        ):
            return _settings_cache["data"]  # type: ignore[return-value]

        try:
            settings_data = await api_get("/settings/public")
            if isinstance(settings_data, list):
                result = {s["key"]: s.get("value", "") for s in settings_data}
                _settings_cache["data"] = result
                _settings_cache["expires"] = now + _SETTINGS_CACHE_TTL
                return result
        except Exception:
            pass
        # Return stale cache if fetch failed
        if _settings_cache["data"] is not None:
            return _settings_cache["data"]  # type: ignore[return-value]
        return {}


async def _check_channel_join(bot: Bot, user_id: int, settings: dict[str, str]) -> bool | None:
    """
    Check if a user has joined the required content channel.
    Returns True if joined, False if not, None if check is disabled/not possible.
    Results are cached for 5 minutes to avoid repeated Telegram API calls.
    """
    require = settings.get("require_channel_join", "false").lower()
    if require not in ("true", "1", "yes"):
        return None  # feature disabled

    channel_id = settings.get("content_channel_id", "").strip()
    if not channel_id:
        return None  # no channel configured

    # Check cache
    cache_key = (channel_id, user_id)
    cached = _join_cache.get(cache_key)
    if cached is not None:
        result, expires_at = cached
        if time.monotonic() < expires_at:
            return result
        _join_cache.pop(cache_key, None)

    try:
        member = await bot.get_chat_member(chat_id=int(channel_id), user_id=user_id)
        joined = member.status in ("member", "administrator", "creator")
        # Evict oldest entries if cache is too large
        if len(_join_cache) >= _JOIN_CACHE_MAX:
            # Remove ~20% of entries at random (O(1) per key)
            import random
            evict_count = _JOIN_CACHE_MAX // 5
            evict_keys = random.sample(list(_join_cache.keys()), min(evict_count, len(_join_cache)))
            for k in evict_keys:
                _join_cache.pop(k, None)
        _join_cache[cache_key] = (joined, time.monotonic() + _JOIN_CACHE_TTL)
        return joined
    except Exception as e:
        logger.warning("Channel membership check failed for user %s: %s", user_id, e)
        return None  # can't verify, allow through


def _resolve_welcome_placeholders(
    template: str,
    display_name: str = "",
    username: str = "",
    platform_name: str = "",
    user_id: int = 0,
) -> str:
    """Replace supported placeholders in a welcome message template.

    Supported: {user_name}, {username}, {platform_name}, {user_id}
    Uses a single-pass regex to avoid cascading replacements if a user's
    name happens to contain another placeholder string.
    """
    import re

    replacements = {
        "{user_name}": display_name,
        "{username}": f"@{username}" if username else display_name,
        "{platform_name}": platform_name,
        "{user_id}": str(user_id),
    }
    pattern = re.compile("|".join(re.escape(k) for k in replacements))
    return pattern.sub(lambda m: replacements[m.group(0)], template)


def _build_join_channel_kb(channel_link: str, token: str | None = None) -> InlineKeyboardMarkup:
    """Build a keyboard with Join Channel + Check Again buttons."""
    rows: list[list[InlineKeyboardButton]] = []
    if channel_link:
        rows.append([InlineKeyboardButton(text="Join Channel", url=channel_link)])
    cb_data = f"check_join:{token}" if token else "check_join:"
    rows.append([InlineKeyboardButton(text="I've Joined - Check Again", callback_data=cb_data)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _build_main_menu(content_channel_link: str = "") -> InlineKeyboardMarkup:
    """Build the interactive main menu keyboard."""
    buttons: list[list[InlineKeyboardButton]] = []

    # Row 1: Browse content + Buy membership
    row1 = []
    if content_channel_link:
        row1.append(InlineKeyboardButton(text="Browse Content", url=content_channel_link))
    row1.append(InlineKeyboardButton(text="Buy Membership", callback_data="menu:plans"))
    buttons.append(row1)

    # Row 2: Profile + Credits
    buttons.append([
        InlineKeyboardButton(text="My Profile", callback_data="menu:profile"),
        InlineKeyboardButton(text="My Credits", callback_data="menu:credits"),
    ])

    # Row 3: Buy Credits
    buttons.append([
        InlineKeyboardButton(text="Buy Credits", callback_data="menu:buy_credits"),
    ])

    # Row 4: Payment status + Help
    buttons.append([
        InlineKeyboardButton(text="Payment Status", callback_data="menu:mystatus"),
        InlineKeyboardButton(text="Help", callback_data="menu:help"),
    ])

    # Row 5: Tutorial + Report Bug
    buttons.append([
        InlineKeyboardButton(text="📚 Tutorial", callback_data="menu:tutorial"),
        InlineKeyboardButton(text="🐛 Report Bug", callback_data="menu:bug_report"),
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _build_access_denied_menu(reason: str = "", upgrade_opts: list[str] | None = None) -> InlineKeyboardMarkup:
    """Build access denied screen with upgrade options."""
    buttons: list[list[InlineKeyboardButton]] = []
    if upgrade_opts:
        # Show targeted plan button for the required access type
        opt = upgrade_opts[0]
        buttons.append([InlineKeyboardButton(
            text=f"\u2b50 Get {opt.upper()} Membership",
            callback_data=f"plans:targeted:{opt}",
        )])
    else:
        buttons.append([InlineKeyboardButton(text="\u2b50 Buy Membership", callback_data="menu:plans")])
    buttons.append([
        InlineKeyboardButton(text="\U0001fa99 Buy Credits", callback_data="menu:buy_credits"),
    ])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f Main Menu", callback_data="menu:main")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def _format_cooldown_minutes(seconds: int | float | None) -> int:
    try:
        total = int(seconds or 0)
    except (TypeError, ValueError):
        total = 0
    return max(1, math.ceil(max(total, 0) / 60))


def _build_cooldown_notice(result: dict) -> str:
    minutes = _format_cooldown_minutes(
        result.get("cooldown_seconds") or result.get("remaining_seconds")
    )
    if result.get("reason_code") == "cooldown_applied":
        headline = f"Cooldown applied for {minutes} Minutes"
    else:
        headline = f"Cooldown active for {minutes} Minutes"
    return (
        f"{headline}\n\n"
        "This is to avoid Telegram spam detection. "
        f"You can access links after {minutes} minutes."
    )


# -- /start ------------------------------------------------

@start_router.message(CommandStart())
async def handle_start(message: Message, bot_username: str = "", hmac_secret: str = "") -> None:
    user = message.from_user
    if not user:
        return

    bot: Bot = message.bot  # type: ignore

    # Extract deep-link token from "/start TOKEN"
    parts = (message.text or "").split(maxsplit=1)
    token = parts[1].strip() if len(parts) > 1 else None

    # -- Channel join gate ------------------------------------
    settings = await _get_settings_map()
    joined = await _check_channel_join(bot, user.id, settings)
    if joined is False:
        # User has NOT joined the channel — block until they join
        channel_link = settings.get("content_channel_link", "")
        platform_name = settings.get("platform_name", "Content Platform")
        kb = _build_join_channel_kb(channel_link, token)
        await _tracked_answer(message,
            f"Welcome to **{platform_name}**!\n\n"
            "To use this bot you must first join our content channel.\n"
            "Please tap **Join Channel** below, then tap **Check Again**.",
            reply_markup=kb,
            parse_mode="Markdown",
        )
        return

    if not token:
        # -- Show interactive main menu -----------------------
        # Register/update user in backend
        try:
            await forward_to_backend(
                bot_username=bot_username,
                hmac_secret=hmac_secret,
                data={
                    "telegram_id": user.id,
                    "username": user.username,
                    "action": "register_user",
                },
            )
        except Exception:
            pass  # Non-critical - user may already exist

        # Use settings already fetched by channel-join gate
        content_channel = settings.get("content_channel_link", "")
        welcome_msg = settings.get("bot_welcome_message", "") or "Choose an option below:"
        platform_name = settings.get("platform_name", "") or "Content Platform"

        display_name = user.first_name or user.username or "there"

        # Resolve placeholders in welcome message
        welcome_msg = _resolve_welcome_placeholders(
            welcome_msg, display_name=display_name, username=user.username or "",
            platform_name=platform_name, user_id=user.id,
        )

        text = (
            f"Hey {display_name}!\n\n"
            f"Welcome to **{platform_name}**\n\n"
            f"{welcome_msg}"
        )

        kb = _build_main_menu(content_channel)
        await _tracked_answer(message, text, reply_markup=kb, parse_mode="Markdown")
        return

    # -- Ad-watch deep link: /start adwatch_TOKEN -------------
    if token.startswith("adwatch_"):
        ad_token = token[len("adwatch_"):]
        try:
            result = await api_post("/ad-watch/activate", {
                "token": ad_token,
                "telegram_id": user.id,
            })
            if result and result.get("success"):
                hours = result.get("free_hours", 12)
                await message.answer(
                    f"**Ad Watch Complete!**\n\n"
                    f"You now have **{hours} hours** of free access!\n"
                    "Go ahead and open any content link.",
                    parse_mode="Markdown",
                )
            else:
                msg = result.get("error", "Could not activate ad-watch access.") if result else "Activation failed."
                await message.answer(f"Could not activate: {msg}")
        except Exception:
            logger.exception("Ad-watch activation failed for user %s", user.id)
            await message.answer("Something went wrong activating your ad-watch access.")
        return

    # -- Token access flow ------------------------------------
    try:
        result = await forward_to_backend(
            bot_username=bot_username,
            hmac_secret=hmac_secret,
            data={
                "telegram_id": user.id,
                "username": user.username,
                "action": "access_check",
                "token": token,
            },
        )

        if not result:
            await _tracked_answer(
                message,
                "⚠️ Service temporarily unavailable. Please try again in a moment.",
            )
            return

        allowed = result.get("allowed", False)
        pack_id = result.get("pack_id")
        reason = result.get("reason", "")
        upgrade_opts = result.get("upgrade_options") or []
        credits_deducted = result.get("credits_deducted", 0)

        if allowed and pack_id:
            # Deliver content directly using copy_message
            delete_after = int(settings.get("content_delete_seconds", "0") or "0")
            if credits_deducted > 0:
                notif = await _tracked_answer(message,
                    f"Access granted! {credits_deducted} credits deducted.\n"
                    "Delivering your content..."
                )
            else:
                notif = await _tracked_answer(message, "Access granted! Delivering your content...")
            delivered_ids = await _deliver_content(message, pack_id)
            if delete_after > 0 and delivered_ids:
                asyncio.create_task(
                    _schedule_delete(
                        bot, message.chat.id,
                        [notif.message_id] + delivered_ids,
                        delete_after,
                    )
                )
        elif result.get("reason_code") in {"cooldown_active", "cooldown_applied"}:
            await _tracked_answer(message, _build_cooldown_notice(result))
        elif upgrade_opts:
            opt_name = upgrade_opts[0].upper() if upgrade_opts else ""
            text = (
                "\u26d4 **Access Restricted**\n\n"
                f"This content requires a **{_md_escape(opt_name)}** membership.\n\n"
                "Upgrade now to unlock this and more premium content \u2b07\ufe0f"
            )
            kb = _build_access_denied_menu(upgrade_opts=upgrade_opts)
            await _tracked_answer(message, text, reply_markup=kb, parse_mode="Markdown")
        else:
            text = (
                "\u26d4 **Access Denied**\n\n"
                f"{_md_escape(reason)}\n\n"
                "Get access using one of these options \u2b07\ufe0f"
            )
            kb = _build_access_denied_menu(reason)
            await _tracked_answer(message, text, reply_markup=kb, parse_mode="Markdown")

    except Exception:
        logger.exception("Error processing /start for user %s", user.id)
        await message.answer("Something went wrong. Please try again later.")


async def _deliver_content(message: Message, pack_id: int) -> list[int]:
    """Fetch pack items from backend and deliver via copy_message.

    Returns the list of sent message IDs so the caller can schedule deletion.
    Strategy:
      1. Try copy_message directly (works if delivery bot is in storage group)
      2. If direct fails, parallel proxy: download via storage bot + re-upload
         via delivery bot (content appears in correct bot's chat)
    """
    bot: Bot = message.bot  # type: ignore
    user_chat_id = message.chat.id
    sent_ids: list[int] = []

    try:
        items = await api_get(f"/internal/pack-items/{pack_id}")
        if not items:
            await message.answer("Content pack is empty or not found.")
            return sent_ids

        valid_items = [
            it for it in items
            if it.get("storage_chat_id") and it.get("storage_message_id")
        ]
        if not valid_items:
            await message.answer("Content pack is empty or not found.")
            return sent_ids

        # ── Attempt 1: direct copy_message (fastest, same-bot) ──
        first = valid_items[0]
        direct_works = False
        try:
            sent = await asyncio.wait_for(
                bot.copy_message(
                    chat_id=user_chat_id,
                    from_chat_id=first["storage_chat_id"],
                    message_id=first["storage_message_id"],
                    protect_content=True,
                ),
                timeout=5,
            )
            sent_ids.append(sent.message_id)
            direct_works = True
        except Exception:
            pass  # direct copy failed, will use relay

        if direct_works:
            # Direct works — copy remaining items in parallel (fast path)
            async def _direct_copy(item: dict) -> int | None:
                try:
                    sent = await asyncio.wait_for(
                        bot.copy_message(
                            chat_id=user_chat_id,
                            from_chat_id=item["storage_chat_id"],
                            message_id=item["storage_message_id"],
                            protect_content=True,
                        ),
                        timeout=10,
                    )
                    return sent.message_id
                except Exception as e:
                    logger.warning("Direct copy failed for item %s: %s", item.get("id"), e)
                    return None

            results = await asyncio.gather(*[_direct_copy(it) for it in valid_items[1:]])
            sent_ids.extend(mid for mid in results if mid is not None)
        else:
            # ── Attempt 2: parallel proxy via delivery bot ──
            # Download all items via storage bot, re-upload via delivery bot
            # so content appears in the correct bot's chat.
            tasks = [
                _deliver_via_proxy(
                    bot, user_chat_id,
                    it["storage_chat_id"],
                    it["storage_message_id"],
                    it.get("media_type", "document"),
                )
                for it in valid_items
            ]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for r in results:
                if isinstance(r, Message):
                    sent_ids.append(r.message_id)

        if not sent_ids:
            await message.answer("Could not deliver content. Please contact support.")
        else:
            logger.info(
                "Delivered %d/%d items from pack %s to user %s",
                len(sent_ids), len(valid_items), pack_id, user_chat_id,
            )
    except Exception:
        logger.exception("Content delivery failed for pack %s", pack_id)
        await message.answer("Delivery failed. Please try again later.")

    return sent_ids


async def _deliver_via_proxy(
    bot: Bot,
    chat_id: int,
    storage_chat_id: int,
    storage_message_id: int,
    media_type: str,
) -> Message | None:
    """Download content via backend proxy and send to user via delivery bot."""
    try:
        result = await api_get_bytes(
            f"/internal/content-proxy/{storage_chat_id}/{storage_message_id}",
        )
        if not result:
            return None
        file_bytes, headers = result
        mt = headers.get("x-media-type", media_type)
        input_file = BufferedInputFile(file_bytes, filename=f"content.{mt}")

        if mt == "photo":
            return await bot.send_photo(chat_id=chat_id, photo=input_file, protect_content=True)
        elif mt == "video":
            return await bot.send_video(chat_id=chat_id, video=input_file, protect_content=True)
        elif mt == "animation":
            return await bot.send_animation(chat_id=chat_id, animation=input_file, protect_content=True)
        else:
            return await bot.send_document(chat_id=chat_id, document=input_file, protect_content=True)
    except Exception as e:
        logger.warning("Proxy delivery failed for %s/%s: %s", storage_chat_id, storage_message_id, e)
        return None


async def _schedule_delete(bot: Bot, chat_id: int, message_ids: list[int], delay: int) -> None:
    """Delete messages from *chat_id* after *delay* seconds (content auto-expiry)."""
    await asyncio.sleep(delay)
    for msg_id in message_ids:
        try:
            await bot.delete_message(chat_id=chat_id, message_id=msg_id)
        except Exception:
            pass  # Already deleted or older than the 48-hour Telegram limit


# -- /menu - re-show the main menu ----------------------------

@start_router.message(Command("menu"))
async def handle_menu(message: Message) -> None:
    user = message.from_user
    if not user:
        return

    settings_map = await _get_settings_map()
    content_channel = settings_map.get("content_channel_link", "")

    kb = _build_main_menu(content_channel)
    await _tracked_answer(message, "**Main Menu** - choose an option:", reply_markup=kb, parse_mode="Markdown")


# -- /profile - show user profile ------------------------------

@start_router.message(Command("profile"))
async def handle_profile(message: Message) -> None:
    user = message.from_user
    if not user:
        return
    await _send_profile(message, user.id)


# -- Callback handlers for menu buttons -----------------------

@start_router.callback_query(lambda c: c.data and c.data.startswith("check_join:"))
async def handle_check_join(callback: CallbackQuery) -> None:
    """User tapped 'Check Again' after joining the channel."""
    user = callback.from_user
    if not user or not callback.data:
        return

    await _safe_answer(callback)
    bot: Bot = callback.bot  # type: ignore
    settings = await _get_settings_map()
    joined = await _check_channel_join(bot, user.id, settings)

    if joined is False:
        channel_link = settings.get("content_channel_link", "")
        token_part = callback.data.split(":", 1)[1] if ":" in callback.data else ""
        kb = _build_join_channel_kb(channel_link, token_part or None)
        await callback.message.answer(  # type: ignore
            "You haven't joined the channel yet.\n"
            "Please join first, then tap **Check Again**.",
            reply_markup=kb,
            parse_mode="Markdown",
        )
        return

    # User has joined — show main menu (or process their original token)
    token_part = callback.data.split(":", 1)[1] if ":" in callback.data else ""
    content_channel = settings.get("content_channel_link", "")
    platform_name = settings.get("platform_name", "Content Platform")
    welcome_msg = settings.get("bot_welcome_message", "Choose an option below:")

    if token_part:
        # Auto-resolve the token — pass it through the access check flow
        try:
            result = await forward_to_backend(
                bot_username=(await bot.get_me()).username or "",
                hmac_secret="",
                data={
                    "telegram_id": user.id,
                    "username": user.username,
                    "action": "access_check",
                    "token": token_part,
                },
            )
            if result and result.get("allowed") and result.get("pack_id"):
                delete_after = int(settings.get("content_delete_seconds", "0") or "0")
                credits_deducted = result.get("credits_deducted", 0)
                if credits_deducted > 0:
                    notif = await callback.message.answer(  # type: ignore
                        f"✅ Channel verified! Access granted \\({credits_deducted} credits deducted\\).\nDelivering your content..."
                    )
                else:
                    notif = await callback.message.answer(  # type: ignore
                        "✅ Channel verified! Access granted \\- delivering your content..."
                    )
                delivered_ids = await _deliver_content(callback.message, result["pack_id"])  # type: ignore
                if delete_after > 0 and delivered_ids:
                    asyncio.create_task(
                        _schedule_delete(bot, callback.message.chat.id, [notif.message_id] + delivered_ids, delete_after)  # type: ignore
                    )
            else:
                reason = result.get("reason", "") if result else ""
                upgrade_opts = result.get("upgrade_options") or [] if result else []
                if result and result.get("reason_code") in {"cooldown_active", "cooldown_applied"}:
                    await callback.message.answer(  # type: ignore
                        _build_cooldown_notice(result),
                    )
                    return
                if upgrade_opts:
                    kb = _build_access_denied_menu(upgrade_opts=upgrade_opts)
                else:
                    kb = _build_access_denied_menu(reason)
                await callback.message.answer(  # type: ignore
                    f"✅ Channel verified!\\n\\n⛔ {_md_escape(reason or 'Access denied.')}",
                    reply_markup=kb,
                    parse_mode="Markdown",
                )
        except Exception:
            logger.exception("Token resolution after channel join failed for user %s", user.id)
            await callback.message.answer(  # type: ignore
                "✅ Channel verified! Please tap your content link again to access it.",
            )
    else:
        display_name = user.first_name or user.username or "there"

        # Resolve placeholders in welcome message
        welcome_msg = _resolve_welcome_placeholders(
            welcome_msg, display_name=display_name, username=user.username or "",
            platform_name=platform_name, user_id=user.id,
        )

        text = (
            f"Hey {display_name}!\n\n"
            f"Welcome to **{platform_name}**\n\n"
            f"{welcome_msg}"
        )
        kb = _build_main_menu(content_channel)
        await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")  # type: ignore


@start_router.callback_query(lambda c: c.data and c.data.startswith("menu:"))
async def handle_menu_callback(callback: CallbackQuery) -> None:
    user = callback.from_user
    if not user or not callback.data:
        return

    action = callback.data.split(":")[1]
    await _safe_answer(callback)

    if action == "profile":
        await _send_profile(callback.message, user.id)  # type: ignore

    elif action == "credits":
        await _send_credits(callback.message, user.id)  # type: ignore

    elif action == "plans":
        await _send_plans(callback.message, telegram_id=user.id)  # type: ignore

    elif action == "buy_credits":
        await _send_credit_packages(callback.message, user.id)  # type: ignore

    elif action == "watch_ad":
        await _start_ad_watch(callback.message, user.id)  # type: ignore

    elif action == "main":
        settings_map = await _get_settings_map()
        content_channel = settings_map.get("content_channel_link", "")
        kb = _build_main_menu(content_channel)
        await callback.message.answer("**Main Menu** - choose an option:", reply_markup=kb, parse_mode="Markdown")  # type: ignore

    elif action == "mystatus":
        await _show_pending_orders(callback.message, user.id)  # type: ignore

    elif action == "help":
        settings_map = await _get_settings_map()
        support = settings_map.get("support_contact", "")
        text = (
            "**Help**\n\n"
            "**Commands:**\n"
            "/start - Main menu\n"
            "/plans - View membership plans\n"
            "/buy - Purchase membership\n"
            "/pay <UTR> - Submit payment reference\n"
            "/mystatus - Check payment status\n"
            "/profile - View your profile\n"
            "/menu - Show main menu\n"
        )
        if support:
            text += f"\nSupport: {support}"
        await callback.message.answer(text, parse_mode="Markdown")  # type: ignore

    elif action == "bug_report":
        from telegram_gateway.redis_state import set_awaiting_bug_report
        set_awaiting_bug_report(user.id)
        await callback.message.answer(  # type: ignore
            "🐛 **Report a Bug**\n\n"
            "Please type your bug report below. Describe the issue in detail.\n\n"
            "When you're done, send /send to submit your report.\n"
            "Send /cancel to cancel.",
            parse_mode="Markdown",
        )

    elif action == "tutorial":
        await _send_tutorial_menu(callback.message, user.id)  # type: ignore


# -- Bug report flow ------------------------------------------------

# Temporary in-memory storage for multi-message bug reports
_bug_report_texts: dict[int, str] = {}


@start_router.message(Command("send"))
async def handle_send_bug(message: Message) -> None:
    """Submit the accumulated bug report text."""
    user = message.from_user
    if not user:
        return
    from telegram_gateway.redis_state import is_awaiting_bug_report, clear_awaiting_bug_report
    if not is_awaiting_bug_report(user.id):
        return  # Not in bug report mode, let other handlers process
    report_text = _bug_report_texts.pop(user.id, "")
    if not report_text.strip():
        await message.answer("You haven't typed any bug report yet. Please type your report first, then send /send.")
        return
    clear_awaiting_bug_report(user.id)
    # Submit to backend
    result = await api_post("/internal/bug-reports", {
        "telegram_id": user.id,
        "username": user.username,
        "first_name": user.first_name,
        "report": report_text.strip(),
    })
    if result and not result.get("_error"):
        await message.answer("✅ **Bug submitted successfully!** Thank you for your report.", parse_mode="Markdown")
    else:
        await message.answer("❌ Failed to submit bug report. Please try again later.")


@start_router.message(Command("cancel"))
async def handle_cancel_bug(message: Message) -> None:
    """Cancel the bug report flow."""
    user = message.from_user
    if not user:
        return
    from telegram_gateway.redis_state import is_awaiting_bug_report, clear_awaiting_bug_report
    if not is_awaiting_bug_report(user.id):
        return
    clear_awaiting_bug_report(user.id)
    _bug_report_texts.pop(user.id, None)
    await message.answer("Bug report cancelled.")


@start_router.message(
    lambda m: (
        m.chat.type == "private"
        and m.text
        and not m.text.startswith("/")
        and m.from_user
        and _is_bug_mode(m.from_user.id)
    )
)
async def handle_bug_report_text(message: Message) -> None:
    """Capture bug report text while user is in bug report mode."""
    user = message.from_user
    if not user or not message.text:
        return
    existing = _bug_report_texts.get(user.id, "")
    _bug_report_texts[user.id] = (existing + "\n" + message.text).strip()
    await message.answer("📝 Noted. You can keep typing or send /send to submit your report.")


# -- Tutorial flow ---------------------------------------------------

async def _send_tutorial_menu(message: Message, user_id: int) -> None:
    """Show tutorial menu with available tutorial topics."""
    tutorials = await api_get("/internal/tutorials")
    if not tutorials:
        await message.answer(
            "📚 **Tutorial**\n\nNo tutorials available yet. Check back later!",
            parse_mode="Markdown",
        )
        return

    buttons: list[list[InlineKeyboardButton]] = []
    for t in tutorials:
        buttons.append([
            InlineKeyboardButton(
                text=f"📖 {t['question']}",
                callback_data=f"tutorial:{t['id']}",
            )
        ])
    buttons.append([InlineKeyboardButton(text="◀️ Main Menu", callback_data="menu:main")])

    await message.answer(
        "📚 **Tutorial**\n\nSelect a topic to watch the tutorial video:",
        reply_markup=InlineKeyboardMarkup(inline_keyboard=buttons),
        parse_mode="Markdown",
    )


@start_router.callback_query(lambda c: c.data and c.data.startswith("tutorial:"))
async def handle_tutorial_callback(callback: CallbackQuery) -> None:
    """Send the tutorial video to the user."""
    user = callback.from_user
    if not user or not callback.data:
        return
    await _safe_answer(callback)

    tutorial_id = callback.data.split(":")[1]
    tutorials = await api_get("/internal/tutorials")
    if not tutorials:
        await callback.message.answer("Tutorial not found.")  # type: ignore
        return

    tutorial = next((t for t in tutorials if str(t["id"]) == tutorial_id), None)
    if not tutorial:
        await callback.message.answer("Tutorial not found.")  # type: ignore
        return

    bot: Bot = callback.message.bot  # type: ignore
    try:
        await bot.copy_message(
            chat_id=callback.message.chat.id,  # type: ignore
            from_chat_id=tutorial["storage_chat_id"],
            message_id=tutorial["storage_message_id"],
            protect_content=True,
        )
    except Exception:
        # Fallback: try sending by file_id
        try:
            await bot.send_video(
                chat_id=callback.message.chat.id,  # type: ignore
                video=tutorial["file_id"],
                protect_content=True,
            )
        except Exception as e:
            logger.warning("Tutorial delivery failed: %s", e)
            await callback.message.answer("❌ Could not deliver tutorial video. Please try again later.")  # type: ignore
            return

    # Show back button
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📚 More Tutorials", callback_data="menu:tutorial")],
        [InlineKeyboardButton(text="◀️ Main Menu", callback_data="menu:main")],
    ])
    await callback.message.answer(  # type: ignore
        f"📖 *{_md_escape(tutorial['question'])}*",
        reply_markup=kb,
        parse_mode="Markdown",
    )


# -- Plan callbacks: targeted view + detail view -------------------

@start_router.callback_query(lambda c: c.data and c.data.startswith("plans:targeted:"))
async def handle_targeted_plan(callback: CallbackQuery) -> None:
    """Show a specific plan based on the access type the user needs."""
    user = callback.from_user
    if not user or not callback.data:
        return
    await _safe_answer(callback)
    access_type = callback.data.split(":", 2)[2]
    await _send_plans(callback.message, target_access_type=access_type, telegram_id=user.id)  # type: ignore


@start_router.callback_query(lambda c: c.data and c.data.startswith("planview:"))
async def handle_plan_detail_view(callback: CallbackQuery) -> None:
    """Show detailed view of a single plan with purchase options."""
    user = callback.from_user
    if not user or not callback.data:
        return
    await _safe_answer(callback)
    plan_id = int(callback.data.split(":")[1])

    plans = await api_get("/payments/plans")
    if not plans:
        await callback.message.answer("Could not load plans.")  # type: ignore
        return
    plan = next((p for p in plans if p["id"] == plan_id), None)
    if not plan:
        await callback.message.answer("Plan not found.")  # type: ignore
        return

    # Fetch user's max tier for tier guard
    profile = await api_get(f"/access/profile/{user.id}")
    user_max_tier = profile.get("max_tier_level", 0) if profile else 0

    await _send_plan_detail(callback.message, plan, user_max_tier=user_max_tier)  # type: ignore


# -- Helper functions -----------------------------------------

async def _send_profile(message: Message, telegram_id: int) -> None:
    """Show user profile with membership, credit, ad-watch, and referral info."""
    DIV = "━━━━━━━━━━━━━━━━━━━━━━"
    LINE = "┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈┈"

    profile = await api_get(f"/access/profile/{telegram_id}")
    if not profile:
        await message.answer(
            f"👤 **MY PROFILE**\n{DIV}\n\n"
            f"🆔 ID: `{telegram_id}`\n"
            "⚠️ Could not load full profile data.",
            parse_mode="Markdown",
        )
        return

    membership_type = profile.get("membership_type", "free")
    membership_expiry = profile.get("membership_expiry", "N/A")
    credits = profile.get("credits", 0)
    level = profile.get("level", 0)

    # ── Header ──
    text = f"👤 **MY PROFILE**\n{DIV}\n\n"

    # ── Basic Info ──
    level_stars = "⭐" * min(level, 5) if level > 0 else "🆕"
    text += f"🆔  Telegram ID:  `{telegram_id}`\n"
    text += f"🏅  Level:  {level_stars} **{level}**\n"
    text += f"💰  Credits:  **{credits}**\n"

    def _fmt_date(raw: str) -> str:
        """Format an ISO datetime string to e.g. '19 Mar 2026, 7:43 PM'."""
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            hour = dt.strftime("%I").lstrip("0") or "12"
            return f"{dt.day} {dt.strftime('%b %Y')}, {hour}:{dt.strftime('%M %p')}"
        except Exception:
            return raw

    # ── Memberships ──
    text += f"\n📋 **MEMBERSHIPS**\n{LINE}\n"
    active_memberships = profile.get("active_memberships", [])
    if active_memberships:
        for m in active_memberships:
            mtype = m.get("type", "unknown").upper()
            mexpiry = m.get("expiry_at", "")
            badge = "👑" if "premium" in mtype.lower() else "💎" if "vip" in mtype.lower() else "🎫"
            if mexpiry:
                text += f"  {badge} **{_md_escape(mtype)}**  ·  expires {_fmt_date(mexpiry)}\n"
            else:
                text += f"  {badge} **{_md_escape(mtype)}**  ·  ♾ no expiry\n"
    else:
        badge = "👑" if "premium" in membership_type.lower() else "💎" if "vip" in membership_type.lower() else "🆓"
        text += f"  {badge} **{_md_escape(membership_type.upper())}**\n"
        if membership_expiry and membership_expiry != "N/A":
            text += f"  ⏳ Expires: {_fmt_date(str(membership_expiry))}\n"

    # ── Ad-Watch ──
    ad_access = profile.get("ad_watch_active", False)
    ad_expires = profile.get("ad_watch_expires", "")
    if ad_access:
        text += f"\n🎬 **AD-WATCH ACCESS**\n{LINE}\n"
        text += f"  ✅ Active until {_fmt_date(str(ad_expires)) if ad_expires else '?'}\n"

    # ── Daily Pass ──
    daily_pass = profile.get("daily_pass_active", False)
    if daily_pass:
        text += f"\n🎫 **DAILY PASS**\n{LINE}\n"
        text += "  ✅ Active today\n"

    # ── Referrals ──
    referral_count = profile.get("referral_count", 0)
    referral_credits = profile.get("referral_credits_earned", 0)
    if referral_count > 0:
        text += f"\n👥 **REFERRALS**\n{LINE}\n"
        text += f"  📊 **{referral_count}** invite{'s' if referral_count != 1 else ''}  ·  💎 **{referral_credits}** credits earned\n"

    # ── Streak ──
    streak = profile.get("streak", {})
    if streak.get("enabled"):
        current = streak.get("current_streak", 0)
        longest = streak.get("longest_streak", 0)
        today_spent = streak.get("today_spent", 0)
        min_spend = streak.get("min_daily_spend", 5)
        today_ok = streak.get("today_qualified", False)
        bonus_earned = streak.get("total_bonus_earned", 0)

        fire = "🔥" * min(current, 5) if current > 0 else "💤"
        text += f"\n🔥 **DAILY STREAK**\n{LINE}\n"
        text += f"  {fire}  **{current} day{'s' if current != 1 else ''}**\n"

        # Level display
        level_info = streak.get("current_level")
        if level_info:
            lvl_stars = "⭐" * min(level_info.get("level", 0), 5)
            lv_label = level_info.get("label") or f"Level {level_info.get('level', 0)}"
            text += f"  🏆 {lvl_stars} **{_md_escape(lv_label)}**\n"

        text += f"  📈 Longest: **{longest}** days  ·  🎁 Bonus: **{bonus_earned}**\n"
        if today_ok:
            text += "  ✅ Today: **Completed!**\n"
        else:
            pct = int(today_spent / min_spend * 100) if min_spend > 0 else 0
            bar_filled = round(pct / 10)
            bar = "▓" * bar_filled + "░" * (10 - bar_filled)
            text += f"  ⏳ Today: {today_spent}/{min_spend} credits `{bar}` {pct}%\n"

        nxt = streak.get("next_milestone")
        if nxt:
            text += f"  🎯 Next reward: **{nxt['bonus_credits']}** credits in **{nxt['days_remaining']}** day{'s' if nxt['days_remaining'] != 1 else ''}\n"

        nxt_lvl = streak.get("next_level")
        if nxt_lvl:
            text += f"  🆙 Next level: **{_md_escape(nxt_lvl['label'])}** in **{nxt_lvl['days_remaining']}** day{'s' if nxt_lvl['days_remaining'] != 1 else ''}"
            rewards = []
            if nxt_lvl.get("bonus_credits", 0) > 0:
                rewards.append(f"{nxt_lvl['bonus_credits']} credits")
            if nxt_lvl.get("has_membership"):
                rewards.append("membership")
            if rewards:
                text += f" ({' + '.join(rewards)})"
            text += "\n"

    # ── Footer ──
    text += f"\n{DIV}"

    await message.answer(text, parse_mode="Markdown")


async def _send_credits(message: Message, telegram_id: int) -> None:
    """Show user credit balance with buy options."""
    profile = await api_get(f"/access/profile/{telegram_id}")
    credits = profile.get("credits", 0) if profile else "?"

    buttons = [
        [InlineKeyboardButton(text="Buy Credit Packs", callback_data="menu:buy_credits")],
    ]
    kb = InlineKeyboardMarkup(inline_keyboard=buttons)

    await message.answer(
        f"**Your Credits**: **{credits}**\n\n"
        "Get more credits through purchases or referrals!",
        reply_markup=kb,
        parse_mode="Markdown",
    )


async def _send_plans(message: Message, target_access_type: str | None = None, telegram_id: int = 0) -> None:
    """Show available membership plans with premium formatting.

    If *target_access_type* is given, show that plan first with an option to
    view all plans.
    """
    plans = await api_get("/payments/plans")
    if not plans:
        await message.answer("No plans available right now.")
        return

    # Fetch user's max tier for tier markers
    user_max_tier = 0
    if telegram_id:
        profile = await api_get(f"/access/profile/{telegram_id}")
        user_max_tier = profile.get("max_tier_level", 0) if profile else 0

    if target_access_type:
        # Find the targeted plan
        targeted = [p for p in plans if p.get("access_type", "").lower() == target_access_type.lower()]
        if targeted:
            p = targeted[0]
            await _send_plan_detail(message, p, show_all_plans_btn=True, user_max_tier=user_max_tier)
            return
        # If not found, fall through to show all

    # --- Premium plan list ---
    text = (
        "\u2b50 **MEMBERSHIP PLANS** \u2b50\n"
        "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
        "Choose a plan to view details and purchase:\n\n"
    )

    buttons: list[list[InlineKeyboardButton]] = []
    tier_icons = {0: "\u25ab\ufe0f", 1: "\U0001f7e2", 2: "\U0001f535", 3: "\U0001f7e1", 4: "\u2b50", 5: "\U0001f451"}

    for p in plans:
        tier = p.get("tier_level", 0)
        icon = tier_icons.get(tier, "\u2b50")
        pname = p.get("display_name") or p["name"]
        duration = _format_duration(p)
        price_txt = f"\u20b9{p['price_inr']}"
        if p.get("credit_price") and p["credit_price"] > 0:
            price_txt += f" / {p['credit_price']} Credits"

        # Tier marker
        tier_marker = ""
        if tier > 0 and user_max_tier >= tier:
            tier_marker = " \u2705" if user_max_tier == tier else " \u2705"

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

    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f Main Menu", callback_data="menu:main")])

    text += "\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n_Tap a plan to view details & buy_"

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


def _format_duration(plan: dict) -> str:
    """Format plan duration as readable string."""
    parts = []
    days = plan.get("duration_days", 0)
    hours = plan.get("duration_hours", 0)
    if days:
        parts.append(f"{days} Day{'s' if days > 1 else ''}")
    if hours:
        parts.append(f"{hours} Hour{'s' if hours > 1 else ''}")
    return " ".join(parts) or "Unlimited"


async def _send_plan_detail(message: Message, plan: dict, show_all_plans_btn: bool = False, user_max_tier: int = 0) -> None:
    """Show a single plan detail with INR / Credits purchase buttons + Back."""
    pname = plan.get("display_name") or plan["name"]
    access = (plan.get("access_type") or "").upper()
    duration = _format_duration(plan)
    desc = plan.get("description") or "Premium membership with full access."
    price = plan["price_inr"]
    credit_price = plan.get("credit_price", 0)
    bonus = plan.get("credit_reward", 0)
    plan_id = plan["id"]
    plan_tier = plan.get("tier_level", 0)

    tier_icons = {0: "\u25ab\ufe0f", 1: "\U0001f7e2", 2: "\U0001f535", 3: "\U0001f7e1", 4: "\u2b50", 5: "\U0001f451"}
    icon = tier_icons.get(plan_tier, "\u2b50")

    # Check if plan is tier-locked for this user
    tier_locked = plan_tier > 0 and user_max_tier > plan_tier
    is_renewal = plan_tier > 0 and user_max_tier == plan_tier

    text = (
        f"{icon} **{_md_escape(pname)}** {icon}\n"
        f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n\n"
        f"\U0001f4cb **Plan Details:**\n"
        f"    \U0001f3f7\ufe0f Type: **{_md_escape(access)}**\n"
        f"    \u23f3 Duration: **{_md_escape(duration)}**\n"
        f"    \U0001f4b0 Price: **\u20b9{price}**\n"
    )
    if credit_price > 0:
        text += f"    \U0001fa99 Credit Price: **{credit_price} Credits**\n"
    if bonus > 0:
        text += f"    \U0001f381 Bonus: **+{bonus} Credits**\n"
    text += (
        f"\n\U0001f4dd **Description:**\n"
        f"    _{_md_escape(desc)}_\n\n"
    )

    buttons: list[list[InlineKeyboardButton]] = []

    if tier_locked:
        # User has a higher tier
        text += (
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            "\U0001f451 **You have a higher\\-tier membership\\!**\n"
            "_This plan is already included in your current access\\._"
        )
    elif is_renewal:
        text += (
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            "\U0001f504 **Renew your membership\\!** Your current plan will be extended\\."
        )
        pay_row = [InlineKeyboardButton(
            text=f"\U0001f504 Renew \u20b9{price} UPI",
            callback_data=f"plan:{plan_id}",
        )]
        if credit_price > 0:
            pay_row.append(InlineKeyboardButton(
                text=f"\U0001fa99 Renew {credit_price} Credits",
                callback_data=f"plan_credits:{plan_id}",
            ))
        buttons.append(pay_row)
    else:
        text += (
            f"\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n"
            "Choose your payment method \u2b07\ufe0f"
        )
        pay_row = [InlineKeyboardButton(
            text=f"\U0001f4b3 \u20b9{price} UPI",
            callback_data=f"plan:{plan_id}",
        )]
        if credit_price > 0:
            pay_row.append(InlineKeyboardButton(
                text=f"\U0001fa99 {credit_price} Credits",
                callback_data=f"plan_credits:{plan_id}",
            ))
        buttons.append(pay_row)

    if show_all_plans_btn:
        buttons.append([InlineKeyboardButton(text="\U0001f4cb View All Plans", callback_data="menu:plans")])
    buttons.append([InlineKeyboardButton(text="\u25c0\ufe0f Back to Plans", callback_data="menu:plans")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


async def _send_credit_packages(message: Message, telegram_id: int) -> None:
    """Show available credit packages for purchase, plus custom-amount option."""
    packages = await api_get("/credit-packages")

    # Fetch limits for custom amount display
    min_credits = 10
    try:
        settings_data = await api_get("/settings/public")
        if isinstance(settings_data, list):
            for s in settings_data:
                if s.get("key") == "custom_credits_min":
                    min_credits = int(s.get("value") or "10")
    except Exception:
        pass

    buttons: list[list[InlineKeyboardButton]] = []
    text = "🪙 **Credit Packages**\n━━━━━━━━━━━━━━━━━━━━━━\n\n"

    if packages:
        for p in packages:
            text += (
                f"💎 **{_md_escape(p.get('display_name') or p['name'])}**\n"
                f"  📦 {p['credits']} credits  ·  💵 ₹{p['price_inr']}\n"
            )
            if p.get("description"):
                text += f"  _{_md_escape(p['description'])}_\n"
            text += "\n"
            buttons.append([
                InlineKeyboardButton(
                    text=f"💎 {p['credits']} Credits — ₹{p['price_inr']}",
                    callback_data=f"creditpkg:{p['id']}",
                )
            ])
    else:
        text += "_No fixed packages available right now._\n\n"

    text += f"━━━━━━━━━━━━━━━━━━━━━━\n⌨️ Or buy a custom amount (min: {min_credits:,} credits)"

    buttons.append([
        InlineKeyboardButton(text="⌨️ Custom Amount", callback_data="custom_buy:enter")
    ])
    buttons.append([
        InlineKeyboardButton(text="◀️ Main Menu", callback_data="menu:main")
    ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(text, reply_markup=kb, parse_mode="Markdown")


async def _start_ad_watch(message: Message, telegram_id: int) -> None:
    """Start an ad-watch session for free access."""
    try:
        bot: Bot = message.bot  # type: ignore
        me = await bot.get_me()
        result = await api_post("/ad-watch/start", {
            "telegram_id": telegram_id,
            "bot_username": me.username or "",
        })
        if result and result.get("ad_page_url"):
            url = result["ad_page_url"]
            buttons = [[InlineKeyboardButton(text="Watch Ads Now", url=url)]]
            kb = InlineKeyboardMarkup(inline_keyboard=buttons)
            ads_required = result.get("ads_required", 4)
            free_hours = result.get("free_hours", 12)
            await message.answer(
                f"**Watch Ads for Free Access!**\n\n"
                f"Watch **{ads_required} short ads** to get **{free_hours} hours** of free access.\n\n"
                "Click the button below to start:",
                reply_markup=kb,
                parse_mode="Markdown",
            )
        elif result and result.get("already_active"):
            expires = result.get("expires_at", "")
            await message.answer(
                f"You already have active ad-watch access until {expires}!",
                parse_mode="Markdown",
            )
        else:
            msg = result.get("error", "Ad-watch is currently unavailable.") if result else "Service unavailable."
            await message.answer(msg)
    except Exception:
        logger.exception("Ad-watch start failed for user %s", telegram_id)
        await message.answer("Something went wrong. Try again later.")


# -- Credit package purchase callback -------------------------

@start_router.callback_query(lambda c: c.data and c.data.startswith("creditpkg:"))
async def handle_credit_package_buy(callback: CallbackQuery) -> None:
    user = callback.from_user
    if not user or not callback.data:
        return

    pkg_id = callback.data.split(":")[1]
    await _safe_answer(callback)

    try:
        result = await api_post("/credit-packages/buy", {
            "package_id": int(pkg_id),
            "telegram_id": user.id,
        })
        if result and (result.get("qr_url") or result.get("qr_data_url")):
            order_ref = result.get("order_ref", "")
            set_pending_order(user.id, order_ref)

            text = (
                f"**Payment for Credit Pack**\n\n"
                f"Amount: Rs.**{result.get('amount', '?')}**\n"
                f"Order: `{order_ref}`\n\n"
                f"**How to pay:**\n"
                f"1. Scan the QR code below with any UPI app\n"
                f"2. Complete the payment\n"
                f"3. Tap **Enter UTR** below and send your reference number\n"
            )

            kb = _build_enter_utr_kb(order_ref)

            # Send QR as a photo (base64 data URL -> bytes)
            qr_data = result.get("qr_data_url") or result.get("qr_url", "")
            if qr_data.startswith("data:image/png;base64,"):
                img_bytes = base64.b64decode(qr_data.split(",", 1)[1])
                photo = BufferedInputFile(img_bytes, filename="qr_code.png")
                await callback.message.answer_photo(  # type: ignore
                    photo=photo,
                    caption=text,
                    reply_markup=kb,
                    parse_mode="Markdown",
                )
            else:
                # Fallback: just send text
                await callback.message.answer(text, reply_markup=kb, parse_mode="Markdown")  # type: ignore
        else:
            msg = result.get("error", "Could not create payment order.") if result else "Payment service unavailable."
            await callback.message.answer(f"Error: {msg}")  # type: ignore
    except Exception:
        logger.exception("Credit package buy failed for user %s", user.id)
        await callback.message.answer("Something went wrong. Try again later.")  # type: ignore
