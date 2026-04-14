"""
Admin Content Factory — bulk upload & publish pipeline.

Endpoints for uploading files to Telegram Storage Group,
managing default thumbnails, and publishing content packs
with persistent job tracking that survives tab switches.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.dependencies import get_db
from backend.models.default_thumbnail import DefaultThumbnail
from backend.models.publish_job import PublishJob
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
TELEGRAM_LOCAL_API = os.environ.get("TELEGRAM_LOCAL_API_URL", "")  # e.g. http://telegram-bot-api:8081

# Cached flag: whether the Local Bot API is actually reachable
_local_api_available: bool | None = None  # None = not yet checked

# Track running asyncio tasks so multiple jobs can run concurrently
_running_tasks: dict[str, asyncio.Task] = {}


async def _check_local_api() -> bool:
    """Quick connectivity check for the Local Bot API server."""
    global _local_api_available
    if not TELEGRAM_LOCAL_API:
        _local_api_available = False
        return False
    try:
        async with httpx.AsyncClient(timeout=5) as client:
            resp = await client.get(TELEGRAM_LOCAL_API)
            _local_api_available = resp.status_code < 500
    except Exception:
        _local_api_available = False
    if not _local_api_available:
        logger.warning("Local Bot API at %s is not reachable — will use cloud API", TELEGRAM_LOCAL_API)
    return _local_api_available


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
    chat_id = int(val)
    if chat_id > 0 and len(str(chat_id)) >= 10:
        chat_id = int(f"-100{chat_id}")
    return chat_id


async def _tg_upload_file(
    token: str,
    method: str,
    data: dict,
    files: dict,
    timeout: int = 120,
    api_base: str = "",
) -> dict | None:
    """Call Telegram Bot API with file upload (multipart/form-data)."""
    base = api_base or TELEGRAM_API
    url = f"{base}/bot{token}/{method}"
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


async def _tg_download_file(token: str, file_id: str) -> bytes | None:
    """Download a file from Telegram using getFile + file download."""
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{TELEGRAM_API}/bot{token}/getFile",
                json={"file_id": file_id},
            )
            if resp.status_code != 200:
                return None
            file_path = resp.json().get("result", {}).get("file_path")
            if not file_path:
                return None
            dl = await client.get(f"{TELEGRAM_API}/file/bot{token}/{file_path}")
            if dl.status_code == 200:
                return dl.content
    except Exception as e:
        logger.warning("TG download file failed: %s", e)
    return None


# ── Upload helpers ────────────────────────────────────────────

def _detect_media_type(content_type: str) -> str:
    ct = content_type.lower()
    if ct.startswith("video/"):
        return "video"
    if ct.startswith("image/gif"):
        return "animation"
    if ct.startswith("image/"):
        return "photo"
    return "document"


def _tg_method_for_type(media_type: str) -> tuple[str, str]:
    return {
        "video": ("sendVideo", "video"),
        "photo": ("sendPhoto", "photo"),
        "animation": ("sendAnimation", "animation"),
        "document": ("sendDocument", "document"),
    }.get(media_type, ("sendDocument", "document"))


BLUR_FILTERS = {
    "light": "boxblur=5:1",
    "medium": "boxblur=10:1",
    "heavy": "boxblur=20:1",
}


def _get_video_duration(video_path: str) -> float | None:
    """Get video duration in seconds using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            video_path,
        ]
        proc = subprocess.run(cmd, capture_output=True, timeout=10, text=True)
        if proc.returncode == 0 and proc.stdout.strip():
            return float(proc.stdout.strip())
    except Exception as e:
        logger.warning("ffprobe duration failed: %s", e)
    return None


def _smart_seek_sec(duration: float | None) -> float:
    """Pick a smart thumbnail seek time based on video duration."""
    if duration is None or duration <= 0:
        return 2.0
    if duration < 10:
        return min(1.0, duration * 0.3)
    if duration < 60:
        return 5.0
    if duration < 300:
        return 30.0
    if duration < 600:
        return 60.0
    return 120.0


