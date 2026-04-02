"""
Content Service — CRUD for content packs & pack items.
"""
from __future__ import annotations

import logging
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.content_pack import ContentPack
from backend.models.pack_item import PackItem
from backend.schemas.content_pack import ContentPackCreate, ContentPackUpdate
from backend.schemas.pack_item import PackItemCreate

logger = logging.getLogger(__name__)


class ContentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── Packs ────────────────────────────────────────

    async def create_pack(self, data: ContentPackCreate) -> ContentPack:
        pack = ContentPack(**data.model_dump())
        self.db.add(pack)
        await self.db.flush()
        logger.info("Created content pack id=%s '%s'", pack.id, pack.title)
        return pack

    async def get_pack(self, pack_id: int) -> Optional[ContentPack]:
        result = await self.db.execute(
            select(ContentPack).where(ContentPack.id == pack_id)
        )
        return result.scalar_one_or_none()

    async def update_pack(self, pack_id: int, data: ContentPackUpdate) -> Optional[ContentPack]:
        pack = await self.get_pack(pack_id)
        if not pack:
            return None
        for field, value in data.model_dump(exclude_unset=True).items():
            setattr(pack, field, value)
        await self.db.flush()
        return pack

    async def delete_pack(self, pack_id: int) -> bool:
        pack = await self.get_pack(pack_id)
        if not pack:
            return False
        await self.db.delete(pack)
        await self.db.flush()
        return True

    async def list_packs(self, limit: int = 100, offset: int = 0) -> List[ContentPack]:
        result = await self.db.execute(
            select(ContentPack).order_by(ContentPack.created_at.desc()).limit(limit).offset(offset)
        )
        return list(result.scalars().all())

    # ── Items ────────────────────────────────────────

    async def add_item(self, data: PackItemCreate) -> PackItem:
        item = PackItem(**data.model_dump())
        self.db.add(item)
        await self.db.flush()
        return item

    async def add_items_bulk(self, pack_id: int, items: List[PackItemCreate]) -> List[PackItem]:
        pack_items = []
        for item_data in items:
            item = PackItem(pack_id=pack_id, **item_data.model_dump(exclude={"pack_id"}))
            self.db.add(item)
            pack_items.append(item)
        await self.db.flush()
        return pack_items

    async def get_items(self, pack_id: int) -> List[PackItem]:
        result = await self.db.execute(
            select(PackItem)
            .where(PackItem.pack_id == pack_id)
            .order_by(PackItem.order_index)
        )
        return list(result.scalars().all())

    async def delete_item(self, item_id: int) -> bool:
        result = await self.db.execute(select(PackItem).where(PackItem.id == item_id))
        item = result.scalar_one_or_none()
        if not item:
            return False
        await self.db.delete(item)
        await self.db.flush()
        return True