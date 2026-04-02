"""
Upload & Publish handler -- admin uploads content via the Storage Group.

Flow:
  1. Admin sends /upload in storage group -> bot enters collection mode
  2. Admin sends photos/videos -> bot collects them
  3. Admin sends /publish -> bot prompts: select bot, select category, thumbnail
  4. Bot generates deep link, auto-posts to main channel

All state is managed per-chat (the storage group).
All backend calls use /internal/* endpoints (no JWT required).
"""
from __future__ import annotations

import logging
import time
from collections import OrderedDict
from typing import Optional

from aiogram import Bot, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command
from aiogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from telegram_gateway.http_client import api_get, api_post

logger = logging.getLogger(__name__)
upload_router = Router(name="upload")


async def _safe_answer(callback: CallbackQuery, text: str = "", **kwargs) -> None:
    """Answer a callback query, silently ignoring expired-query errors."""
    try:
        await callback.answer(text, **kwargs)
    except TelegramBadRequest as e:
        if "query is too old" in str(e) or "query id is invalid" in str(e).lower():
            logger.debug("Stale callback query ignored: %s", e)
        else:
            raise

# -- In-memory upload sessions (per chat_id) --
_upload_sessions: dict[int, dict] = {}
_SESSION_TTL = 3600  # 1 hour — auto-expire stale sessions


def _get_session(chat_id: int) -> Optional[dict]:
    session = _upload_sessions.get(chat_id)
    if session and time.monotonic() - session.get("_created_at", 0) > _SESSION_TTL:
        _upload_sessions.pop(chat_id, None)
        return None
    return session


def _prune_stale_sessions() -> None:
    """Remove upload/announce sessions older than TTL."""
    now = time.monotonic()
    for store in (_upload_sessions, _announce_sessions):
        expired = [k for k, v in store.items() if now - v.get("_created_at", 0) > _SESSION_TTL]
        for k in expired:
            store.pop(k, None)


# ---------------------------------------------------------------------------
# Multi-bot deduplication
# ---------------------------------------------------------------------------
# When multiple bots share the same storage group, every bot receives each
# message.  _claim_message() ensures only the FIRST bot to process a given
# (chat_id, message_id) pair actually handles it; all others skip silently.
# Bounded to prevent unbounded memory growth.
# ---------------------------------------------------------------------------
_MAX_HANDLED = 10_000
_handled_upload_messages: OrderedDict[tuple[int, int], None] = OrderedDict()


def _claim_message(message: Message) -> bool:
    """Return True if this bot is the first to handle this message."""
    key = (message.chat.id, message.message_id)
    if key in _handled_upload_messages:
        return False
    _handled_upload_messages[key] = None
    # Evict oldest entries if over limit
    while len(_handled_upload_messages) > _MAX_HANDLED:
        _handled_upload_messages.popitem(last=False)
    return True


# -- /upload -- start media collection --------------------------

@upload_router.message(Command("upload"))
async def handle_upload(message: Message) -> None:
    chat_id = message.chat.id
    # Only work in groups/supergroups (storage group)
    if message.chat.type not in ("group", "supergroup"):
        await message.answer(
            "This command only works in the Storage Group.\n"
            "Add the bot to your storage group and use /upload there."
        )
        return

    # With multiple bots in the same group, only the first bot to claim the
    # message responds — prevents duplicate "Upload Mode Active" messages.
    if not _claim_message(message):
        return

    _prune_stale_sessions()
    _upload_sessions[chat_id] = {
        "_created_at": time.monotonic(),
        "state": "collecting",
        "media": [],
        "selected_bot": None,
        "selected_bot_token": None,
        "selected_category": None,
        "thumbnail_file_id": None,
        "title": "",
        "credit_mode": "per_item",   # per_pack | per_item
        "credit_cost": 0,            # total cost if per_pack
        "credit_per_item": 1,        # cost per item if per_item
    }

    await message.answer(
        "Upload Mode Active\n\n"
        "Send me photos and videos now.\n"
        "When done, send /publish to finalize.\n"
        "Send /cancel to abort.",
    )