def _extract_video_thumbnail(
    video_path: str, seek_sec: float = 2.0, blur: str = "none",
) -> bytes | None:
    """Extract a single frame from video at seek_sec using FFmpeg.

    Returns JPEG bytes resized to max 320px wide, compressed under 200KB,
    or None if extraction fails.  Optionally applies blur.
    Accepts a file path (not bytes) to avoid holding video in memory.
    """
    tmp_out = None
    try:
        tmp_out = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        tmp_out.close()

        vf_parts = ["scale=320:-2"]
        blur_filter = BLUR_FILTERS.get(blur)
        if blur_filter:
            vf_parts.append(blur_filter)

        cmd = [
            "ffmpeg", "-y",
            "-ss", str(seek_sec),
            "-i", video_path,
            "-frames:v", "1",
            "-vf", ",".join(vf_parts),
            "-q:v", "5",
            tmp_out.name,
        ]
        proc = subprocess.run(
            cmd, capture_output=True, timeout=15,
        )
        if proc.returncode != 0:
            # If seek is past video end, retry at 0s
            if seek_sec > 0:
                return _extract_video_thumbnail(video_path, seek_sec=0, blur=blur)
            logger.warning("FFmpeg frame extraction failed: %s", proc.stderr[:300])
            return None

        thumb_bytes = open(tmp_out.name, "rb").read()
        if len(thumb_bytes) == 0:
            return None
        if len(thumb_bytes) > 200 * 1024:
            # Re-encode with lower quality
            cmd2 = [
                "ffmpeg", "-y",
                "-i", tmp_out.name,
                "-q:v", "10",
                tmp_out.name,
            ]
            subprocess.run(cmd2, capture_output=True, timeout=10)
            thumb_bytes = open(tmp_out.name, "rb").read()
        return thumb_bytes
    except Exception as e:
        logger.warning("Thumbnail extraction error: %s", e)
        return None
    finally:
        if tmp_out:
            try:
                os.unlink(tmp_out.name)
            except OSError:
                pass


async def _auto_thumbnail(
    token: str, storage_group_id: int, media_type: str,
    video_path: str | None = None, blur: str = "none",
) -> str | None:
    """Auto-generate a thumbnail for videos by extracting a frame.

    For photos, return None (photo file_id can be used directly).
    Runs FFmpeg in a thread to avoid blocking the event loop.
    Uses file path instead of bytes to avoid OOM on large videos.
    """
    if media_type != "video" or not video_path:
        return None
    try:
        loop = asyncio.get_event_loop()
        # Determine video duration and pick smart seek time
        duration = await loop.run_in_executor(None, _get_video_duration, video_path)
        seek_sec = _smart_seek_sec(duration)
        logger.info("Auto-thumbnail: duration=%.1fs, seek=%.1fs", duration or 0, seek_sec)
        thumb_bytes = await loop.run_in_executor(
            None, _extract_video_thumbnail, video_path, seek_sec, blur,
        )
        if not thumb_bytes:
            return None
        # Upload the thumbnail to Telegram storage group
        result = await _tg_upload_file(
            token, "sendPhoto",
            data={"chat_id": str(storage_group_id)},
            files={"photo": ("auto_thumb.jpg", thumb_bytes, "image/jpeg")},
        )
        if not result or not result.get("ok"):
            return None
        photos = result["result"].get("photo") or []
        return photos[-1]["file_id"] if photos else None
    except Exception as e:
        logger.warning("Auto-thumbnail failed: %s", e)
        return None


