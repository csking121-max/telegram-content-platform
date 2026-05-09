"""Admin content transfer jobs for reposting packs to a new channel/storage group."""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from backend.api.admin.content_factory import _merge_thumbnail_ids, _post_to_channel, _tg_request
from backend.database import AsyncSessionLocal
from backend.dependencies import get_db
from backend.engines.token_service import TokenService
from backend.models.bot import Bot
from backend.models.content_pack import ContentPack
from backend.models.pack_item import PackItem
from backend.models.publish_job import PublishJob
from backend.models.token import Token
from backend.services.bot_service import BotService
from backend.services.platform_settings_service import PlatformSettingsService

logger = logging.getLogger(__name__)
router = APIRouter()

CHANNELS_KEY = "content_transfer_channels"
_running_transfer_tasks: dict[str, asyncio.Task] = {}


class TransferChannel(BaseModel):
    id: str = Field(default_factory=lambda: uuid.uuid4().hex[:10])
    name: str
    channel_id: str
    channel_link: str = ""
    storage_group_id: str = ""
    bot_id: int | None = None


class TransferChannelList(BaseModel):
    channels: list[TransferChannel]


class TransferPackRow(BaseModel):
    id: int
    title: str
    access_type: str
    item_count: int
    created_at: str | None


class TransferStartRequest(BaseModel):
    channel_id: str
    channel_name: str = ""
    channel_link: str = ""
    storage_group_id: str = ""
    bot_id: int
    pack_ids: list[int] = Field(default_factory=list)
    date_from: datetime | None = None
    date_to: datetime | None = None
    include_all: bool = True
    copy_to_storage: bool = False
    make_active_after: bool = False
    rate_per_minute: int = 2


async def _get_channels(db: AsyncSession) -> list[TransferChannel]:
    svc = PlatformSettingsService(db)
    raw = await svc.get(CHANNELS_KEY, "[]")
    try:
        data = json.loads(raw or "[]")
        return [TransferChannel(**item) for item in data if isinstance(item, dict)]
    except Exception:
        return []


async def _set_channels(db: AsyncSession, channels: list[TransferChannel]) -> None:
    svc = PlatformSettingsService(db)
    await svc.set(CHANNELS_KEY, json.dumps([c.model_dump() for c in channels]))


async def _update_job(job_id: str, **fields) -> None:
    async with AsyncSessionLocal() as db:
        await db.execute(
            update(PublishJob)
            .where(PublishJob.id == job_id)
            .values(updated_at=datetime.now(timezone.utc), **fields)
        )
        await db.commit()


async def _append_result(job_id: str, result_item: dict, completed_delta: int = 0, failed_delta: int = 0) -> None:
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


async def _is_cancelled(db: AsyncSession, job_id: str) -> bool:
    row = await db.get(PublishJob, job_id)
    return bool(row and row.status == "cancelled")


async def _latest_or_new_token(db: AsyncSession, pack_id: int) -> Token:
    result = await db.execute(
        select(Token).where(Token.pack_id == pack_id).order_by(Token.created_at.desc()).limit(1)
    )
    token = result.scalar_one_or_none()
    if token:
        return token
    token_svc = TokenService(db)
    return await token_svc.create(pack_id=pack_id)


async def _copy_pack_items_to_storage(
    db: AsyncSession,
    bot: Bot,
    pack: ContentPack,
    storage_group_id: str,
    job_id: str,
) -> tuple[int, int]:
    copied = 0
    failed = 0
    target_chat_id = int(storage_group_id)

    for item in pack.items:
        if await _is_cancelled(db, job_id):
            break
        result = await _tg_request(bot.bot_token, "copyMessage", {
            "chat_id": target_chat_id,
            "from_chat_id": item.storage_chat_id,
            "message_id": item.storage_message_id,
        })
        message_id = (result or {}).get("result", {}).get("message_id")
        if message_id:
            item.storage_chat_id = target_chat_id
            item.storage_message_id = int(message_id)
            copied += 1
        else:
            failed += 1

    return copied, failed


async def _select_packs(db: AsyncSession, body: TransferStartRequest) -> list[ContentPack]:
    query = select(ContentPack).options(selectinload(ContentPack.items)).order_by(ContentPack.created_at.asc())
    if not body.include_all:
        if body.pack_ids:
            query = query.where(ContentPack.id.in_(body.pack_ids))
        elif not body.date_from and not body.date_to:
            return []
    if body.date_from:
        query = query.where(ContentPack.created_at >= body.date_from)
    if body.date_to:
        query = query.where(ContentPack.created_at <= body.date_to)
    result = await db.execute(query)
    return list(result.scalars().unique().all())


