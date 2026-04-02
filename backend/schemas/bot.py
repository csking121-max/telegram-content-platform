from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class BotCreate(BaseModel):
    bot_username: str
    bot_token: str
    webhook_secret: str
    status: str = "active"


class BotRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    bot_username: str
    status: str
    cleanup_hours: int = 0
    created_at: datetime
    last_used_at: Optional[datetime] = None


class BotUpdate(BaseModel):
    bot_token: Optional[str] = None
    webhook_secret: Optional[str] = None
    status: Optional[str] = None
    cleanup_hours: Optional[int] = None