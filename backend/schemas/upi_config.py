"""Pydantic schemas for UPI Configuration."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class UpiConfigCreate(BaseModel):
    upi_id: str
    payee_name: str
    is_active: bool = False


class UpiConfigUpdate(BaseModel):
    upi_id: Optional[str] = None
    payee_name: Optional[str] = None
    is_active: Optional[bool] = None


class UpiConfigRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    upi_id: str
    payee_name: str
    is_active: bool
    created_at: datetime
