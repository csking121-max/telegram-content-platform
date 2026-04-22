from __future__ import annotations

from datetime import datetime
from typing import List, Optional

from sqlalchemy import CheckConstraint, DateTime, Integer, String, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class ContentPack(Base):
    __tablename__ = "content_packs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    title: Mapped[str] = mapped_column(String(512), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(2048), nullable=True)
    access_type: Mapped[str] = mapped_column(
        String(32), nullable=False, default="free", index=True,
    )  # free | credits | daily_pass | vip | premium
    credit_cost: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    credit_mode: Mapped[str] = mapped_column(
        String(16), nullable=False, default="per_item",
    )  # per_pack | per_item
    credit_per_item: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    deletion_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    thumbnail_file_id: Mapped[Optional[str]] = mapped_column(String(256), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    # ── Relationships ────────────────────────────────
    items: Mapped[List["PackItem"]] = relationship(  # noqa: F821
        "PackItem",
        back_populates="content_pack",
        order_by="PackItem.order_index",
        lazy="selectin",
        cascade="all, delete-orphan",
    )
    tokens: Mapped[List["Token"]] = relationship(  # noqa: F821
        "Token", back_populates="content_pack",
        lazy="dynamic", cascade="all, delete-orphan", passive_deletes=True,
    )

    __table_args__ = (
        CheckConstraint(
            "access_type IN ('free', 'credits', 'credits_only', 'daily_pass', 'vip', 'premium', 'exclusive')",
            name="ck_content_pack_access_type",
        ),
    )

    def __repr__(self) -> str:
        return f"<ContentPack id={self.id} '{self.title}'>"