"""
Cooldown — tracks when users have exceeded their link access limit and are under cooldown.

A user enters cooldown when they access more than the configured number of links (counted globally across all bots).
They remain in cooldown until the cooldown_until timestamp is reached.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Cooldown(Base):
    __tablename__ = "cooldowns"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    exceeded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    cooldown_until: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    access_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)  # Number of links accessed
    reason: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)  # e.g., "Exceeded 5 links limit"

    def __repr__(self) -> str:
        return f"<Cooldown user_id={self.user_id} until={self.cooldown_until}>"
