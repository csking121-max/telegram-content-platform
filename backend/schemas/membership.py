from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MembershipCreate(BaseModel):
    user_id: int
    membership_type: str
    expiry_at: Optional[datetime] = None


class MembershipRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    membership_type: str
    start_at: datetime
    expiry_at: Optional[datetime] = None


class MembershipUpdate(BaseModel):
    membership_type: Optional[str] = None
    expiry_at: Optional[datetime] = None