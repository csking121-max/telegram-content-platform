from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class Tutorial(Base):
    __tablename__ = "tutorials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(512), nullable=False)
    storage_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_id: Mapped[str] = mapped_column(String(256), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<Tutorial id={self.id} '{self.question[:30]}'>"
