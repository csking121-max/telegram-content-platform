"""
UPI Configuration model — admin-managed UPI IDs for payment collection.
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class UpiConfig(Base):
    __tablename__ = "upi_configs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    upi_id: Mapped[str] = mapped_column(String(256), nullable=False, unique=True)
    payee_name: Mapped[str] = mapped_column(String(256), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<UpiConfig id={self.id} '{self.upi_id}' active={self.is_active}>"
