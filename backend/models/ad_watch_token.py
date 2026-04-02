"""
Ad-Watch Token model — 12-hour free access grant after watching 4 ads.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class AdWatchToken(Base):
    __tablename__ = "ad_watch_tokens"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    token: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    ads_completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ads_required: Mapped[int] = mapped_column(Integer, nullable=False, default=4)
    activated: Mapped[bool] = mapped_column(Boolean, default=False)
    activated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # noqa: F821

    @property
    def is_active(self) -> bool:
        from datetime import datetime, timezone
        if not self.activated or not self.expires_at:
            return False
        return datetime.now(timezone.utc) < self.expires_at

    def __repr__(self) -> str:
        return f"<AdWatchToken id={self.id} user={self.user_id} active={self.is_active}>"
