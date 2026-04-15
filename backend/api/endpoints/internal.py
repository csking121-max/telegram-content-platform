"""
Internal / service-to-service endpoints — protected by X-Internal-Key header.

These are intended for the Telegram gateway and workers to call over the
internal Docker/LAN network. They should NOT be exposed publicly.
"""
from __future__ import annotations

import asyncio
import logging
import secrets as _secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import httpx
from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel
from sqlalchemy import select, delete as sa_delete
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.database import AsyncSessionLocal
from backend.dependencies import get_db
from backend.services.bot_service import BotService
from backend.services.content_service import ContentService
from backend.services.platform_settings_service import PlatformSettingsService
from backend.engines.token_service import TokenService
from backend.schemas.content_pack import ContentPackCreate, ContentPackRead
from backend.schemas.pack_item import PackItemCreate, PackItemRead
from backend.schemas.token import TokenRead

logger = logging.getLogger(__name__)
router = APIRouter()

TELEGRAM_API = "https://api.telegram.org"
TELEGRAM_LOCAL_API = __import__("os").environ.get("TELEGRAM_LOCAL_API_URL", "")


# ── Internal API authentication ──────────────────────────────

async def verify_internal_key(
    x_internal_key: str = Header(default=""),
) -> None:
    """Validate the X-Internal-Key header against settings.INTERNAL_API_KEY.
    Skipped when INTERNAL_API_KEY is not configured (dev mode).
    """
    configured = settings.INTERNAL_API_KEY
    if not configured:
        if not settings.DEBUG:
            raise HTTPException(
                status_code=503,
                detail="Internal API key not configured. Set INTERNAL_API_KEY env var.",
            )
        return  # Allow in DEBUG mode only
    if not _secrets.compare_digest(x_internal_key, configured):
        raise HTTPException(status_code=403, detail="Invalid internal API key")


# ── Bot listing ──────────────────────────────────────────────

class InternalBotInfo(BaseModel):
    id: int
    username: str
    token: str
    hmac_secret: str


