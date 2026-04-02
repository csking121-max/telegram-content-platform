"""Schemas for platform settings."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PlatformSettingRead(BaseModel):
    id: int
    key: str
    value: str
    description: Optional[str] = None
    category: str
    created_at: datetime | None = None
    updated_at: datetime | None = None

    model_config = ConfigDict(from_attributes=True)


class PlatformSettingUpdate(BaseModel):
    value: str


class PlatformSettingCreate(BaseModel):
    key: str
    value: str
    description: Optional[str] = None
    category: str = "general"


class PlatformSettingBulkUpdate(BaseModel):
    """For updating multiple settings at once from the admin UI."""
    settings: dict[str, str]  # key → value