# ── Upload endpoints ─────────────────────────────────────────

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    bot_id: Optional[int] = Query(None, description="Bot ID to use for upload (default: first active bot)"),
    blur: Optional[str] = Query(None, description="Blur level for auto-thumbnail: light, medium, heavy"),
    db: AsyncSession = Depends(get_db),
):
    """Upload any file to the Telegram Storage Group."""
    ct = file.content_type or "application/octet-stream"
    media_type = _detect_media_type(ct)

    if bot_id:
        svc = BotService(db)
        bot = await svc.get_by_id(bot_id)
        if not bot:
            raise HTTPException(404, f"Bot ID {bot_id} not found")
    else:
        bot = await _get_first_active_bot(db)
    storage_group_id = await _get_storage_group_id(db)

    # Stream file to disk to avoid OOM on large uploads
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename or "")[1] or ".tmp")
    try:
        size = 0
        while chunk := await file.read(8 * 1024 * 1024):  # 8 MB chunks
            tmp_file.write(chunk)
            size += len(chunk)
        tmp_file.close()
        tmp_path = tmp_file.name
        size_mb = size / (1024 * 1024)

        if size_mb > 2048:
            raise HTTPException(413, "File must be under 2 GB")

        # Check Local Bot API reachability (cached after first check)
        global _local_api_available
        if _local_api_available is None and TELEGRAM_LOCAL_API:
            await _check_local_api()

        use_local = size_mb > 50 and TELEGRAM_LOCAL_API and _local_api_available
        api_base = TELEGRAM_LOCAL_API if use_local else TELEGRAM_API
        if use_local:
            logger.info("Large file %.1f MB — routing through Local Bot API", size_mb)
        elif size_mb > 50:
            logger.warning(
                "Large file %.1f MB but Local Bot API unavailable — trying cloud API (may fail for >50 MB)",
                size_mb,
            )

        tg_method, field_name = _tg_method_for_type(media_type)
        extra_data: dict = {}
        if media_type == "video":
            extra_data["supports_streaming"] = "true"

        upload_timeout = max(120, int(size_mb / 50 * 60) + 60)

        # Read file from disk for the upload (streamed, not all at once for huge files)
        file_bytes = open(tmp_path, "rb").read()

        upload_kwargs = dict(
            token=bot.bot_token,
            method=tg_method,
            data={"chat_id": str(storage_group_id), **extra_data},
            files={field_name: (file.filename or "file", file_bytes, ct)},
            timeout=upload_timeout,
        )

        # Try up to 2 times: first with chosen API, then fallback
        result = await _tg_upload_file(**upload_kwargs, api_base=api_base)

        # If Local Bot API failed, retry with cloud API
        if not result and use_local:
            logger.warning("Local Bot API failed — retrying with cloud API")
            result = await _tg_upload_file(**upload_kwargs, api_base=TELEGRAM_API)
            if result and result.get("ok"):
                logger.info("Cloud API fallback succeeded for %.1f MB file", size_mb)

        # If cloud API failed, retry once more (transient errors)
        if not result or not result.get("ok"):
            logger.info("First attempt failed — retrying upload in 2s")
            await asyncio.sleep(2)
            result = await _tg_upload_file(**upload_kwargs, api_base=TELEGRAM_API)

        # Free the bytes from memory now that upload is done
        del file_bytes

        if not result or not result.get("ok"):
            desc = result.get("description", "") if result else ""
            if "Request Entity Too Large" in desc or (not result and size_mb > 50):
                raise HTTPException(
                    413,
                    f"File is {size_mb:.0f} MB — Telegram cloud API supports up to 50 MB. "
                    "To upload larger files, configure the Local Bot API service "
                    "(requires TELEGRAM_API_ID and TELEGRAM_API_HASH in .env from my.telegram.org).",
                )
            detail = "Failed to upload file to Telegram storage group"
            if desc:
                detail += f": {desc}"
            raise HTTPException(502, detail)

        msg = result["result"]

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
        else:
            info = msg.get("document") or {}
            file_id = info.get("file_id", "")

        # Auto-thumbnail uses the temp file on disk (no extra memory)
        thumbnail_file_id = await _auto_thumbnail(
            bot.bot_token, storage_group_id, media_type,
            video_path=tmp_path,
            blur=blur or "none",
        )

        return {
            "storage_chat_id": storage_group_id,
            "storage_message_id": msg["message_id"],
            "file_id": file_id,
            "filename": file.filename,
            "media_type": media_type,
            "duration": info.get("duration"),
            "width": info.get("width"),
            "height": info.get("height"),
            "thumbnail_file_id": thumbnail_file_id,
        }
    finally:
        try:
            os.unlink(tmp_file.name)
        except OSError:
            pass


@router.post("/upload-thumbnail")
async def upload_thumbnail(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    """Upload a thumbnail image to Telegram Storage Group."""
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


@router.post("/extract-frame")
async def extract_frame(
    file: UploadFile = File(...),
    timestamp: float = Query(2.0, description="Timestamp in seconds to extract frame from"),
    blur: Optional[str] = Query(None, description="Blur level: light, medium, heavy"),
    db: AsyncSession = Depends(get_db),
):
    """Extract a frame from a video at a specific timestamp and upload as thumbnail."""
    ct = file.content_type or ""
    if not ct.startswith("video/"):
        raise HTTPException(400, f"Only video files accepted (got {ct})")

    if timestamp < 0:
        raise HTTPException(400, "Timestamp must be non-negative")

    bot = await _get_first_active_bot(db)
    storage_group_id = await _get_storage_group_id(db)

    # Stream video to temp file
    tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename or "")[1] or ".mp4")
    try:
        while chunk := await file.read(8 * 1024 * 1024):
            tmp_file.write(chunk)
        tmp_file.close()

        loop = asyncio.get_event_loop()
        thumb_bytes = await loop.run_in_executor(
            None, _extract_video_thumbnail, tmp_file.name, timestamp, blur or "none",
        )

        if not thumb_bytes:
            raise HTTPException(422, "Could not extract frame at the given timestamp")

        # Upload to Telegram storage group
        result = await _tg_upload_file(
            bot.bot_token, "sendPhoto",
            data={"chat_id": str(storage_group_id)},
            files={"photo": ("frame_thumb.jpg", thumb_bytes, "image/jpeg")},
        )
        if not result or not result.get("ok"):
            raise HTTPException(502, "Failed to upload extracted frame to Telegram")

        photos = result["result"].get("photo") or []
        file_id = photos[-1]["file_id"] if photos else ""
        return {"file_id": file_id}
    finally:
        try:
            os.unlink(tmp_file.name)
        except OSError:
            pass


