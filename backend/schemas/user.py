from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UserCreate(BaseModel):
    telegram_id: int
    username: Optional[str] = None


class UserRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: Optional[str] = None
    level: int = 0
    created_at: datetime
    last_active_at: Optional[datetime] = None
    blocked_until: Optional[datetime] = None


class UserUpdate(BaseModel):
    username: Optional[str] = None
    level: Optional[int] = None
    blocked_until: Optional[datetime] = None


class UserBrief(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    telegram_id: int
    username: Optional[str] = None