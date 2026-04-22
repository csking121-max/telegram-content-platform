"""
Membership Plan model — admin-configurable plans with pricing.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, CheckConstraint, DateTime, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class MembershipPlan(Base):
    __tablename__ = "membership_plans"
    __table_args__ = (
        CheckConstraint("tier_level >= 0", name="ck_membership_plan_tier_level_non_negative"),
        CheckConstraint("sort_order >= 0", name="ck_membership_plan_sort_order_non_negative"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    display_name: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    access_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="vip",
    )  # free | vip | premium | daily_pass | exclusive
    price_inr: Mapped[Decimal] = mapped_column(Numeric(10, 2), nullable=False, default=0)
    credit_price: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=30)
    duration_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_reward: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    tier_level: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<MembershipPlan id={self.id} '{self.name}' ₹{self.price_inr}>"