# ── Default Thumbnails CRUD ──────────────────────────────────

@router.get("/default-thumbnails")
async def list_default_thumbnails(db: AsyncSession = Depends(get_db)):
    """List all saved default thumbnails."""
    result = await db.execute(
        select(DefaultThumbnail).order_by(DefaultThumbnail.id)
    )
    thumbs = result.scalars().all()
    return [
        {"id": t.id, "name": t.name, "file_id": t.file_id}
        for t in thumbs
    ]


class CreateDefaultThumbnailRequest(BaseModel):
    name: str
    file_id: str


@router.post("/default-thumbnails")
async def create_default_thumbnail(
    body: CreateDefaultThumbnailRequest,
    db: AsyncSession = Depends(get_db),
):
    """Save a new default thumbnail (name + file_id from a previous upload)."""
    thumb = DefaultThumbnail(name=body.name, file_id=body.file_id)
    db.add(thumb)
    await db.commit()
    await db.refresh(thumb)
    return {"id": thumb.id, "name": thumb.name, "file_id": thumb.file_id}


class RenameDefaultThumbnailRequest(BaseModel):
    name: str


@router.patch("/default-thumbnails/{thumb_id}")
async def rename_default_thumbnail(
    thumb_id: int,
    body: RenameDefaultThumbnailRequest,
    db: AsyncSession = Depends(get_db),
):
    """Rename a default thumbnail."""
    result = await db.execute(
        select(DefaultThumbnail).where(DefaultThumbnail.id == thumb_id)
    )
    thumb = result.scalar_one_or_none()
    if not thumb:
        raise HTTPException(404, "Thumbnail not found")
    thumb.name = body.name
    await db.commit()
    return {"id": thumb.id, "name": thumb.name, "file_id": thumb.file_id}


