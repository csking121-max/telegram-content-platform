from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import BigInteger, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(255), index=True, nullable=True)
    level: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_active_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    blocked_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # ── Relationships ────────────────────────────────
    credit: Mapped[Optional["Credit"]] = relationship(  # noqa: F821
        "Credit", back_populates="user", uselist=False, lazy="select",
    )
    memberships: Mapped[List["Membership"]] = relationship(  # noqa: F821
        "Membership", back_populates="user", lazy="select",
    )
    payments: Mapped[List["Payment"]] = relationship(  # noqa: F821
        "Payment", back_populates="user", lazy="select",
    )
    credit_history: Mapped[List["CreditHistory"]] = relationship(  # noqa: F821
        "CreditHistory", back_populates="user", lazy="select",
    )
    activity_logs: Mapped[List["ActivityLog"]] = relationship(  # noqa: F821
        "ActivityLog", back_populates="user", lazy="select",
    )
    referrals_made: Mapped[List["Referral"]] = relationship(  # noqa: F821
        "Referral",
        back_populates="referrer",
        foreign_keys="Referral.referrer_user_id",
        lazy="select",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} tg={self.telegram_id}>"