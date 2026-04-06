from __future__ import annotations

import json
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database import Base


class PublishJob(Base):
    __tablename__ = "publish_jobs"

    id: Mapped[str] = mapped_column(String(16), primary_key=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="queued")
    mode: Mapped[str] = mapped_column(String(16), nullable=False, default="solo")
    total: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    rate_per_minute: Mapped[int] = mapped_column(Integer, nullable=False, default=2)
    results: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    error: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    @property
    def results_list(self) -> list[dict]:
        try:
            return json.loads(self.results)
        except (json.JSONDecodeError, TypeError):
            return []

    @results_list.setter
    def results_list(self, value: list[dict]) -> None:
        self.results = json.dumps(value)

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "status": self.status,
            "mode": self.mode,
            "total": self.total,
            "completed": self.completed,
            "failed": self.failed,
            "rate_per_minute": self.rate_per_minute,
            "results": self.results_list,
            "error": self.error,
            "created_at": self.created_at.isoformat() if self.created_at else None,
        }

    def __repr__(self) -> str:
        return f"<PublishJob id={self.id} status={self.status}>"
