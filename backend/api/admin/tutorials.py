"""
Admin tutorials — manage tutorial videos with questions.
"""
from __future__ import annotations

import logging
import os
import tempfile
from typing import Optional

import httpx
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel
from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.models.tutorial import Tutorial
from backend.services.bot_service import BotService
from backend.services.platform_settings_service import PlatformSettingsService

logger = logging.getLogger(__name__)
router = APIRouter()

TELEGRAM_API = "https://api.telegram.org"


async def _get_first_bot_token(db: AsyncSession) -> str:
    svc = BotService(db)
    bots = await svc.list_active()
    if not bots:
        raise HTTPException(503, "No active bots configured")
    return bots[0].bot_token


async def _get_storage_group_id(db: AsyncSession) -> int:
    svc = PlatformSettingsService(db)
    val = await svc.get("storage_group_id")
    if not val:
        raise HTTPException(503, "storage_group_id not configured")
    chat_id = int(val)
    if chat_id > 0 and len(str(chat_id)) >= 10:
        chat_id = int(f"-100{chat_id}")
    return chat_id


@router.get("")
async def list_tutorials(db: AsyncSession = Depends(get_db)):
    """List all tutorials ordered by sort_order."""
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
            "sort_order": t.sort_order,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tutorials
    ]


@router.post("")
async def create_tutorial(
    file: UploadFile = File(...),
    question: str = Query(..., description="Tutorial question text"),
    sort_order: int = Query(0),
    db: AsyncSession = Depends(get_db),
):
    """Upload a tutorial video and create a tutorial entry."""
    ct = file.content_type or ""
    if not ct.startswith("video/"):
        raise HTTPException(400, f"Only video files accepted (got {ct})")

    token = await _get_first_bot_token(db)
    storage_group_id = await _get_storage_group_id(db)

    # Stream to temp file
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
    try:
        while chunk := await file.read(8 * 1024 * 1024):
            tmp.write(chunk)
        tmp.close()

        file_bytes = open(tmp.name, "rb").read()
        url = f"{TELEGRAM_API}/bot{token}/sendVideo"
        async with httpx.AsyncClient(timeout=300) as client:
            resp = await client.post(
                url,
                data={"chat_id": str(storage_group_id), "supports_streaming": "true"},
                files={"video": (file.filename or "tutorial.mp4", file_bytes, ct)},
            )
        del file_bytes

        if resp.status_code != 200 or not resp.json().get("ok"):
            raise HTTPException(502, "Failed to upload tutorial video to Telegram")

        msg = resp.json()["result"]
        video_info = msg.get("video") or {}
        file_id = video_info.get("file_id", "")

        tutorial = Tutorial(
            question=question,
            storage_chat_id=storage_group_id,
            storage_message_id=msg["message_id"],
            file_id=file_id,
            sort_order=sort_order,
        )
        db.add(tutorial)
        await db.commit()
        await db.refresh(tutorial)

        return {
            "id": tutorial.id,
            "question": tutorial.question,
            "file_id": file_id,
            "storage_message_id": msg["message_id"],
        }
    finally:
        try:
            os.unlink(tmp.name)
        except OSError:
            pass


class UpdateTutorial(BaseModel):
    question: Optional[str] = None
    sort_order: Optional[int] = None


@router.put("/{tutorial_id}")
async def update_tutorial(
    tutorial_id: int,
    body: UpdateTutorial,
    db: AsyncSession = Depends(get_db),
):
    """Update tutorial question or sort order."""
    values = {}
    if body.question is not None:
        values["question"] = body.question
    if body.sort_order is not None:
        values["sort_order"] = body.sort_order
    if not values:
        raise HTTPException(400, "Nothing to update")
    result = await db.execute(
        update(Tutorial).where(Tutorial.id == tutorial_id).values(**values)
    )
    if result.rowcount == 0:
        raise HTTPException(404, "Tutorial not found")
    await db.commit()
    return {"detail": "Updated"}


@router.delete("/{tutorial_id}")
async def delete_tutorial(
    tutorial_id: int,
    db: AsyncSession = Depends(get_db),
):
    """Delete a tutorial."""
    result = await db.execute(
        delete(Tutorial).where(Tutorial.id == tutorial_id)
    )
    if result.rowcount == 0:
        raise HTTPException(404, "Tutorial not found")
    await db.commit()
    return {"detail": "Deleted"}
