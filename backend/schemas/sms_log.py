"""Pydantic schemas for SMS Log."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class SmsLogRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    sender: str
    body: str
    received_at: datetime
    utr_extracted: Optional[str] = None
    amount_extracted: Optional[float] = None
    matched: bool
    matched_order_id: Optional[int] = None
    source_chat_id: Optional[int] = None
    created_at: datetime
