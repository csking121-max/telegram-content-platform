"""Admin CRUD for pack items."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.schemas.pack_item import PackItemCreate, PackItemRead
from backend.services.content_service import ContentService

router = APIRouter()


@router.get("/pack/{pack_id}", response_model=list[PackItemRead])
async def list_items(
    pack_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    svc = ContentService(db)
    return await svc.get_items(pack_id)


@router.post("", response_model=PackItemRead, status_code=201)
async def add_item(body: PackItemCreate, db: AsyncSession = Depends(get_db)):
    svc = ContentService(db)
    item = await svc.add_item(body)
    return item


@router.post("/bulk", response_model=list[PackItemRead], status_code=201)
async def add_items_bulk(
    items: list[PackItemCreate],
    db: AsyncSession = Depends(get_db),
):
    if not items:
        return []
    svc = ContentService(db)
    return await svc.add_items_bulk(items[0].pack_id, items)


@router.delete("/{item_id}")
async def delete_item(item_id: int, db: AsyncSession = Depends(get_db)):
    svc = ContentService(db)
    ok = await svc.delete_item(item_id)
    if not ok:
        raise HTTPException(404, "Pack item not found")
    return {"detail": "Pack item deleted"}