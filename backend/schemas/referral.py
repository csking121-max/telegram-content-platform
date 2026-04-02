from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class ReferralRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    invite_code: str
    referrer_user_id: int
    used_by_user_id: Optional[int] = None
    reward_granted: bool
    created_at: datetime


class ReferralCreate(BaseModel):
    inviter_id: int


class ReferralUse(BaseModel):
    invite_code: str
    user_id: int  # the user using the invite code