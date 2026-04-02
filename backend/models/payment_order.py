"""
Payment Order model — tracks UPI payment flow: QR generated → UTR submitted → verified.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class PaymentOrder(Base):
    __tablename__ = "payment_orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    plan_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("membership_plans.id"), nullable=False, index=True,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    upi_id_used: Mapped[str] = mapped_column(String(256), nullable=False)
    order_ref: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default="pending", index=True,
    )  # pending | utr_submitted | verified | failed | expired
    package_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("credit_packages.id", ondelete="SET NULL"), nullable=True, index=True,
    )
    utr_submitted: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    verified_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    # For custom-amount credit orders (no fixed package)
    custom_credits: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    user: Mapped["User"] = relationship("User", foreign_keys=[user_id])  # noqa: F821
    plan: Mapped["MembershipPlan"] = relationship("MembershipPlan", foreign_keys=[plan_id])  # noqa: F821
    package: Mapped[Optional["CreditPackage"]] = relationship("CreditPackage", foreign_keys=[package_id])  # noqa: F821

    __table_args__ = (
        CheckConstraint(
            "status IN ('pending', 'utr_submitted', 'verified', 'failed', 'expired')",
            name="ck_payment_order_status",
        ),
    )

    def __repr__(self) -> str:
        return f"<PaymentOrder id={self.id} ref={self.order_ref} status={self.status}>"
