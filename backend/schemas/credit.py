from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CreditRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    user_id: int
    balance: int


class CreditAdjust(BaseModel):
    """Used by admin and internal engines to change a user's balance."""
    user_id: int
    change_amount: int
    reason: str


class CreditHistoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    change_amount: int
    reason: str
    created_at: datetime