# -- Collect media messages --

@upload_router.message(
    lambda m: m.chat.type in ("group", "supergroup")
    and (m.photo or m.video or m.document or m.animation)
    and m.chat.id in _upload_sessions
)
async def collect_media(message: Message) -> None:
    chat_id = message.chat.id
    session = _get_session(chat_id)

    if not session:
        return
    if not _claim_message(message):
        return

    if session["state"] == "awaiting_thumbnail":
        # Capture thumbnail file_id
        if message.photo:
            session["thumbnail_file_id"] = message.photo[-1].file_id
        elif message.video:
            session["thumbnail_file_id"] = message.video.file_id
        elif message.document:
            session["thumbnail_file_id"] = message.document.file_id
        elif message.animation:
            session["thumbnail_file_id"] = message.animation.file_id
        else:
            await message.answer("Please send a photo or video as the thumbnail.")
            return

        session["state"] = "confirming"
        media_count = len(session["media"])
        bot_name = session["selected_bot"] or "?"
        category = session["selected_category"] or "?"

        # Build credit info line
        credit_info = ""
        if category == "credits":
            mode = session.get("credit_mode", "per_item")
            if mode == "per_item":
                cpi = session.get("credit_per_item", 1)
                total = cpi * media_count
                credit_info = f"\n  Credit mode: Per Item ({cpi} credit/item = {total} total)"
            else:
                cost = session.get("credit_cost", media_count)
                credit_info = f"\n  Credit mode: Per Pack ({cost} credits flat)"

        await message.answer(
            "Thumbnail captured!\n\n"
            f"Summary:\n"
            f"  Media items: {media_count}\n"
            f"  Delivery bot: @{bot_name}\n"
            f"  Category: {category.upper()}"
            f"{credit_info}\n\n"
            "Now send a title for this content pack, or type /confirm to publish.",
        )
        return

    if session["state"] != "collecting":
        return

    # Collecting media items
    media_type = "photo"
    if message.video:
        media_type = "video"
    elif message.document:
        media_type = "document"
    elif message.animation:
        media_type = "animation"

    session["media"].append({
        "chat_id": chat_id,
        "message_id": message.message_id,
        "media_type": media_type,
    })

    count = len(session["media"])
    if count == 1:
        await message.answer(f"Collected 1 item. Keep sending or use /publish when done.")
    elif count % 5 == 0:
        await message.answer(f"Collected {count} items. Keep sending or use /publish when done.")


# -- /publish -- start the finalization flow --

