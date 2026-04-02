from __future__ import annotations

from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class Token(Base):
    __tablename__ = "tokens"

    token: Mapped[str] = mapped_column(String(128), primary_key=True)
    pack_id: Mapped[int] = mapped_column(Integer, ForeignKey("content_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    single_use: Mapped[bool] = mapped_column(Boolean, default=False)
    bound_user_id: Mapped[Optional[int]] = mapped_column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ── Relationships ────────────────────────────────
    content_pack: Mapped["ContentPack"] = relationship(  # noqa: F821
        "ContentPack", back_populates="tokens",
    )
    bound_user: Mapped[Optional["User"]] = relationship(  # noqa: F821
        "User", foreign_keys=[bound_user_id],
    )

    def __repr__(self) -> str:
        return f"<Token '{self.token[:8]}…' pack={self.pack_id}>"