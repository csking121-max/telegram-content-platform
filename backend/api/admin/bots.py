"""Admin CRUD for bots."""

import asyncio

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import AsyncSessionLocal
from backend.dependencies import get_db
from backend.models.delivered_message import DeliveredMessage
from backend.schemas.bot import BotCreate, BotRead, BotUpdate
from backend.services.bot_service import BotService
from backend.api.endpoints.internal import (
    announce_to_users as _internal_announce,
    clear_bot_messages as _internal_clear,
    send_welcome as _internal_welcome,
    _AnnounceBody,
)

router = APIRouter()


@router.get("")
async def list_bots(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    svc = BotService(db)
    bots = await svc.list_all()

    # Count unique users per bot from delivered_messages
    count_q = (
        select(DeliveredMessage.bot_id, func.count(func.distinct(DeliveredMessage.user_id)))
        .group_by(DeliveredMessage.bot_id)
    )
    count_result = await db.execute(count_q)
    traffic = dict(count_result.all())

    return [
        {
            **BotRead.model_validate(b).model_dump(mode="json"),
            "user_count": traffic.get(b.id, 0),
        }
        for b in bots
    ]


@router.get("/active", response_model=list[BotRead])
async def list_active_bots(db: AsyncSession = Depends(get_db)):
    svc = BotService(db)
    return await svc.list_active()


@router.get("/{bot_id}", response_model=BotRead)
async def get_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    svc = BotService(db)
    bot = await svc.get_by_id(bot_id)
    if not bot:
        raise HTTPException(404, "Bot not found")
    return bot


@router.post("", response_model=BotRead, status_code=201)
async def register_bot(body: BotCreate, db: AsyncSession = Depends(get_db)):
    svc = BotService(db)
    bot = await svc.register(body)
    return bot


@router.patch("/{bot_id}", response_model=BotRead)
async def update_bot(bot_id: int, body: BotUpdate, db: AsyncSession = Depends(get_db)):
    svc = BotService(db)
    bot = await svc.update(bot_id, body)
    if not bot:
        raise HTTPException(404, "Bot not found")
    return bot


@router.delete("/{bot_id}")
async def delete_bot(bot_id: int, db: AsyncSession = Depends(get_db)):
    svc = BotService(db)
    ok = await svc.delete(bot_id)
    if not ok:
        raise HTTPException(404, "Bot not found")
    return {"detail": "Bot deleted"}


# ── Bulk actions on multiple bots (must be before /{bot_id} routes) ──

class BulkBotIds(BaseModel):
    bot_ids: list[int]


class BulkAnnounceBody(BaseModel):
    bot_ids: list[int]
    message: str


async def _announce_one(bot_id: int, message: str) -> dict:
    async with AsyncSessionLocal() as db:
        try:
            res = await _internal_announce(bot_id, _AnnounceBody(message=message), db)
            return {"bot_id": bot_id, "sent": res.get("sent", 0), "failed": res.get("failed", 0)}
        except Exception as e:
            return {"bot_id": bot_id, "sent": 0, "failed": 0, "error": str(e)}


async def _clear_one(bot_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        try:
            res = await _internal_clear(bot_id, db)
            return {"bot_id": bot_id, "deleted": res.get("deleted", 0), "failed": res.get("failed", 0)}
        except Exception as e:
            return {"bot_id": bot_id, "deleted": 0, "failed": 0, "error": str(e)}


async def _welcome_one(bot_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        try:
            res = await _internal_welcome(bot_id, db)
            return {"bot_id": bot_id, "sent": res.get("sent", 0), "failed": res.get("failed", 0)}
        except Exception as e:
            return {"bot_id": bot_id, "sent": 0, "failed": 0, "error": str(e)}


async def _delete_one(bot_id: int) -> dict:
    async with AsyncSessionLocal() as db:
        try:
            svc = BotService(db)
            ok = await svc.delete(bot_id)
            return {"bot_id": bot_id, "deleted": ok}
        except Exception as e:
            return {"bot_id": bot_id, "deleted": False, "error": str(e)}


@router.post("/bulk/announce")
async def bulk_announce(body: BulkAnnounceBody):
    results = await asyncio.gather(*[_announce_one(bot_id, body.message) for bot_id in body.bot_ids])
    return {"results": list(results)}


@router.post("/bulk/clear-messages")
async def bulk_clear(body: BulkBotIds):
    results = await asyncio.gather(*[_clear_one(bot_id) for bot_id in body.bot_ids])
    return {"results": list(results)}


@router.post("/bulk/send-welcome")
async def bulk_welcome(body: BulkBotIds):
    results = await asyncio.gather(*[_welcome_one(bot_id) for bot_id in body.bot_ids])
    return {"results": list(results)}


@router.post("/bulk/delete")
async def bulk_delete(body: BulkBotIds):
    results = await asyncio.gather(*[_delete_one(bot_id) for bot_id in body.bot_ids])
    return {"results": list(results)}


# ── Announce / Clear / Welcome — delegate to internal endpoints ──

class AnnounceBody(BaseModel):
    message: str


@router.post("/{bot_id}/announce")
async def announce(bot_id: int, body: AnnounceBody, db: AsyncSession = Depends(get_db)):
    return await _internal_announce(bot_id, _AnnounceBody(message=body.message), db)


@router.post("/{bot_id}/clear-messages")
async def clear_messages(bot_id: int, db: AsyncSession = Depends(get_db)):
    return await _internal_clear(bot_id, db)


@router.post("/{bot_id}/send-welcome")
async def welcome(bot_id: int, db: AsyncSession = Depends(get_db)):
    return await _internal_welcome(bot_id, db)