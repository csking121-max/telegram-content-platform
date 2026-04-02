from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Referral(Base):
    __tablename__ = "referrals"
    __table_args__ = (
        UniqueConstraint("referrer_user_id", "used_by_user_id", name="uq_referral_pair"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    invite_code: Mapped[str] = mapped_column(String(64), unique=True, index=True, nullable=False)
    referrer_user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    used_by_user_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True,
    )
    reward_granted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    referrer: Mapped["User"] = relationship("User", foreign_keys=[referrer_user_id], back_populates="referrals_made")  # noqa: F821
    used_by: Mapped[Optional["User"]] = relationship("User", foreign_keys=[used_by_user_id])  # noqa: F821

    def __repr__(self) -> str:
        return f"<Referral code={self.invite_code} by_user={self.referrer_user_id}>"