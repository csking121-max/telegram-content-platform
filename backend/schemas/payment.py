from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PaymentCreate(BaseModel):
    user_id: int
    amount: float
    method: str
    reference: str


class PaymentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    amount: float
    method: str
    reference: str
    status: str
    created_at: datetime
    completed_at: Optional[datetime] = None


class PaymentVerify(BaseModel):
    """Incoming webhook from payment provider."""
    reference: str
    status: str  # completed | failed
    provider_data: Optional[dict] = None