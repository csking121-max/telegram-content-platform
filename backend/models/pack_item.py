from __future__ import annotations

from sqlalchemy import BigInteger, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.database import Base


class PackItem(Base):
    __tablename__ = "pack_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pack_id: Mapped[int] = mapped_column(Integer, ForeignKey("content_packs.id", ondelete="CASCADE"), nullable=False, index=True)
    storage_chat_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    storage_message_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    file_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    media_type: Mapped[str] = mapped_column(String(32), nullable=False)  # photo | video | document | animation
    order_index: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ── Relationships ────────────────────────────────
    content_pack: Mapped["ContentPack"] = relationship(  # noqa: F821
        "ContentPack", back_populates="items",
    )

    def __repr__(self) -> str:
        return f"<PackItem id={self.id} pack={self.pack_id} #{self.order_index}>"