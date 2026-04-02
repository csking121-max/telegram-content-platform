"""Admin CRUD for content packs."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.schemas.content_pack import (
    ContentPackCreate,
    ContentPackRead,
    ContentPackUpdate,
    ContentPackWithItems,
)
from backend.services.content_service import ContentService

router = APIRouter()


@router.get("", response_model=list[ContentPackRead])
async def list_packs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    svc = ContentService(db)
    return await svc.list_packs(limit=limit, offset=skip)


@router.get("/{pack_id}", response_model=ContentPackWithItems)
async def get_pack(pack_id: int, db: AsyncSession = Depends(get_db)):
    svc = ContentService(db)
    pack = await svc.get_pack(pack_id)
    if not pack:
        raise HTTPException(404, "Content pack not found")
    return pack


@router.post("", response_model=ContentPackRead, status_code=201)
async def create_pack(body: ContentPackCreate, db: AsyncSession = Depends(get_db)):
    svc = ContentService(db)
    pack = await svc.create_pack(body)
    return pack


@router.patch("/{pack_id}", response_model=ContentPackRead)
async def update_pack(pack_id: int, body: ContentPackUpdate, db: AsyncSession = Depends(get_db)):
    svc = ContentService(db)
    pack = await svc.update_pack(pack_id, body)
    if not pack:
        raise HTTPException(404, "Content pack not found")
    return pack


@router.delete("/{pack_id}")
async def delete_pack(pack_id: int, db: AsyncSession = Depends(get_db)):
    svc = ContentService(db)
    ok = await svc.delete_pack(pack_id)
    if not ok:
        raise HTTPException(404, "Content pack not found")
    return {"detail": "Content pack deleted"}