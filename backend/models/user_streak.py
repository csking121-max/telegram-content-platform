"""
UserStreak — tracks daily activity streaks per user.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, Date, DateTime, Integer, ForeignKey, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class UserStreak(Base):
    __tablename__ = "user_streaks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False, index=True,
    )
    current_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    longest_streak: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_streak_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    last_spend_date: Mapped[datetime | None] = mapped_column(Date, nullable=True)
    today_spent: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_bonus_earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_milestone_claimed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    current_level: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_level_claimed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