@router.get("/bots/active", response_model=list[InternalBotInfo])
async def list_active_bots_internal(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Return all active bots — used by the telegram gateway to start polling."""
    svc = BotService(db)
    bots = await svc.list_active()
    return [
        InternalBotInfo(
            id=b.id,
            username=b.bot_username,
            token=b.bot_token,
            hmac_secret=b.webhook_secret,
        )
        for b in bots
    ]


# ── Content packs (gateway upload flow) ─────────────────────

class InternalPackCreate(BaseModel):
    title: str
    description: Optional[str] = None
    access_type: str = "free"
    credit_cost: int = 0
    credit_mode: str = "per_item"   # per_pack | per_item
    credit_per_item: int = 1
    deletion_seconds: Optional[int] = None


@router.post("/content-packs", response_model=ContentPackRead, status_code=201)
async def create_pack_internal(
    body: InternalPackCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Create a content pack — used by gateway upload handler."""
    svc = ContentService(db)
    pack = await svc.create_pack(ContentPackCreate(**body.model_dump()))
    await db.commit()
    await db.refresh(pack)
    return pack


# ── Pack items (gateway upload flow) ────────────────────────

@router.post("/pack-items", response_model=PackItemRead, status_code=201)
async def add_item_internal(
    body: PackItemCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Add a single item to a content pack — used by gateway upload handler."""
    svc = ContentService(db)
    item = await svc.add_item(body)
    await db.commit()
    await db.refresh(item)
    return item


@router.post("/pack-items/bulk", response_model=list[PackItemRead], status_code=201)
async def add_items_bulk_internal(
    items: list[PackItemCreate],
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Add multiple items to a content pack at once."""
    if not items:
        return []
    svc = ContentService(db)
    result = await svc.add_items_bulk(items[0].pack_id, items)
    await db.commit()
    for item in result:
        await db.refresh(item)
    return result


# ── Tokens (gateway upload flow) ────────────────────────────

class InternalTokenCreate(BaseModel):
    pack_id: int
    single_use: bool = False
    bound_user_id: Optional[int] = None


@router.post("/tokens", response_model=TokenRead, status_code=201)
async def create_token_internal(
    body: InternalTokenCreate,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Create a token (deep link) for a content pack — used by gateway upload handler."""
    svc = TokenService(db)
    token = await svc.create(
        pack_id=body.pack_id,
        single_use=body.single_use,
        bound_user_id=body.bound_user_id,
    )
    await db.commit()
    await db.refresh(token)
    return token


# ── Membership plan categories (gateway upload flow) ────────

@router.get("/plan-categories")
async def list_plan_categories_internal(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Return distinct access_types from active plans — used by gateway upload handler."""
    from backend.models.membership_plan import MembershipPlan
    result = await db.execute(
        select(MembershipPlan.access_type, MembershipPlan.display_name, MembershipPlan.tier_level)
        .where(MembershipPlan.is_active == True)
        .order_by(MembershipPlan.tier_level, MembershipPlan.sort_order)
    )
    seen = set()
    categories = [
        {"tag": "free", "display_name": "Free"},
        {"tag": "credits", "display_name": "Credits (free for members)"},
        {"tag": "credits_only", "display_name": "Credits Only (always costs credits)"},
    ]
    seen.update(("free", "credits", "credits_only"))
    for access_type, display_name, _ in result.all():
        if access_type not in seen:
            categories.append({"tag": access_type, "display_name": display_name or access_type.title()})
            seen.add(access_type)
    return categories


# ── Platform settings (gateway needs channel ID, etc.) ──────

@router.get("/settings/all")
async def get_all_settings_internal(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Return ALL platform settings — internal use only."""
    svc = PlatformSettingsService(db)
    await svc.seed_defaults()
    await db.commit()
    all_settings = await svc.get_all()
    return [{"key": s.key, "value": s.value} for s in all_settings]


# ── Pack items lookup (gateway delivery) ────────────────────

@router.get("/pack-items/{pack_id}", response_model=list[PackItemRead])
async def get_pack_items_internal(
    pack_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Return all items in a content pack — used by gateway for direct delivery."""
    svc = ContentService(db)
    items = await svc.get_items(pack_id)
    return items


# ── Content proxy (cross-bot delivery fallback) ─────────────

class _CopyRequest(BaseModel):
    chat_id: int
    storage_chat_id: int
    storage_message_id: int


@router.post("/copy-via-storage-bot")
async def copy_via_storage_bot(
    body: _CopyRequest,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Use the storage bot (first active bot) to copyMessage to user.

    Instant delivery — no download/re-upload needed. Works because the
    storage bot is a member of the storage group AND the user has /start'd
    at least one bot on the platform.
    """
    bot_svc = BotService(db)
    bots = await bot_svc.list_active()
    if not bots:
        raise HTTPException(503, "No active bots")
    storage_bot = bots[0]

    result = await _tg_request(storage_bot.bot_token, "copyMessage", {
        "chat_id": body.chat_id,
        "from_chat_id": body.storage_chat_id,
        "message_id": body.storage_message_id,
    })

    if result and result.get("ok"):
        return {"ok": True, "message_id": result["result"]["message_id"]}

    return {"ok": False, "error": "copyMessage failed — user may not have started the storage bot"}


@router.post("/copy-via-storage-bot/batch")
async def copy_batch_via_storage_bot(
    items: list[_CopyRequest],
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Batch copyMessage via storage bot — all items sent in parallel."""
    bot_svc = BotService(db)
    bots = await bot_svc.list_active()
    if not bots:
        raise HTTPException(503, "No active bots")
    storage_bot = bots[0]
    token = storage_bot.bot_token

    async def _copy_one(item: _CopyRequest) -> dict:
        result = await _tg_request(token, "copyMessage", {
            "chat_id": item.chat_id,
            "from_chat_id": item.storage_chat_id,
            "message_id": item.storage_message_id,
        })
        if result and result.get("ok"):
            return {"ok": True, "message_id": result["result"]["message_id"]}
        return {"ok": False}

    results = await asyncio.gather(*[_copy_one(it) for it in items])
    return list(results)


@router.get("/content-proxy/{storage_chat_id}/{storage_message_id}")
async def proxy_content(
    storage_chat_id: int,
    storage_message_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Download content from storage group via first active bot.

    Uses stored file_id from query params when available (fast path).
    Falls back to forwardMessage extraction if file_id not provided.
    """
    from starlette.responses import Response
    from starlette.requests import Request
    from fastapi import Request as FastAPIRequest

    bot_svc = BotService(db)
    bots = await bot_svc.list_active()
    if not bots:
        raise HTTPException(503, "No active bots")
    storage_bot = bots[0]
    token = storage_bot.bot_token

    # Check if file_id and media_type were passed as query params
    # (set by gateway when pack_item has stored file_id)
    from starlette.requests import Request as _Req

    file_id = None
    media_type = "document"

    # Try to get from pack_items table first
    cs = ContentService(db)
    from sqlalchemy import select as sa_select
    from backend.models.pack_item import PackItem as _PI
    result = await db.execute(
        sa_select(_PI).where(
            _PI.storage_chat_id == storage_chat_id,
            _PI.storage_message_id == storage_message_id,
        ).limit(1)
    )
    pack_item = result.scalar_one_or_none()
    if pack_item and pack_item.file_id:
        file_id = pack_item.file_id
        media_type = pack_item.media_type or "document"
    else:
        # Fallback: forward message to extract file_id
        fwd = await _tg_request(token, "forwardMessage", {
            "chat_id": storage_chat_id,
            "from_chat_id": storage_chat_id,
            "message_id": storage_message_id,
        })
        if not fwd or not fwd.get("ok"):
            raise HTTPException(502, "Cannot access storage content")

        msg = fwd["result"]
        fwd_msg_id = msg.get("message_id")

        if msg.get("photo"):
            photos = msg["photo"]
            file_id = photos[-1]["file_id"] if photos else None
            media_type = "photo"
        elif msg.get("video"):
            file_id = msg["video"].get("file_id")
            media_type = "video"
        elif msg.get("animation"):
            file_id = msg["animation"].get("file_id")
            media_type = "animation"
        elif msg.get("document"):
            file_id = msg["document"].get("file_id")
            media_type = "document"
        elif msg.get("audio"):
            file_id = msg["audio"].get("file_id")
            media_type = "audio"

        # Download FIRST, then clean up forwarded message
        try:
            dl_result = await _download_file(token, file_id, media_type)
        finally:
            if fwd_msg_id:
                await _tg_request(token, "deleteMessage", {
                    "chat_id": storage_chat_id,
                    "message_id": fwd_msg_id,
                })
        if dl_result:
            return dl_result
        raise HTTPException(502, "Download failed")

    if not file_id:
        raise HTTPException(502, "No file found in storage message")

    dl_result = await _download_file(token, file_id, media_type)
    if dl_result:
        return dl_result
    raise HTTPException(502, "Download failed")


async def _download_file(token: str, file_id: str | None, media_type: str):
    """Download file bytes via Telegram getFile API.

    Falls back to Local Bot API when cloud getFile returns 'file is too big' (>20 MB).
    """
    from starlette.responses import Response

    if not file_id:
        return None
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            # Try cloud API first
            resp = await client.post(
                f"{TELEGRAM_API}/bot{token}/getFile",
                json={"file_id": file_id},
            )
            if resp.status_code != 200:
                body = resp.text[:200]
                if "file is too big" in body and TELEGRAM_LOCAL_API:
                    # File >20 MB — retry via Local Bot API which has no size limit
                    logger.info("getFile: file too big for cloud API, retrying via Local Bot API")
                    resp = await client.post(
                        f"{TELEGRAM_LOCAL_API}/bot{token}/getFile",
                        json={"file_id": file_id},
                    )
                    if resp.status_code != 200:
                        logger.warning("getFile via Local API also failed: %s %s", resp.status_code, resp.text[:200])
                        return None
                    file_path = resp.json().get("result", {}).get("file_path")
                    if not file_path:
                        return None
                    dl = await client.get(f"{TELEGRAM_LOCAL_API}/file/bot{token}/{file_path}")
                    if dl.status_code != 200:
                        return None
                    return Response(
                        content=dl.content,
                        media_type="application/octet-stream",
                        headers={"X-Media-Type": media_type},
                    )
                logger.warning("getFile failed: %s %s", resp.status_code, body)
                return None
            file_path = resp.json().get("result", {}).get("file_path")
            if not file_path:
                return None
            dl = await client.get(f"{TELEGRAM_API}/file/bot{token}/{file_path}")
            if dl.status_code != 200:
                return None
            return Response(
                content=dl.content,
                media_type="application/octet-stream",
                headers={"X-Media-Type": media_type},
            )
    except Exception as e:
        logger.error("Content proxy download failed: %s", e)
        return None


# ── Message tracking (gateway reports in/out message IDs) ───

class _TrackMsg(BaseModel):
    bot_id: int
    chat_id: int
    message_id: int
    direction: str = "out"  # "in" | "out"


@router.post("/track-messages", status_code=201)
async def track_messages(
    items: list[_TrackMsg],
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Batch-insert tracked message IDs from the gateway."""
    from backend.models.bot_message import BotMessage

    if not items:
        return {"tracked": 0}

    for it in items:
        db.add(BotMessage(
            bot_id=it.bot_id,
            chat_id=it.chat_id,
            message_id=it.message_id,
            direction=it.direction,
        ))
    await db.commit()
    return {"tracked": len(items)}


# ── Telegram API helper ─────────────────────────────────────

async def _tg_request(token: str, method: str, payload: dict) -> dict | None:
    """Call Telegram Bot API. Returns the JSON result or None on failure."""
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    # These Telegram errors are normal operational events, not worth WARNING spam.
    _SILENT_ERRORS = {
        "chat not found",
        "bot was blocked by the user",
        "user is deactivated",
        "bot can't initiate conversation with a user",
        "have no rights to send a message",
        "message to delete not found",
        "message can't be deleted",
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json()
            body = resp.text[:300]
            body_lower = body.lower()
            if any(err in body_lower for err in _SILENT_ERRORS):
                logger.debug("TG %s → %s (expected): %s", method, resp.status_code, body)
            else:
                logger.warning("TG %s → %s: %s", method, resp.status_code, body)
    except Exception as e:
        logger.warning("TG %s failed: %s", method, e)
    return None


async def _get_bot_user_tg_ids(bot_id: int, db: AsyncSession) -> list[int]:
    """Get all user telegram_ids to contact for a bot.

    Uses the users table (all registered users) plus any chat_ids
    captured via bot_messages tracking for that specific bot.
    Falls back gracefully when tables are empty.
    """
    from backend.models.user import User
    from backend.models.bot_message import BotMessage

    # All registered platform users — stream in batches to limit memory
    tg_ids: set[int] = set()
    batch_size = 500
    offset = 0
    while True:
        result = await db.execute(
            select(User.telegram_id).distinct().limit(batch_size).offset(offset)
        )
        rows = result.all()
        if not rows:
            break
        tg_ids.update(row[0] for row in rows)
        offset += batch_size

    # Also include any private-chat chat_ids from bot_messages for this bot
    # (chat_id == telegram_id for private chats)
    result2 = await db.execute(
        select(BotMessage.chat_id)
        .where(BotMessage.bot_id == bot_id)
        .distinct()
    )
    tg_ids.update(row[0] for row in result2.all())

    return list(tg_ids)


# ── Announce to all users of a bot ──────────────────────────

class _AnnounceBody(BaseModel):
    message: str


@router.post("/bots/{bot_id}/announce")
async def announce_to_users(
    bot_id: int,
    body: _AnnounceBody,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Send an announcement to all users of a bot."""
    svc = BotService(db)
    bot = await svc.get_by_id(bot_id)
    if not bot:
        return {"detail": "Bot not found", "sent": 0, "failed": 0}

    telegram_ids = await _get_bot_user_tg_ids(bot_id, db)
    if not telegram_ids:
        return {"detail": "No users found", "sent": 0, "failed": 0}

    from backend.models.bot_message import BotMessage

    sent = 0
    failed = 0
    for tg_id in telegram_ids:
        r = await _tg_request(bot.bot_token, "sendMessage", {
            "chat_id": tg_id,
            "text": body.message,
            "parse_mode": "Markdown",
        })
        if r and r.get("ok"):
            sent += 1
            # Track the outgoing message so cleanup can find it
            msg_id = r.get("result", {}).get("message_id")
            if msg_id:
                db.add(BotMessage(bot_id=bot_id, chat_id=tg_id, message_id=msg_id, direction="out"))
        else:
            failed += 1
        if (sent + failed) % 25 == 0:
            await asyncio.sleep(1)

    await db.commit()
    logger.info("Announce bot=%d: sent=%d failed=%d", bot_id, sent, failed)
    return {"detail": "Announcement sent", "sent": sent, "failed": failed}


# ── Clear all tracked messages for a bot ────────────────────

@router.post("/bots/{bot_id}/clear-messages")
async def clear_bot_messages(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Delete tracked messages (within 48h Telegram limit) then purge DB records."""
    from backend.models.bot_message import BotMessage

    svc = BotService(db)
    bot = await svc.get_by_id(bot_id)
    if not bot:
        return {"detail": "Bot not found", "deleted": 0, "failed": 0}

    # Use naive UTC for SQLite datetime comparison (SQLite stores naive UTC strings)
    cutoff_48h = datetime.utcnow() - timedelta(hours=48)
    q = select(BotMessage).where(BotMessage.bot_id == bot_id, BotMessage.created_at >= cutoff_48h)
    result = await db.execute(q)
    messages = list(result.scalars().all())

    deleted = 0
    failed = 0
    for msg in messages:
        r = await _tg_request(bot.bot_token, "deleteMessage", {
            "chat_id": msg.chat_id,
            "message_id": msg.message_id,
        })
        if r and r.get("ok"):
            deleted += 1
        else:
            failed += 1
        if (deleted + failed) % 25 == 0:
            await asyncio.sleep(1)

    # Always purge all tracked messages for this bot from DB
    await db.execute(sa_delete(BotMessage).where(BotMessage.bot_id == bot_id))
    await db.commit()

    logger.info("Clear bot=%d: deleted=%d failed=%d", bot_id, deleted, failed)
    return {"detail": "Messages cleared", "deleted": deleted, "failed": failed}


# ── Send welcome message to all users of a bot ─────────────

@router.post("/bots/{bot_id}/send-welcome")
async def send_welcome(
    bot_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Send the platform welcome message to all users of a bot."""
    svc = BotService(db)
    bot = await svc.get_by_id(bot_id)
    if not bot:
        return {"detail": "Bot not found", "sent": 0, "failed": 0}

    settings_svc = PlatformSettingsService(db)
    welcome_msg = await settings_svc.get("bot_welcome_message") or "Choose an option below:"
    platform_name = await settings_svc.get("platform_name") or "Content Platform"
    content_channel_link = await settings_svc.get("content_channel_link") or ""

    # Build inline keyboard matching the gateway's _build_main_menu
    rows = []
    row1 = []
    if content_channel_link:
        row1.append({"text": "Browse Content", "url": content_channel_link})
    row1.append({"text": "Buy Membership", "callback_data": "menu:plans"})
    rows.append(row1)
    rows.append([
        {"text": "My Profile", "callback_data": "menu:profile"},
        {"text": "My Credits", "callback_data": "menu:credits"},
    ])
    rows.append([
        {"text": "Buy Credits", "callback_data": "menu:buy_credits"},
        {"text": "Watch Ad (Free)", "callback_data": "menu:watch_ad"},
    ])
    rows.append([
        {"text": "Payment Status", "callback_data": "menu:mystatus"},
        {"text": "Help", "callback_data": "menu:help"},
    ])

    telegram_ids = await _get_bot_user_tg_ids(bot_id, db)
    if not telegram_ids:
        return {"detail": "No users found", "sent": 0, "failed": 0}

    from backend.models.bot_message import BotMessage

    sent = 0
    failed = 0
    def _md_escape(t: str) -> str:
        """Escape Markdown v1 special chars in dynamic strings."""
        for ch in ("_", "*", "`", "["):
            t = t.replace(ch, f"\\{ch}")
        return t

    safe_platform = _md_escape(platform_name)

    for tg_id in telegram_ids:
        # Resolve placeholders (user-specific names not available in bulk send)
        resolved_msg = welcome_msg.replace("{platform_name}", platform_name)
        resolved_msg = resolved_msg.replace("{user_name}", "there")
        resolved_msg = resolved_msg.replace("{username}", "there")
        resolved_msg = resolved_msg.replace("{user_id}", str(tg_id))
        safe_msg = _md_escape(resolved_msg)
        text = f"Hey!\n\nWelcome to *{safe_platform}*\n\n{safe_msg}"
        r = await _tg_request(bot.bot_token, "sendMessage", {
            "chat_id": tg_id,
            "text": text,
            "parse_mode": "Markdown",
            "reply_markup": {"inline_keyboard": rows},
        })
        if r and r.get("ok"):
            sent += 1
            # Track the outgoing message so cleanup can find it
            msg_id = r.get("result", {}).get("message_id")
            if msg_id:
                db.add(BotMessage(bot_id=bot_id, chat_id=tg_id, message_id=msg_id, direction="out"))
        else:
            failed += 1
        if (sent + failed) % 25 == 0:
            await asyncio.sleep(1)

    await db.commit()
    logger.info("Welcome bot=%d: sent=%d failed=%d", bot_id, sent, failed)
    return {"detail": "Welcome messages sent", "sent": sent, "failed": failed}


# ── Auto-cleanup background job ─────────────────────────────

async def auto_cleanup_all_bots() -> None:
    """
    Run once: for every bot that has cleanup_hours > 0, delete tracked
    messages that are older than cleanup_hours but within the Telegram
    48-hour deletion window.  Called periodically from the backend lifespan.
    """
    from backend.models.bot import Bot as BotModel
    from backend.models.bot_message import BotMessage

    async with AsyncSessionLocal() as db:
        try:
            result = await db.execute(
                select(BotModel).where(BotModel.cleanup_hours > 0, BotModel.status == "active")
            )
            bots = list(result.scalars().all())
        except Exception as exc:
            logger.warning("auto_cleanup: failed to query bots: %s", exc)
            return

        # Use naive UTC — SQLite stores datetime without timezone info
        now = datetime.utcnow()
        tg_48h_cutoff = now - timedelta(hours=48)

        for bot in bots:
            cutoff = now - timedelta(hours=bot.cleanup_hours)

            q = (
                select(BotMessage)
                .where(
                    BotMessage.bot_id == bot.id,
                    BotMessage.created_at <= cutoff,
                    BotMessage.created_at >= tg_48h_cutoff,
                )
            )
            result2 = await db.execute(q)
            messages = list(result2.scalars().all())

            if not messages:
                continue

            deleted = 0
            failed = 0
            ids_to_delete: list[int] = []

            for msg in messages:
                r = await _tg_request(bot.bot_token, "deleteMessage", {
                    "chat_id": msg.chat_id,
                    "message_id": msg.message_id,
                })
                if r and r.get("ok"):
                    deleted += 1
                    ids_to_delete.append(msg.id)
                else:
                    # Message may already be gone; still remove from DB
                    failed += 1
                    ids_to_delete.append(msg.id)
                if len(ids_to_delete) % 25 == 0:
                    await asyncio.sleep(1)

            if ids_to_delete:
                await db.execute(
                    sa_delete(BotMessage).where(BotMessage.id.in_(ids_to_delete))
                )
                await db.commit()

            logger.info(
                "auto_cleanup bot=%d (@%s): deleted=%d failed=%d",
                bot.id, bot.bot_username, deleted, failed,
            )


# ── Bug reports (gateway → backend) ─────────────────────────

class _BugReportBody(BaseModel):
    telegram_id: int
    username: str | None = None
    first_name: str | None = None
    report: str


@router.post("/bug-reports", status_code=201)
async def submit_bug_report(
    body: _BugReportBody,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Submit a bug report from a user via the gateway."""
    from backend.models.bug_report import BugReport
    bug = BugReport(
        telegram_id=body.telegram_id,
        username=body.username,
        first_name=body.first_name,
        report=body.report,
    )
    db.add(bug)
    await db.commit()
    return {"detail": "Bug report submitted", "id": bug.id}


# ── Tutorials (gateway → backend) ───────────────────────────

@router.get("/tutorials")
async def list_tutorials_internal(
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Return all tutorials for the bot menu."""
    from backend.models.tutorial import Tutorial
    result = await db.execute(
        select(Tutorial).order_by(Tutorial.sort_order, Tutorial.id)
    )
    tutorials = result.scalars().all()
    return [
        {
            "id": t.id,
            "question": t.question,
            "storage_chat_id": t.storage_chat_id,
            "storage_message_id": t.storage_message_id,
            "file_id": t.file_id,
        }
        for t in tutorials
    ]
