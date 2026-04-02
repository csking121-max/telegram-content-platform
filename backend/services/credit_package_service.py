"""
Credit Package Service — CRUD for buyable credit packages.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.credit_package import CreditPackage
from backend.schemas.credit_package import CreditPackageCreate, CreditPackageUpdate

logger = logging.getLogger(__name__)


class CreditPackageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create(self, data: CreditPackageCreate) -> CreditPackage:
        pkg = CreditPackage(**data.model_dump())
        self.db.add(pkg)
        await self.db.flush()
        logger.info("Created credit package '%s' (%d credits, ₹%s)", pkg.name, pkg.credits, pkg.price_inr)
        return pkg

    async def get_by_id(self, pkg_id: int) -> Optional[CreditPackage]:
        result = await self.db.execute(select(CreditPackage).where(CreditPackage.id == pkg_id))
        return result.scalar_one_or_none()

    async def list_active(self) -> List[CreditPackage]:
        result = await self.db.execute(
            select(CreditPackage)
            .where(CreditPackage.is_active == True)  # noqa: E712
            .order_by(CreditPackage.sort_order, CreditPackage.price_inr)
        )
        return list(result.scalars().all())

    async def list_all(self, include_inactive: bool = True) -> List[CreditPackage]:
        query = select(CreditPackage).order_by(CreditPackage.sort_order, CreditPackage.price_inr)
        if not include_inactive:
            query = query.where(CreditPackage.is_active == True)  # noqa: E712
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def update(self, pkg_id: int, data: CreditPackageUpdate) -> Optional[CreditPackage]:
        pkg = await self.get_by_id(pkg_id)
        if not pkg:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(pkg, field, value)
        await self.db.flush()
        return pkg

    async def delete(self, pkg_id: int) -> bool:
        pkg = await self.get_by_id(pkg_id)
        if not pkg:
            return False
        await self.db.delete(pkg)
        await self.db.flush()
        return True
