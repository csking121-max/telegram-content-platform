from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, ConfigDict

from backend.schemas.pack_item import PackItemRead


class ContentPackCreate(BaseModel):
    title: str
    description: Optional[str] = None
    access_type: str = "free"  # free | credits | daily_pass | vip | premium
    credit_cost: int = 0
    credit_mode: str = "per_item"  # per_pack | per_item
    credit_per_item: int = 1
    deletion_seconds: Optional[int] = None
    thumbnail_file_id: Optional[str] = None


class ContentPackRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    title: str
    description: Optional[str] = None
    access_type: str
    credit_cost: int
    credit_mode: str = "per_item"
    credit_per_item: int = 1
    deletion_seconds: Optional[int] = None
    created_at: datetime


class ContentPackUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    access_type: Optional[str] = None
    credit_cost: Optional[int] = None
    credit_mode: Optional[str] = None
    credit_per_item: Optional[int] = None
    deletion_seconds: Optional[int] = None
    thumbnail_file_id: Optional[str] = None


class ContentPackWithItems(ContentPackRead):
    items: List[PackItemRead] = []