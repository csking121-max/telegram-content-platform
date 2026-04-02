"""Schemas for credit packages."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class CreditPackageCreate(BaseModel):
    name: str
    display_name: str
    description: str = ""
    credits: int
    price_inr: float
    is_active: bool = True
    sort_order: int = 0


class CreditPackageUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    credits: Optional[int] = None
    price_inr: Optional[float] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class CreditPackageRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str
    description: str
    credits: int
    price_inr: float
    is_active: bool
    sort_order: int
    created_at: datetime
