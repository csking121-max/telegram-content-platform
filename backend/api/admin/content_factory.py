"""
Admin Content Factory — bulk upload & publish pipeline.

Endpoints for uploading files to Telegram Storage Group
and publishing them as content packs with deep links.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.dependencies import get_db
from backend.models.token import Token
from backend.services.bot_service import BotService
from backend.services.content_service import ContentService
from backend.services.platform_settings_service import PlatformSettingsService
from backend.engines.token_service import TokenService
from backend.schemas.content_pack import ContentPackCreate, ContentPackUpdate
from backend.schemas.pack_item import PackItemCreate

logger = logging.getLogger(__name__)
router = APIRouter()

TELEGRAM_API = "https://api.telegram.org"

# ── In-memory publish job tracker ────────────────────────────
_publish_jobs: dict[str, dict] = {}


# ── Telegram helpers ─────────────────────────────────────────

async def _get_first_active_bot(db: AsyncSession):
    """Get the first active bot from DB for API calls."""
    svc = BotService(db)
    bots = await svc.list_active()
    if not bots:
        raise HTTPException(503, "No active bots configured")
    return bots[0]


async def _get_storage_group_id(db: AsyncSession) -> int:
    """Get storage_group_id from platform settings."""
    svc = PlatformSettingsService(db)
    val = await svc.get("storage_group_id")
    if not val:
        raise HTTPException(
            503,
            "storage_group_id not configured. Set it in Settings → Content.",
        )
    return int(val)


async def _tg_upload_file(
    token: str,
    method: str,
    data: dict,
    files: dict,
    timeout: int = 120,
) -> dict | None:
    """Call Telegram Bot API with file upload (multipart/form-data)."""
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(url, data=data, files=files)
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "TG %s → %s: %s", method, resp.status_code, resp.text[:400],
            )
    except Exception as e:
        logger.warning("TG %s failed: %s", method, e)
    return None


async def _tg_request(token: str, method: str, payload: dict) -> dict | None:
    """Call Telegram Bot API with JSON payload."""
    url = f"{TELEGRAM_API}/bot{token}/{method}"
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(url, json=payload)
            if resp.status_code == 200:
                return resp.json()
            logger.warning(
                "TG %s → %s: %s", method, resp.status_code, resp.text[:400],
            )
    except Exception as e:
        logger.warning("TG %s failed: %s", method, e)
    return None


# ── Upload helpers ────────────────────────────────────────────

def _detect_media_type(content_type: str) -> str:
    """Map MIME content_type to Telegram media category."""
    ct = content_type.lower()
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("image/gif"):
        return "animation"
    if ct.startswith("image/"):
        return "photo"
    # Everything else (pdf, zip, etc.) → document
    return "document"


def _tg_method_for_type(media_type: str) -> tuple[str, str]:
    """Return (Telegram API method, multipart field name) for media_type."""
    return {
        "video": ("sendVideo", "video"),
        "photo": ("sendPhoto", "photo"),
        "animation": ("sendAnimation", "animation"),
        "document": ("sendDocument", "document"),
    }.get(media_type, ("sendDocument", "document"))


# ── Upload endpoints ─────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload any file to the Telegram Storage Group. Returns storage metadata."""
    ct = file.content_type or "application/octet-stream"
    media_type = _detect_media_type(ct)

    bot = await _get_first_active_bot(db)
    storage_group_id = await _get_storage_group_id(db)

    file_bytes = await file.read()
    if len(file_bytes) > 50 * 1024 * 1024:
        raise HTTPException(413, "File must be under 50 MB")

    tg_method, field_name = _tg_method_for_type(media_type)
    extra_data: dict = {}
    if media_type == "video":
        extra_data["supports_streaming"] = "true"

    result = await _tg_upload_file(
        bot.bot_token,
        tg_method,
        data={"chat_id": str(storage_group_id), **extra_data},
        files={field_name: (file.filename or "file", file_bytes, ct)},
    )

    if not result or not result.get("ok"):
        detail = "Failed to upload file to Telegram storage group"
        if result and result.get("description"):
            detail += f": {result['description']}"
        raise HTTPException(502, detail)

    msg = result["result"]

    # Extract file_id from the relevant message field
    file_id = ""
    info: dict = {}
    if media_type == "video":
        info = msg.get("video") or {}
        file_id = info.get("file_id", "")
    elif media_type == "photo":
        photos = msg.get("photo") or []
        file_id = photos[-1]["file_id"] if photos else ""
    elif media_type == "animation":
        info = msg.get("animation") or {}
        file_id = info.get("file_id", "")
    else:  # document
        info = msg.get("document") or {}
        file_id = info.get("file_id", "")

    return {
        "storage_chat_id": storage_group_id,
        "storage_message_id": msg["message_id"],
        "file_id": file_id,
        "filename": file.filename,
        "media_type": media_type,
        "duration": info.get("duration"),
        "width": info.get("width"),
        "height": info.get("height"),
    }


