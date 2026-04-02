"""
PlatformSetting — key/value store for all admin-configurable settings.

Replaces hard-coded env vars for things like:
  - UTR verification group chat ID
  - Content channel link/username
  - Bot tokens and chat IDs
  - UPI IDs (supplement to upi_configs table)
  - SMS forwarding API key
  - Payment expiry minutes
  - Welcome messages, etc.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class PlatformSetting(Base):
    __tablename__ = "platform_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    key: Mapped[str] = mapped_column(String(128), unique=True, nullable=False, index=True)
    value: Mapped[str] = mapped_column(Text, nullable=False, default="")
    description: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, default="general", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self) -> str:
        return f"<PlatformSetting key={self.key!r} value={self.value!r}>"
