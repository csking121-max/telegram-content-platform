"""Pydantic schemas for MembershipPlan."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class MembershipPlanCreate(BaseModel):
    name: str
    display_name: str
    description: Optional[str] = None
    access_type: str = "vip"  # free | vip | premium | daily_pass
    price_inr: float = 0
    credit_price: int = 0
    duration_days: int = 30
    duration_hours: int = 0
    credit_reward: int = 0
    is_active: bool = True
    sort_order: int = 0
    tier_level: int = 0


class MembershipPlanUpdate(BaseModel):
    name: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    access_type: Optional[str] = None
    price_inr: Optional[float] = None
    credit_price: Optional[int] = None
    duration_days: Optional[int] = None
    duration_hours: Optional[int] = None
    credit_reward: Optional[int] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None
    tier_level: Optional[int] = None


class MembershipPlanRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    display_name: str
    description: Optional[str] = None
    access_type: str
    price_inr: float
    credit_price: int
    duration_days: int
    duration_hours: int
    credit_reward: int
    is_active: bool
    sort_order: int
    tier_level: int
    created_at: datetime
