from __future__ import annotations

from sqlalchemy import CheckConstraint, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Credit(Base):
    """One-to-one credit balance per user."""
    __tablename__ = "credits"

    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), primary_key=True,
    )
    balance: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    user: Mapped["User"] = relationship("User", back_populates="credit")  # noqa: F821

    __table_args__ = (
        CheckConstraint("balance >= 0", name="ck_credit_balance_non_negative"),
    )

    def __repr__(self) -> str:
        return f"<Credit user={self.user_id} balance={self.balance}>"