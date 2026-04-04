"""
Public settings endpoint — exposes non-sensitive platform settings
for the Telegram bot gateway (no auth required).
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.services.platform_settings_service import PlatformSettingsService

router = APIRouter()

# Only expose these safe keys publicly
_PUBLIC_KEYS = {
    "content_channel_id",
    "content_channel_link",
    "content_channel_name",
    "content_delete_seconds",
    "bot_welcome_message",
    "platform_name",
    "support_contact",
    "utr_group_chat_id",
    "require_channel_join",
    "default_credits_new_user",
    "credits_per_inr",
    "custom_credits_min",
    "custom_credits_max",
}


@router.get("/public")
async def get_public_settings(db: AsyncSession = Depends(get_db)):
    """
    Returns non-sensitive platform settings for bot/public use.
    Does NOT require authentication.
    """
    svc = PlatformSettingsService(db)
    all_settings = await svc.get_all()
    return [
        {"key": s.key, "value": s.value}
        for s in all_settings
        if s.key in _PUBLIC_KEYS
    ]
