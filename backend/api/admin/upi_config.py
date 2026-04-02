"""Admin CRUD for UPI configuration (add/delete/set active UPI IDs)."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.schemas.upi_config import UpiConfigCreate, UpiConfigRead, UpiConfigUpdate
from backend.services.upi_service import UpiService

router = APIRouter()


@router.get("", response_model=list[UpiConfigRead])
async def list_upi_configs(db: AsyncSession = Depends(get_db)):
    svc = UpiService(db)
    return await svc.list_all()


@router.get("/{config_id}", response_model=UpiConfigRead)
async def get_upi_config(config_id: int, db: AsyncSession = Depends(get_db)):
    svc = UpiService(db)
    cfg = await svc.get_by_id(config_id)
    if not cfg:
        raise HTTPException(404, "UPI config not found")
    return cfg


@router.post("", response_model=UpiConfigRead, status_code=201)
async def create_upi_config(body: UpiConfigCreate, db: AsyncSession = Depends(get_db)):
    svc = UpiService(db)
    cfg = await svc.create(body)
    return cfg


@router.patch("/{config_id}", response_model=UpiConfigRead)
async def update_upi_config(config_id: int, body: UpiConfigUpdate, db: AsyncSession = Depends(get_db)):
    svc = UpiService(db)
    cfg = await svc.update(config_id, body)
    if not cfg:
        raise HTTPException(404, "UPI config not found")
    return cfg


@router.post("/{config_id}/set-active", response_model=UpiConfigRead)
async def set_active_upi(config_id: int, db: AsyncSession = Depends(get_db)):
    """Set this UPI ID as the active one for payments (deactivates all others)."""
    svc = UpiService(db)
    cfg = await svc.set_active(config_id)
    if not cfg:
        raise HTTPException(404, "UPI config not found")
    return cfg


@router.delete("/{config_id}")
async def delete_upi_config(config_id: int, db: AsyncSession = Depends(get_db)):
    svc = UpiService(db)
    ok = await svc.delete(config_id)
    if not ok:
        raise HTTPException(404, "UPI config not found")
    return {"detail": "UPI config deleted"}
