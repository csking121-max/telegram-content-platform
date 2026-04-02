from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel


# ── Telegram native types (for raw update parsing) ─────────────

class TelegramUser(BaseModel):
    id: int
    is_bot: bool = False
    first_name: str = ""
    username: Optional[str] = None


class TelegramChat(BaseModel):
    id: int
    type: str = "private"


class TelegramMessage(BaseModel):
    message_id: int
    date: int
    chat: TelegramChat
    from_user: Optional[TelegramUser] = None
    text: Optional[str] = None

    model_config = {"populate_by_name": True}


class WebhookUpdate(BaseModel):
    """Incoming Telegram webhook update — we only need the fields we use."""
    update_id: int
    message: Optional[TelegramMessage] = None


# ── Gateway → Backend payload ──────────────────────────────────

class BotWebhookPayload(BaseModel):
    """
    Wrapper sent by the Telegram gateway to the backend webhook endpoint.

    The gateway parses the raw Telegram update, extracts the core fields,
    and POSTs this structure with an HMAC signature in the header.
    """
    telegram_id: int
    username: Optional[str] = None
    action: str  # "access_check" | "request_delivery" | …
    token: Optional[str] = None
    pack_id: Optional[int] = None
    extra: Optional[dict[str, Any]] = None