from __future__ import annotations

from pydantic import BaseModel, ConfigDict


class PackItemCreate(BaseModel):
    pack_id: int
    storage_chat_id: int
    storage_message_id: int
    file_id: str | None = None
    media_type: str  # photo | video | document | animation
    order_index: int = 0


class PackItemRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    pack_id: int
    storage_chat_id: int
    storage_message_id: int
    file_id: str | None = None
    media_type: str
    order_index: int


class PackItemUpdate(BaseModel):
    storage_chat_id: int | None = None
    storage_message_id: int | None = None
    file_id: str | None = None
    media_type: str | None = None
    order_index: int | None = None