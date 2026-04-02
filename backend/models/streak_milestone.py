"""
StreakMilestone — configurable reward tiers for streaks.

Example: 5 days → 50 bonus credits, 10 days → 120 bonus credits, etc.
Admin can create/edit/delete milestones from the admin panel.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Boolean, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class StreakMilestone(Base):
    __tablename__ = "streak_milestones"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    days_required: Mapped[int] = mapped_column(Integer, nullable=False, unique=True, index=True)
    bonus_credits: Mapped[int] = mapped_column(Integer, nullable=False)
    label: Mapped[str] = mapped_column(String(128), nullable=False, default="")
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
