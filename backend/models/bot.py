from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Bot(Base):
    __tablename__ = "bots"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_username: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    bot_token: Mapped[str] = mapped_column(String(255), nullable=False)
    webhook_secret: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="active")  # active | inactive | rotated
    cleanup_hours: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 0 = disabled
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        CheckConstraint(
            "status IN ('active', 'inactive', 'rotated')",
            name="ck_bot_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<Bot id={self.id} @{self.bot_username}>"