"""
StreakLevel — admin-configurable level tiers based on streak count.

Each level can award: bonus credits, a membership, or both.
Example: Level 1 (10 streak days) → 50 credits + VIP membership for 7 days.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class StreakLevel(Base):
    __tablename__ = "streak_levels"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    level: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    streak_days_required: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    bonus_credits: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    membership_plan_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("membership_plans.id", ondelete="SET NULL"), nullable=True,
    )
    membership_duration_days: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    label: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