@router.delete("/default-thumbnails/{thumb_id}")
async def delete_default_thumbnail(
    thumb_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a default thumbnail."""
    await db.execute(
        delete(DefaultThumbnail).where(DefaultThumbnail.id == thumb_id)
    )
    await db.commit()
    return {"deleted": True}


# ── Publish schemas ──────────────────────────────────────────

class PublishItem(BaseModel):
    storage_chat_id: int
    storage_message_id: int
    file_id: str | None = None
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
    mode: str = "solo"
    items: list[PublishItem]
    group_settings: GroupSettings | None = None
    rate_per_minute: int = 0  # 0 = send all at once (no delay)
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

    # Persist job in DB so it survives tab switches / reconnects
    job_row = PublishJob(
        id=job_id,
        status="queued",
        mode=body.mode,
        total=len(body.items),
        completed=0,
        failed=0,
        rate_per_minute=body.rate_per_minute,
        results="[]",
    )
    db.add(job_row)
    await db.commit()

    task = asyncio.create_task(_process_publish_job(job_id, body))
    _running_tasks[job_id] = task
    task.add_done_callback(lambda t: _running_tasks.pop(job_id, None))

    return {"job_id": job_id, "status": "queued", "total": len(body.items)}


# ── Background publishing logic ──────────────────────────────

async def _update_job(job_id: str, **fields):
    """Update job fields in DB."""
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(PublishJob)
            .where(PublishJob.id == job_id)
            .values(updated_at=datetime.now(timezone.utc), **fields)
        )
        await db.commit()


async def _append_result(job_id: str, result_item: dict, completed_delta: int = 0, failed_delta: int = 0):
    """Append a result to the job results list in DB."""
    async with AsyncSessionLocal() as db:
        row = await db.get(PublishJob, job_id)
        if not row:
            return
        results = row.results_list
        results.append(result_item)
        row.results_list = results
        row.completed += completed_delta
        row.failed += failed_delta
        row.updated_at = datetime.now(timezone.utc)
        await db.commit()


async def _process_publish_job(job_id: str, body: PublishRequest):
    """Background task to process publish queue."""
    await _update_job(job_id, status="processing")

    delay = (60.0 / body.rate_per_minute) if body.rate_per_minute > 0 else 0

    try:
        if body.mode == "group":
            await _publish_group(job_id, body)
        else:
            await _publish_solo(job_id, body, delay)
    except Exception as e:
        logger.error("Publish job %s failed: %s", job_id, e, exc_info=True)
        await _update_job(job_id, status="failed", error=str(e))
        return

    await _update_job(job_id, status="completed")


async def _publish_group(job_id: str, body: PublishRequest):
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
            thumbnail_file_id=gs.thumbnail_file_id,
        ))
        await db.flush()

        items_to_add = [
            PackItemCreate(
                pack_id=pack.id,
                storage_chat_id=item.storage_chat_id,
                storage_message_id=item.storage_message_id,
                file_id=item.file_id,
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

        await _append_result(job_id, {
            "pack_id": pack.id,
            "token": token.token,
            "deep_link": deep_link,
            "items_count": len(body.items),
            "channel_posted": channel_posted,
            "title": gs.title,
        }, completed_delta=len(body.items))


async def _publish_solo(job_id: str, body: PublishRequest, delay: float):
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
                    thumbnail_file_id=item.thumbnail_file_id,
                ))
                await db.flush()

                await cs.add_item(PackItemCreate(
                    pack_id=pack.id,
                    storage_chat_id=item.storage_chat_id,
                    storage_message_id=item.storage_message_id,
                    file_id=item.file_id,
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

                await _append_result(job_id, {
                    "pack_id": pack.id,
                    "token": token.token,
                    "deep_link": deep_link,
                    "items_count": 1,
                    "channel_posted": channel_posted,
                    "title": title,
                }, completed_delta=1)
        except Exception as e:
            logger.error("Failed to publish item %d: %s", idx, e, exc_info=True)
            await _append_result(job_id, {"error": str(e), "index": idx}, failed_delta=1)

        if delay > 0 and idx < len(body.items) - 1:
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
        # Try sending with file_id directly (works if same bot uploaded it)
        result = await _tg_request(bot.bot_token, "sendPhoto", {
            "chat_id": int(channel_id),
            "photo": thumbnail_file_id,
            "caption": caption,
            "reply_markup": reply_markup,
        })
        if result:
            return True

        # file_id failed — thumbnail was uploaded via a different bot.
        # Download via the upload bot and re-upload through the channel bot.
        upload_bot = await _get_first_active_bot(db)
        if upload_bot.bot_token != bot.bot_token:
            img_bytes = await _tg_download_file(upload_bot.bot_token, thumbnail_file_id)
            if img_bytes:
                reup = await _tg_upload_file(
                    bot.bot_token,
                    "sendPhoto",
                    data={
                        "chat_id": str(int(channel_id)),
                        "caption": caption,
                        "reply_markup": json.dumps(reply_markup),
                    },
                    files={"photo": ("thumb.jpg", img_bytes, "image/jpeg")},
                )
                if reup and reup.get("ok"):
                    return True

    result = await _tg_request(bot.bot_token, "sendMessage", {
        "chat_id": int(channel_id),
        "text": f"{caption}\n\n{deep_link}",
        "reply_markup": reply_markup,
    })
    return result is not None


# ── Job tracking endpoints ───────────────────────────────────

@router.get("/jobs")
async def list_jobs(db: AsyncSession = Depends(get_db)):
    """List all publish jobs (newest first). Persisted in DB."""
    result = await db.execute(
        select(PublishJob).order_by(PublishJob.created_at.desc()).limit(50)
    )
    jobs = result.scalars().all()
    return [j.to_dict() for j in jobs]


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific publish job status and results."""
    job = await db.get(PublishJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    return job.to_dict()


@router.delete("/jobs/{job_id}")
async def delete_job(job_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a completed/failed job from history."""
    job = await db.get(PublishJob, job_id)
    if not job:
        raise HTTPException(404, "Job not found")
    if job.status == "processing":
        raise HTTPException(400, "Cannot delete a running job")
    await db.execute(delete(PublishJob).where(PublishJob.id == job_id))
    await db.commit()
    return {"deleted": True}


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

    pack_ids = [p.id for p in packs]
    if not pack_ids:
        return []

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


# ── Re-publish ───────────────────────────────────────────────

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

    result = await db.execute(
        select(Token).where(Token.pack_id == pack_id).order_by(Token.created_at.desc()).limit(1)
    )
    token = result.scalar_one_or_none()
    if not token:
        ts = TokenService(db)
        token = await ts.create(pack_id=pack_id)
        await db.commit()

    deep_link = f"https://t.me/{bot.bot_username}?start={token.token}"
    thumb = body.thumbnail_file_id or pack.thumbnail_file_id

    posted = await _post_to_channel(
        db, bot, pack.title, pack.access_type, pack.credit_cost,
        len(pack.items), deep_link, thumb,
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