@router.post("/upload-thumbnail")
async def upload_thumbnail(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a thumbnail image to Telegram Storage Group. Returns file_id."""
    ct = file.content_type or ""
    if not ct.startswith("image/"):
        raise HTTPException(400, f"Only image files accepted (got {ct})")

    bot = await _get_first_active_bot(db)
    storage_group_id = await _get_storage_group_id(db)

    img_bytes = await file.read()
    if len(img_bytes) > 10 * 1024 * 1024:
        raise HTTPException(413, "Image must be under 10 MB")

    result = await _tg_upload_file(
        bot.bot_token,
        "sendPhoto",
        data={"chat_id": str(storage_group_id)},
        files={"photo": (file.filename or "thumb.jpg", img_bytes, ct)},
    )

    if not result or not result.get("ok"):
        raise HTTPException(502, "Failed to upload thumbnail to Telegram")

    msg = result["result"]
    photos = msg.get("photo", [])
    file_id = photos[-1]["file_id"] if photos else ""

    return {"file_id": file_id, "message_id": msg["message_id"]}


# ── Publish schemas ──────────────────────────────────────────

class PublishItem(BaseModel):
    storage_chat_id: int
    storage_message_id: int
    media_type: str = "video"
    title: str = ""
    access_type: str = "free"
    credit_cost: int = 0
    credit_mode: str = "per_item"
    credit_per_item: int = 1
    bot_id: int
    thumbnail_file_id: str | None = None


class GroupSettings(BaseModel):
    title: str
    access_type: str = "free"
    credit_cost: int = 0
    credit_mode: str = "per_item"
    credit_per_item: int = 1
    bot_id: int
    thumbnail_file_id: str | None = None


class PublishRequest(BaseModel):
    mode: str = "solo"  # "solo" or "group"
    items: list[PublishItem]
    group_settings: GroupSettings | None = None
    rate_per_minute: int = 2
    deletion_seconds: int | None = None


# ── Publish endpoint ─────────────────────────────────────────

@router.post("/publish")
async def start_publish(
    body: PublishRequest,
    db: AsyncSession = Depends(get_db),
):
    """Queue a bulk publish job. Returns job_id for tracking progress."""
    if not body.items:
        raise HTTPException(400, "No items to publish")

    if body.mode == "group" and not body.group_settings:
        raise HTTPException(400, "group_settings required for group mode")

    # Validate referenced bots exist
    svc = BotService(db)
    if body.mode == "group":
        bot = await svc.get_by_id(body.group_settings.bot_id)
        if not bot:
            raise HTTPException(404, f"Bot ID {body.group_settings.bot_id} not found")
    else:
        bot_ids = {item.bot_id for item in body.items}
        for bid in bot_ids:
            bot = await svc.get_by_id(bid)
            if not bot:
                raise HTTPException(404, f"Bot ID {bid} not found")

    job_id = uuid.uuid4().hex[:12]
    job = {
        "id": job_id,
        "status": "queued",
        "mode": body.mode,
        "total": len(body.items),
        "completed": 0,
        "failed": 0,
        "results": [],
        "rate_per_minute": body.rate_per_minute,
    }
    _publish_jobs[job_id] = job

    # Serialise body for the background task (avoid sharing SQLAlchemy session)
    asyncio.create_task(_process_publish_job(job_id, body))

    return {"job_id": job_id, "status": "queued", "total": len(body.items)}


# ── Background publishing logic ──────────────────────────────

async def _process_publish_job(job_id: str, body: PublishRequest):
    """Background task to process publish queue."""
    job = _publish_jobs[job_id]
    job["status"] = "processing"

    delay = 60.0 / max(body.rate_per_minute, 1)

    try:
        if body.mode == "group":
            await _publish_group(job, body)
        else:
            await _publish_solo(job, body, delay)
    except Exception as e:
        logger.error("Publish job %s failed: %s", job_id, e, exc_info=True)
        job["status"] = "failed"
        job["error"] = str(e)
        return

    job["status"] = "completed"


async def _publish_group(job: dict, body: PublishRequest):
    """Publish all items as a single group pack with one deep link."""
    gs = body.group_settings

    async with AsyncSessionLocal() as db:
        bot_svc = BotService(db)
        bot = await bot_svc.get_by_id(gs.bot_id)

        cs = ContentService(db)
        pack = await cs.create_pack(ContentPackCreate(
            title=gs.title,
            access_type=gs.access_type,
            credit_cost=gs.credit_cost,
            credit_mode=gs.credit_mode,
            credit_per_item=gs.credit_per_item,
            deletion_seconds=body.deletion_seconds,
        ))
        await db.flush()

        items_to_add = [
            PackItemCreate(
                pack_id=pack.id,
                storage_chat_id=item.storage_chat_id,
                storage_message_id=item.storage_message_id,
                media_type=item.media_type,
                order_index=idx,
            )
            for idx, item in enumerate(body.items)
        ]
        await cs.add_items_bulk(pack.id, items_to_add)

        ts = TokenService(db)
        token = await ts.create(pack_id=pack.id)
        await db.commit()

        deep_link = f"https://t.me/{bot.bot_username}?start={token.token}"

        channel_posted = await _post_to_channel(
            db, bot, gs.title, gs.access_type, gs.credit_cost,
            len(body.items), deep_link, gs.thumbnail_file_id,
        )

        job["completed"] = len(body.items)
        job["results"].append({
            "pack_id": pack.id,
            "token": token.token,
            "deep_link": deep_link,
            "items_count": len(body.items),
            "channel_posted": channel_posted,
            "title": gs.title,
        })


async def _publish_solo(job: dict, body: PublishRequest, delay: float):
    """Publish each item as a separate pack with its own deep link."""
    for idx, item in enumerate(body.items):
        try:
            async with AsyncSessionLocal() as db:
                bot_svc = BotService(db)
                bot = await bot_svc.get_by_id(item.bot_id)

                title = item.title or f"Content #{idx + 1}"

                cs = ContentService(db)
                pack = await cs.create_pack(ContentPackCreate(
                    title=title,
                    access_type=item.access_type,
                    credit_cost=item.credit_cost,
                    credit_mode=item.credit_mode,
                    credit_per_item=item.credit_per_item,
                    deletion_seconds=body.deletion_seconds,
                ))
                await db.flush()

                await cs.add_item(PackItemCreate(
                    pack_id=pack.id,
                    storage_chat_id=item.storage_chat_id,
                    storage_message_id=item.storage_message_id,
                    media_type=item.media_type,
                    order_index=0,
                ))

                ts = TokenService(db)
                token = await ts.create(pack_id=pack.id)
                await db.commit()

                deep_link = f"https://t.me/{bot.bot_username}?start={token.token}"

                channel_posted = await _post_to_channel(
                    db, bot, title, item.access_type, item.credit_cost,
                    1, deep_link, item.thumbnail_file_id,
                )

                job["completed"] += 1
                job["results"].append({
                    "pack_id": pack.id,
                    "token": token.token,
                    "deep_link": deep_link,
                    "items_count": 1,
                    "channel_posted": channel_posted,
                    "title": title,
                })
        except Exception as e:
            logger.error("Failed to publish item %d: %s", idx, e, exc_info=True)
            job["failed"] += 1
            job["results"].append({"error": str(e), "index": idx})

        # Rate-limit between items
        if idx < len(body.items) - 1:
            await asyncio.sleep(delay)


async def _post_to_channel(
    db: AsyncSession,
    bot,
    title: str,
    access_type: str,
    credit_cost: int,
    item_count: int,
    deep_link: str,
    thumbnail_file_id: str | None,
) -> bool:
    """Post content to the main Telegram channel."""
    svc = PlatformSettingsService(db)
    channel_id = await svc.get("content_channel_id")
    if not channel_id:
        logger.warning("content_channel_id not configured — skipping channel post")
        return False

    if access_type in ("credits", "credits_only") and credit_cost > 0:
        btn_label = f"Watch for {credit_cost} Credits"
    else:
        btn_label = "Access Content"

    suffix = "s" if item_count > 1 else ""
    caption = f"{title}\n{access_type.upper()} | {item_count} item{suffix}"

    reply_markup = {
        "inline_keyboard": [[{"text": btn_label, "url": deep_link}]],
    }

    if thumbnail_file_id:
        result = await _tg_request(bot.bot_token, "sendPhoto", {
            "chat_id": int(channel_id),
            "photo": thumbnail_file_id,
            "caption": caption,
            "reply_markup": reply_markup,
        })
        if result:
            return True

    # Fallback: text message with deep link
    result = await _tg_request(bot.bot_token, "sendMessage", {
        "chat_id": int(channel_id),
        "text": f"{caption}\n\n{deep_link}",
        "reply_markup": reply_markup,
    })
    return result is not None


# ── Job tracking endpoints ───────────────────────────────────

@router.get("/jobs")
async def list_jobs():
    """List all publish jobs (newest first)."""
    return sorted(_publish_jobs.values(), key=lambda j: j["id"], reverse=True)


@router.get("/jobs/{job_id}")
async def get_job(job_id: str):
    """Get a specific publish job's status and results."""
    job = _publish_jobs.get(job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job


# ── Content listing (enriched with tokens & stats) ──────────

@router.get("/content")
async def list_content(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List content packs enriched with deep links, item counts, and view stats."""
    cs = ContentService(db)
    packs = await cs.list_packs(limit=limit, offset=skip)

    # Batch-fetch first token per pack for deep-link construction
    pack_ids = [p.id for p in packs]
    if not pack_ids:
        return []

    # Get one token per pack (newest)
    subq = (
        select(
            Token.pack_id,
            Token.token,
            Token.used_count,
            func.row_number().over(
                partition_by=Token.pack_id,
                order_by=Token.created_at.desc(),
            ).label("rn"),
        )
        .where(Token.pack_id.in_(pack_ids))
        .subquery()
    )
    token_rows = await db.execute(
        select(subq.c.pack_id, subq.c.token, subq.c.used_count)
        .where(subq.c.rn == 1)
    )
    token_map: dict[int, tuple[str, int]] = {
        row.pack_id: (row.token, row.used_count) for row in token_rows.all()
    }

    # Get active bots (for constructing deep links)
    bot_svc = BotService(db)
    bots = await bot_svc.list_active()
    default_bot_username = bots[0].bot_username if bots else None

    enriched = []
    for pack in packs:
        token_str, used_count = token_map.get(pack.id, (None, 0))
        deep_link = None
        if token_str and default_bot_username:
            deep_link = f"https://t.me/{default_bot_username}?start={token_str}"

        enriched.append({
            "id": pack.id,
            "title": pack.title,
            "description": pack.description,
            "access_type": pack.access_type,
            "credit_cost": pack.credit_cost,
            "credit_mode": pack.credit_mode,
            "credit_per_item": pack.credit_per_item,
            "deletion_seconds": pack.deletion_seconds,
            "created_at": pack.created_at.isoformat() if pack.created_at else None,
            "item_count": len(pack.items),
            "token": token_str,
            "deep_link": deep_link,
            "views": used_count,
        })

    return enriched


# ── Re-publish (post existing pack to channel again) ────────

class RepublishRequest(BaseModel):
    bot_id: int
    thumbnail_file_id: str | None = None


@router.post("/republish/{pack_id}")
async def republish_pack(
    pack_id: int,
    body: RepublishRequest,
    db: AsyncSession = Depends(get_db),
):
    """Re-post an existing content pack to the channel."""
    cs = ContentService(db)
    pack = await cs.get_pack(pack_id)
    if not pack:
        raise HTTPException(404, "Content pack not found")

    bot_svc = BotService(db)
    bot = await bot_svc.get_by_id(body.bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")

    # Get or create token
    result = await db.execute(
        select(Token).where(Token.pack_id == pack_id).order_by(Token.created_at.desc()).limit(1)
    )
    token = result.scalar_one_or_none()
    if not token:
        ts = TokenService(db)
        token = await ts.create(pack_id=pack_id)
        await db.commit()

    deep_link = f"https://t.me/{bot.bot_username}?start={token.token}"

    posted = await _post_to_channel(
        db, bot, pack.title, pack.access_type, pack.credit_cost,
        len(pack.items), deep_link, body.thumbnail_file_id,
    )

    return {
        "posted": posted,
        "deep_link": deep_link,
        "pack_id": pack.id,
        "token": token.token,
    }


# ── Categories ───────────────────────────────────────────────

@router.get("/categories")
async def get_categories(db: AsyncSession = Depends(get_db)):
    """Get available content categories (access types)."""
    from backend.models.membership_plan import MembershipPlan

    result = await db.execute(
        select(MembershipPlan.access_type, MembershipPlan.display_name)
        .where(MembershipPlan.is_active == True)  # noqa: E712
        .order_by(MembershipPlan.tier_level, MembershipPlan.sort_order)
    )

    categories = [
        {"tag": "free", "label": "Free"},
        {"tag": "credits", "label": "Credits (free for members)"},
        {"tag": "credits_only", "label": "Credits Only"},
    ]
    seen = {"free", "credits", "credits_only"}

    for access_type, display_name in result.all():
        if access_type not in seen:
            categories.append({
                "tag": access_type,
                "label": display_name or access_type.title(),
            })
            seen.add(access_type)

    return categories