@upload_router.message(Command("publish"))
async def handle_publish(message: Message) -> None:
    chat_id = message.chat.id
    if not _claim_message(message):
        return
    session = _get_session(chat_id)

    if not session or session["state"] != "collecting":
        await message.answer("No active upload session. Use /upload first.")
        return

    if not session["media"]:
        await message.answer("No media collected yet. Send photos/videos first.")
        return

    media_count = len(session["media"])
    session["state"] = "awaiting_bot"

    # Fetch registered bots from backend (internal, no auth)
    bots = await api_get("/internal/bots/active")
    if not bots:
        await message.answer("No delivery bots registered. Add a bot in the admin panel first.")
        session["state"] = "collecting"
        return

    buttons = []
    for b in bots:
        uname = b.get("username", "unknown")
        buttons.append([
            InlineKeyboardButton(
                text=f"@{uname}",
                callback_data=f"pub_bot:{uname}",
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer(
        f"{media_count} items collected.\n\nSelect a delivery bot for this content pack:",
        reply_markup=kb,
    )


# -- Bot selection callback --

@upload_router.callback_query(lambda c: c.data and c.data.startswith("pub_bot:"))
async def handle_bot_selection(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id if callback.message else 0
    session = _get_session(chat_id)

    if not session or session["state"] != "awaiting_bot":
        await callback.answer("No active publish flow.", show_alert=True)
        return

    bot_username = callback.data.split(":", 1)[1]
    session["selected_bot"] = bot_username
    session["state"] = "awaiting_category"
    await _safe_answer(callback)

    # Fetch active plan categories from backend
    tags = await api_get("/internal/plan-categories")
    if not tags:
        # Fallback: free + credits only
        tags = [
            {"tag": "free", "display_name": "Free"},
            {"tag": "credits", "display_name": "Credits"},
        ]

    buttons = []
    for t in tags:
        tag_val = t.get("tag", t.get("name", ""))
        display = t.get("display_name", tag_val)
        buttons.append([
            InlineKeyboardButton(
                text=display,
                callback_data=f"pub_cat:{tag_val}",
            )
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await callback.message.answer(
        f"Bot: @{bot_username}\n\n"
        "Now select an access category for this content:",
        reply_markup=kb,
    )


# -- Category selection callback --

@upload_router.callback_query(lambda c: c.data and c.data.startswith("pub_cat:"))
async def handle_category_selection(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id if callback.message else 0
    session = _get_session(chat_id)

    if not session or session["state"] != "awaiting_category":
        await callback.answer("No active publish flow.", show_alert=True)
        return

    category = callback.data.split(":", 1)[1]
    session["selected_category"] = category
    await _safe_answer(callback)

    if category == "credits":
        # Ask for credit mode
        session["state"] = "awaiting_credit_mode"
        buttons = [
            [InlineKeyboardButton(
                text="Per Item (charge per file)",
                callback_data="pub_cmode:per_item",
            )],
            [InlineKeyboardButton(
                text="Per Pack (flat charge for all)",
                callback_data="pub_cmode:per_pack",
            )],
        ]
        kb = InlineKeyboardMarkup(inline_keyboard=buttons)
        media_count = len(session["media"])
        await callback.message.answer(
            f"Category: CREDITS\n"
            f"This pack has {media_count} items.\n\n"
            "How should credits be charged?\n\n"
            "**Per Item** — credits charged × number of items\n"
            "**Per Pack** — flat credit charge for the entire pack",
            reply_markup=kb,
            parse_mode="Markdown",
        )
    else:
        # Non-credit categories go straight to thumbnail
        session["state"] = "awaiting_thumbnail"
        await callback.message.answer(
            f"Category: {category.upper()}\n\n"
            "Now send a thumbnail/preview image for the channel post.\n"
            "This will be the cover image shown in the main channel.",
        )


# -- Credit mode selection callback --

@upload_router.callback_query(lambda c: c.data and c.data.startswith("pub_cmode:"))
async def handle_credit_mode_selection(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id if callback.message else 0
    session = _get_session(chat_id)

    if not session or session["state"] != "awaiting_credit_mode":
        await callback.answer("No active credit mode selection.", show_alert=True)
        return

    mode = callback.data.split(":", 1)[1]  # per_item or per_pack
    session["credit_mode"] = mode
    session["state"] = "awaiting_credit_amount"
    await _safe_answer(callback)

    media_count = len(session["media"])
    if mode == "per_item":
        await callback.message.answer(
            f"Mode: Per Item\n\n"
            f"Send the credit cost **per item** (number only).\n"
            f"Default is 1 credit per item.\n"
            f"With {media_count} items, total cost = credits × {media_count}\n\n"
            "Send a number or type `1` for default:",
            parse_mode="Markdown",
        )
    else:
        await callback.message.answer(
            f"Mode: Per Pack\n\n"
            f"Send the total credit cost for the **entire pack** (number only).\n"
            f"Default is {media_count} credits (1 per item).\n\n"
            f"Send a number or type `{media_count}` for default:",
            parse_mode="Markdown",
        )


# -- Credit amount text handler --
# (handled by handle_text_in_session below, state == "awaiting_credit_amount")


# -- /confirm -- finalize and publish to channel --

@upload_router.message(Command("confirm"))
async def handle_confirm(message: Message) -> None:
    chat_id = message.chat.id
    if not _claim_message(message):
        return
    session = _get_session(chat_id)

    if not session or session["state"] != "confirming":
        await message.answer("Nothing to confirm. Use /upload -> /publish flow.")
        return

    await _do_publish(message, session)


# -- Text messages during confirming state (used as title) --

@upload_router.message(
    lambda m: m.chat.type in ("group", "supergroup")
    and m.text
    and not m.text.startswith("/")
    and m.chat.id in _upload_sessions
)
async def handle_text_in_session(message: Message) -> None:
    chat_id = message.chat.id
    session = _get_session(chat_id)

    if not session:
        return
    if not _claim_message(message):
        return

    # Handle credit amount input
    if session["state"] == "awaiting_credit_amount":
        text = message.text.strip()
        media_count = len(session["media"])
        try:
            amount = int(text)
            if amount < 1:
                amount = 1
        except ValueError:
            # Default: 1 per item
            amount = 1

        if session["credit_mode"] == "per_item":
            session["credit_per_item"] = amount
            session["credit_cost"] = 0  # will be ignored; per_item mode uses credit_per_item
            total = amount * media_count
            await message.answer(
                f"Credit per item: {amount}\n"
                f"Total cost for {media_count} items: {total} credits\n\n"
                "Now send a thumbnail/preview image for the channel post.",
            )
        else:
            session["credit_cost"] = amount
            session["credit_per_item"] = 0  # will be ignored; per_pack mode uses credit_cost
            await message.answer(
                f"Pack cost: {amount} credits (flat)\n\n"
                "Now send a thumbnail/preview image for the channel post.",
            )
        session["state"] = "awaiting_thumbnail"
        return

    if session["state"] == "confirming":
        session["title"] = message.text.strip()
        await _do_publish(message, session)


# -- /cancel -- abort upload session --

@upload_router.message(Command("cancel"))
async def handle_cancel(message: Message) -> None:
    chat_id = message.chat.id
    if not _claim_message(message):
        return
    if chat_id in _upload_sessions:
        del _upload_sessions[chat_id]
        await message.answer("Upload session cancelled.")
    else:
        await message.answer("No active upload session.")


# -- /announce -- broadcast a message to all users of a bot --------

# Per-chat announce state: {"state": "awaiting_bot"|"awaiting_text", "bot_id":..., "bot_token":...}
_announce_sessions: dict[int, dict] = {}


@upload_router.message(Command("announce"))
async def handle_announce(message: Message) -> None:
    """Start announcement flow in storage group: pick bot, then type message."""
    chat_id = message.chat.id
    if message.chat.type not in ("group", "supergroup"):
        await message.answer("This command only works in the Storage Group.")
        return
    if not _claim_message(message):
        return

    # Check if text was provided inline: /announce Hello everyone
    parts = (message.text or "").split(maxsplit=1)
    inline_text = parts[1].strip() if len(parts) > 1 else ""

    bots = await api_get("/internal/bots/active")
    if not bots:
        await message.answer("No bots registered. Add a bot in the admin panel first.")
        return

    _announce_sessions[chat_id] = {"_created_at": time.monotonic(), "state": "awaiting_bot", "inline_text": inline_text}

    buttons = []
    for b in bots:
        uname = b.get("username", "unknown")
        buttons.append([InlineKeyboardButton(text=f"@{uname}", callback_data=f"ann_bot:{uname}")])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons)
    await message.answer("Select which bot should send the announcement:", reply_markup=kb)


@upload_router.callback_query(lambda c: c.data and c.data.startswith("ann_bot:"))
async def handle_announce_bot_selection(callback: CallbackQuery) -> None:
    chat_id = callback.message.chat.id if callback.message else 0
    session = _announce_sessions.get(chat_id)
    if not session or session["state"] != "awaiting_bot":
        await callback.answer("No active announcement.", show_alert=True)
        return

    bot_username = callback.data.split(":", 1)[1]
    await _safe_answer(callback)

    # Fetch bot details (need the token for sending)
    bots = await api_get("/internal/bots/active")
    bot_info = None
    if bots:
        for b in bots:
            if b.get("username") == bot_username:
                bot_info = b
                break

    if not bot_info:
        await callback.message.answer(f"Bot @{bot_username} not found.")
        del _announce_sessions[chat_id]
        return

    session["bot_id"] = bot_info.get("id")
    session["bot_token"] = bot_info.get("token", "")
    session["bot_username"] = bot_username

    # If inline text was already provided, send immediately
    if session.get("inline_text"):
        await _send_announcement(callback.message, session, session["inline_text"])
        return

    session["state"] = "awaiting_text"
    await callback.message.answer(
        f"Bot: @{bot_username}\n\n"
        "Now type the announcement message to send to all users.\n"
        "Supports Markdown formatting.\n\n"
        "Type /cancelannounce to abort."
    )


@upload_router.message(Command("cancelannounce"))
async def handle_cancel_announce(message: Message) -> None:
    chat_id = message.chat.id
    if not _claim_message(message):
        return
    if chat_id in _announce_sessions:
        del _announce_sessions[chat_id]
        await message.answer("Announcement cancelled.")
    else:
        await message.answer("No active announcement.")


@upload_router.message(
    lambda m: m.chat.type in ("group", "supergroup")
    and m.text
    and not m.text.startswith("/")
    and m.chat.id in _announce_sessions
)
async def handle_announce_text(message: Message) -> None:
    """Capture announcement text when in awaiting_text state."""
    chat_id = message.chat.id
    session = _announce_sessions.get(chat_id)
    if not session or session["state"] != "awaiting_text":
        return
    if not _claim_message(message):
        return

    await _send_announcement(message, session, message.text.strip())


async def _send_announcement(message: Message, session: dict, text: str) -> None:
    """Send announcement via backend internal API."""
    chat_id = message.chat.id
    bot_id = session.get("bot_id")
    bot_username = session.get("bot_username", "?")

    await message.answer(f"Sending announcement via @{bot_username}...")

    try:
        result = await api_post(f"/internal/bots/{bot_id}/announce", {"message": text})
        if result and not result.get("_error"):
            await message.answer(
                f"Announcement complete!\n"
                f"Sent: {result.get('sent', 0)}\n"
                f"Failed: {result.get('failed', 0)}"
            )
        else:
            err = result.get("message", "Unknown error") if result else "No response"
            await message.answer(f"Announcement failed: {err}")
    except Exception as e:
        logger.error("Announce failed: %s", e)
        await message.answer(f"Announcement error: {e}")

    _announce_sessions.pop(chat_id, None)


# -- Internal: do the actual publish --

async def _do_publish(message: Message, session: dict) -> None:
    """Create content pack in backend, generate deep link, and post to channel."""
    chat_id = message.chat.id
    bot_username = session["selected_bot"]
    category = session["selected_category"]
    media_items = session["media"]
    title = session.get("title") or f"Content Pack ({len(media_items)} items)"

    await message.answer("Publishing...")

    # 1. Create content pack via internal endpoint (no auth needed)
    credit_mode = session.get("credit_mode", "per_item")
    credit_per_item = session.get("credit_per_item", 1)
    credit_cost = session.get("credit_cost", 0)

    # Calculate sensible defaults for credits category
    if category == "credits":
        if credit_mode == "per_item" and credit_per_item < 1:
            credit_per_item = 1
        if credit_mode == "per_pack" and credit_cost < 1:
            credit_cost = len(media_items)  # default 1 per item
    else:
        credit_mode = "per_item"
        credit_per_item = 0
        credit_cost = 0

    pack_result = await api_post("/internal/content-packs", {
        "title": title,
        "access_type": category,
        "credit_cost": credit_cost,
        "credit_mode": credit_mode,
        "credit_per_item": credit_per_item,
    })

    if not pack_result:
        await message.answer("Failed to create content pack in backend. Check logs.")
        return

    pack_id = pack_result.get("id")
    logger.info("Created content pack id=%s title=%s", pack_id, title)

    # 2. Add each media item to the pack via internal endpoint
    for idx, item in enumerate(media_items):
        result = await api_post("/internal/pack-items", {
            "pack_id": pack_id,
            "storage_chat_id": item["chat_id"],
            "storage_message_id": item["message_id"],
            "media_type": item["media_type"],
            "order_index": idx,
        })
        if not result:
            logger.warning("Failed to add item %d to pack %s", idx, pack_id)

    # 3. Generate a token (deep link) for this pack via internal endpoint
    token_result = await api_post("/internal/tokens", {
        "pack_id": pack_id,
        "single_use": False,
    })

    if not token_result:
        await message.answer(f"Pack #{pack_id} created but deep link generation failed.")
        del _upload_sessions[chat_id]
        return

    token_str = token_result.get("token", "")
    deep_link = f"https://t.me/{bot_username}?start={token_str}"
    logger.info("Generated deep link: %s", deep_link)

    # 4. Auto-post to the main channel
    channel_posted = False
    try:
        # Get ALL settings via internal endpoint (includes content_channel_id)
        settings = await api_get("/internal/settings/all")
        channel_id = ""
        if isinstance(settings, list):
            for s in settings:
                if s.get("key") == "content_channel_id":
                    channel_id = s.get("value", "")

        if channel_id:
            bot: Bot = message.bot  # type: ignore
            thumbnail_file_id = session.get("thumbnail_file_id")

            # Build inline keyboard with deep link button
            if category == "credits" and credit_cost > 0:
                btn_label = f"Watch for {credit_cost} Credits"
            else:
                btn_label = "Access Content"
            link_kb = InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=btn_label, url=deep_link)]
            ])

            caption = (
                f"{title}\n"
                f"{category.upper()} | {len(media_items)} items"
            )

            if thumbnail_file_id:
                try:
                    # Send thumbnail as photo with caption and deep link button
                    await bot.send_photo(
                        chat_id=int(channel_id),
                        photo=thumbnail_file_id,
                        caption=caption,
                        reply_markup=link_kb,
                    )
                    channel_posted = True
                except Exception as e:
                    logger.warning("Failed to send photo to channel %s: %s", channel_id, e)

            if not channel_posted:
                # Fallback: just send text message with deep link
                try:
                    await bot.send_message(
                        chat_id=int(channel_id),
                        text=f"{caption}\n\n{deep_link}",
                        reply_markup=link_kb,
                    )
                    channel_posted = True
                except Exception as e:
                    logger.warning("Failed to send message to channel %s: %s", channel_id, e)
        else:
            logger.warning("content_channel_id not configured in settings")
    except Exception as e:
        logger.warning("Channel post failed: %s", e)

    # 5. Confirmation message in storage group
    status_lines = [
        "Published!\n",
        f"Pack: {title} (#{pack_id})",
        f"Category: {category.upper()}",
        f"Items: {len(media_items)}",
        f"Bot: @{bot_username}",
        f"Deep Link: {deep_link}",
    ]
    if channel_posted:
        status_lines.append("\nPosted to main channel.")
    else:
        status_lines.append(
            "\nChannel post failed. Make sure:\n"
            "  1. content_channel_id is set in Settings\n"
            "  2. The bot is an admin in the channel"
        )

    await message.answer("\n".join(status_lines))

    # Cleanup session
    del _upload_sessions[chat_id]
