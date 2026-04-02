"""Admin CRUD for credit packages."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.schemas.credit_package import CreditPackageCreate, CreditPackageRead, CreditPackageUpdate
from backend.services.credit_package_service import CreditPackageService

router = APIRouter()


@router.get("", response_model=list[CreditPackageRead])
async def list_credit_packages(
    include_inactive: bool = True,
    db: AsyncSession = Depends(get_db),
):
    svc = CreditPackageService(db)
    return await svc.list_all(include_inactive)


@router.post("", response_model=CreditPackageRead, status_code=201)
async def create_credit_package(
    data: CreditPackageCreate,
    db: AsyncSession = Depends(get_db),
):
    svc = CreditPackageService(db)
    pkg = await svc.create(data)
    await db.commit()
    return pkg


@router.get("/{pkg_id}", response_model=CreditPackageRead)
async def get_credit_package(pkg_id: int, db: AsyncSession = Depends(get_db)):
    svc = CreditPackageService(db)
    pkg = await svc.get_by_id(pkg_id)
    if not pkg:
        raise HTTPException(404, "Credit package not found")
    return pkg


@router.patch("/{pkg_id}", response_model=CreditPackageRead)
async def update_credit_package(
    pkg_id: int,
    data: CreditPackageUpdate,
    db: AsyncSession = Depends(get_db),
):
    svc = CreditPackageService(db)
    pkg = await svc.update(pkg_id, data)
    if not pkg:
        raise HTTPException(404, "Credit package not found")
    await db.commit()
    return pkg


@router.delete("/{pkg_id}")
async def delete_credit_package(pkg_id: int, db: AsyncSession = Depends(get_db)):
    svc = CreditPackageService(db)
    if not await svc.delete(pkg_id):
        raise HTTPException(404, "Credit package not found")
    await db.commit()
    return {"ok": True}