async def _process_transfer_job(job_id: str, body: TransferStartRequest) -> None:
    await _update_job(job_id, status="processing")
    delay = (60.0 / body.rate_per_minute) if body.rate_per_minute > 0 else 0

    try:
        async with AsyncSessionLocal() as db:
            bot_svc = BotService(db)
            bot = await bot_svc.get_by_id(body.bot_id)
            if not bot:
                raise RuntimeError(f"Bot ID {body.bot_id} not found")

            packs = await _select_packs(db, body)
            for index, pack in enumerate(packs):
                if await _is_cancelled(db, job_id):
                    return

                copied = 0
                copy_failed = 0
                if body.copy_to_storage and body.storage_group_id:
                    copied, copy_failed = await _copy_pack_items_to_storage(db, bot, pack, body.storage_group_id, job_id)

                token = await _latest_or_new_token(db, pack.id)
                await db.commit()

                deep_link = f"https://t.me/{bot.bot_username}?start={token.token}"
                posted = await _post_to_channel(
                    db,
                    bot,
                    pack.title,
                    pack.access_type,
                    pack.credit_cost,
                    pack.credit_mode,
                    pack.credit_per_item,
                    len(pack.items),
                    None,
                    deep_link,
                    _merge_thumbnail_ids(pack.thumbnail_file_id, []),
                    channel_id_override=body.channel_id,
                )

                await _append_result(job_id, {
                    "pack_id": pack.id,
                    "title": pack.title,
                    "deep_link": deep_link,
                    "channel_posted": posted,
                    "copied_items": copied,
                    "copy_failed": copy_failed,
                }, completed_delta=1 if posted else 0, failed_delta=0 if posted else 1)

                if delay > 0 and index < len(packs) - 1:
                    await asyncio.sleep(delay)

            if body.make_active_after:
                svc = PlatformSettingsService(db)
                await svc.bulk_update({
                    "content_channel_id": body.channel_id,
                    "content_channel_name": body.channel_name or "Content Channel",
                    "content_channel_link": body.channel_link,
                    "storage_group_id": body.storage_group_id,
                })
                await db.commit()
    except asyncio.CancelledError:
        await _update_job(job_id, status="cancelled")
        raise
    except Exception as exc:
        logger.exception("Content transfer job %s failed", job_id)
        await _update_job(job_id, status="failed", error=str(exc))
        return

    await _update_job(job_id, status="completed")


@router.get("/channels", response_model=TransferChannelList)
async def list_transfer_channels(db: AsyncSession = Depends(get_db)):
    return TransferChannelList(channels=await _get_channels(db))


@router.post("/channels", response_model=TransferChannel)
async def save_transfer_channel(body: TransferChannel, db: AsyncSession = Depends(get_db)):
    channels = await _get_channels(db)
    incoming = body if body.id else TransferChannel(**body.model_dump(exclude={"id"}))
    replaced = False
    for idx, channel in enumerate(channels):
        if channel.id == incoming.id:
            channels[idx] = incoming
            replaced = True
            break
    if not replaced:
        channels.append(incoming)
    await _set_channels(db, channels)
    await db.commit()
    return incoming


@router.delete("/channels/{channel_id}")
async def delete_transfer_channel(channel_id: str, db: AsyncSession = Depends(get_db)):
    channels = [c for c in await _get_channels(db) if c.id != channel_id]
    await _set_channels(db, channels)
    await db.commit()
    return {"detail": "Deleted"}


@router.get("/packs", response_model=list[TransferPackRow])
async def list_transfer_packs(limit: int = 500, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(
            ContentPack.id,
            ContentPack.title,
            ContentPack.access_type,
            ContentPack.created_at,
            func.count(PackItem.id).label("item_count"),
        )
        .outerjoin(PackItem, PackItem.pack_id == ContentPack.id)
        .group_by(ContentPack.id)
        .order_by(ContentPack.created_at.desc())
        .limit(limit)
    )
    return [
        TransferPackRow(
            id=row.id,
            title=row.title,
            access_type=row.access_type,
            item_count=row.item_count,
            created_at=row.created_at.isoformat() if row.created_at else None,
        )
        for row in result
    ]


@router.post("/jobs")
async def start_transfer(body: TransferStartRequest, db: AsyncSession = Depends(get_db)):
    if not body.channel_id:
        raise HTTPException(400, "Destination channel ID is required")
    if not body.bot_id:
        raise HTTPException(400, "Delivery bot is required")
    if body.copy_to_storage and not body.storage_group_id:
        raise HTTPException(400, "Storage group ID is required when copying media")

    bot = await BotService(db).get_by_id(body.bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")

    packs = await _select_packs(db, body)
    if not packs:
        raise HTTPException(400, "No content packs match this transfer")

    job_id = uuid.uuid4().hex[:12]
    job = PublishJob(
        id=job_id,
        status="queued",
        mode="transfer",
        total=len(packs),
        completed=0,
        failed=0,
        rate_per_minute=body.rate_per_minute,
        results="[]",
    )
    db.add(job)
    await db.commit()

    task = asyncio.create_task(_process_transfer_job(job_id, body))
    _running_transfer_tasks[job_id] = task
    task.add_done_callback(lambda _: _running_transfer_tasks.pop(job_id, None))
    return {"job_id": job_id, "status": "queued", "total": len(packs)}


@router.get("/jobs")
async def list_transfer_jobs(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PublishJob)
        .where(PublishJob.mode == "transfer")
        .order_by(PublishJob.created_at.desc())
        .limit(25)
    )
    return [job.to_dict() for job in result.scalars().all()]


@router.post("/jobs/{job_id}/cancel")
async def cancel_transfer_job(job_id: str, db: AsyncSession = Depends(get_db)):
    job = await db.get(PublishJob, job_id)
    if not job or job.mode != "transfer":
        raise HTTPException(404, "Transfer job not found")
    if job.status in ("completed", "failed", "cancelled"):
        return {"detail": f"Job already {job.status}"}

    job.status = "cancelled"
    job.updated_at = datetime.now(timezone.utc)
    await db.commit()

    task = _running_transfer_tasks.get(job_id)
    if task:
        task.cancel()
    return {"detail": "Transfer job cancelled"}
