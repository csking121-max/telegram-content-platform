from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class TokenCreate(BaseModel):
    pack_id: int
    expires_at: Optional[datetime] = None
    single_use: bool = False
    bound_user_id: Optional[int] = None


class TokenRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    token: str
    pack_id: int
    expires_at: Optional[datetime] = None
    single_use: bool
    bound_user_id: Optional[int] = None
    used_count: int
    created_at: datetime


class TokenUpdate(BaseModel):
    expires_at: Optional[datetime] = None
    single_use: Optional[bool] = None
    bound_user_id: Optional[int] = None