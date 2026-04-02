from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Membership(Base):
    __tablename__ = "memberships"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    membership_type: Mapped[str] = mapped_column(String(32), nullable=False, default="free")
    start_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expiry_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    expiry_notified_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None,
    )

    user: Mapped["User"] = relationship("User", back_populates="memberships")  # noqa: F821

    @property
    def is_active(self) -> bool:
        from datetime import datetime, timezone
        if self.expiry_at is None:
            return True
        expiry = self.expiry_at
        if expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < expiry

    def __repr__(self) -> str:
        return f"<Membership user={self.user_id} type={self.membership_type}>"