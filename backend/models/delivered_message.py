from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, DateTime, ForeignKey, Integer, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class DeliveredMessage(Base):
    __tablename__ = "delivered_messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True,
    )
    bot_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("bots.id", ondelete="CASCADE"), nullable=False,
    )
    telegram_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    delete_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    deleted: Mapped[bool] = mapped_column(default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self) -> str:
        return f"<DeliveredMessage id={self.id} msg={self.telegram_message_id}>"