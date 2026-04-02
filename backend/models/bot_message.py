"""
BotMessage model — tracks messages exchanged between bots and users
so they can be bulk-deleted for cleanup.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class BotMessage(Base):
    __tablename__ = "bot_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    bot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False, default="out")  # "in" | "out"
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
