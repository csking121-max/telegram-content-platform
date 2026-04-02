from __future__ import annotations

from typing import List, Optional

from pydantic import BaseModel, Field


class AccessRequest(BaseModel):
    telegram_id: int = Field(..., gt=0)
    token: str = Field(..., min_length=1, max_length=256)
    bot_username: str = Field(..., min_length=1, max_length=128)


class AccessResponse(BaseModel):
    allowed: bool
    reason: Optional[str] = None
    pack_id: Optional[int] = None
    upgrade_options: Optional[List[str]] = None
    credits_deducted: int = 0
    credit_cost: int = 0


class DeliveryResult(BaseModel):
    delivered_message_ids: List[int] = []
    deletion_scheduled: bool = False
    deletion_seconds: Optional[int] = None