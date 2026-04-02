"""
SMS Log model — stores forwarded bank SMS for UTR matching.
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class SmsLog(Base):
    __tablename__ = "sms_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sender: Mapped[str] = mapped_column(String(64), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    utr_extracted: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    amount_extracted: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    matched: Mapped[bool] = mapped_column(Boolean, default=False)
    matched_order_id: Mapped[Optional[int]] = mapped_column(
        Integer, ForeignKey("payment_orders.id", ondelete="SET NULL"), nullable=True,
    )
    source_chat_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<SmsLog id={self.id} utr={self.utr_extracted} matched={self.matched}>"
