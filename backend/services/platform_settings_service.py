"""
Platform Settings Service — reads/writes configurable settings from the DB.

Default settings are seeded on first access. Admin can override via the admin panel.
Includes an in-memory TTL cache to avoid hitting the DB on every get().
"""
from __future__ import annotations

import logging
import time
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.platform_setting import PlatformSetting

logger = logging.getLogger(__name__)

# ── In-memory cache with TTL ────────────────────────────────
_CACHE_TTL = 60  # seconds
_cache: dict[str, tuple[str, float]] = {}  # key → (value, expires_at)


def _cache_get(key: str) -> str | None:
    """Return cached value if present and not expired, else None."""
    entry = _cache.get(key)
    if entry is None:
        return None
    value, expires_at = entry
    if time.monotonic() > expires_at:
        _cache.pop(key, None)
        return None
    return value


def _cache_set(key: str, value: str) -> None:
    _cache[key] = (value, time.monotonic() + _CACHE_TTL)


def _cache_invalidate(key: str) -> None:
    _cache.pop(key, None)


def invalidate_settings_cache() -> None:
    """Clear entire settings cache (e.g. after bulk update)."""
    _cache.clear()

# ── Default settings (seeded if not in DB) ──────────────────

DEFAULTS: list[dict] = [
    # Telegram
    {"key": "utr_group_chat_id", "value": "", "description": "Telegram group ID where bank SMS are forwarded for UTR verification", "category": "payment"},
    {"key": "content_channel_link", "value": "", "description": "Public Telegram channel link (e.g. https://t.me/yourchannel) where content links are posted", "category": "content"},
    {"key": "content_channel_name", "value": "Content Channel", "description": "Display name for the content channel shown to users", "category": "content"},
    {"key": "content_channel_id", "value": "", "description": "Telegram channel ID (numeric, e.g. -1001234567890) for auto-posting content", "category": "content"},
    {"key": "storage_group_id", "value": "", "description": "Private Telegram group ID used as media storage backend", "category": "content"},
    {"key": "content_delete_seconds", "value": "0", "description": "Seconds after which delivered content messages are auto-deleted. 0 = never delete.", "category": "content"},
    {"key": "bot_welcome_message", "value": "👋 Welcome! Choose an option below:", "description": "Welcome message shown when user starts the bot", "category": "telegram"},

    # Payment
    {"key": "payment_expiry_minutes", "value": "15", "description": "Minutes before a payment order expires (default: 15)", "category": "payment"},

    # Credits
    {"key": "daily_credits_enabled", "value": "true", "description": "Enable daily free credit grants for all users", "category": "credits"},
    {"key": "daily_credits_amount", "value": "100", "description": "Number of free credits granted to each user daily", "category": "credits"},
    {"key": "default_credits_new_user", "value": "100", "description": "Default credit balance for newly registered users", "category": "credits"},
    {"key": "referral_reward_credits", "value": "10", "description": "Credits awarded per successful referral", "category": "credits"},
    {"key": "referral_enabled", "value": "true", "description": "Enable or disable the referral program", "category": "credits"},

    # Platform URL (HTTPS required for Telegram inline buttons)
    {"key": "public_base_url", "value": "", "description": "Public HTTPS base URL of the backend (e.g. https://yourdomain.com). Required for Telegram inline button URLs.", "category": "general"},

    # Ad-Watch System
    {"key": "ad_watch_count", "value": "4", "description": "Number of ads user must watch for free access", "category": "ad_watch"},
    {"key": "ad_watch_free_hours", "value": "12", "description": "Hours of free access granted after watching ads", "category": "ad_watch"},
    {"key": "ad_watch_timer_seconds", "value": "15", "description": "Countdown timer seconds per ad step", "category": "ad_watch"},
    {"key": "ad_watch_enabled", "value": "true", "description": "Enable or disable the ad-watch free access system", "category": "ad_watch"},

    # Streak System
    {"key": "streak_enabled", "value": "true", "description": "Enable or disable the daily credit streak system", "category": "streak"},
    {"key": "streak_min_daily_spend", "value": "5", "description": "Minimum credits a user must spend in a day to count as a streak day", "category": "streak"},

    # Expiry Notifications
    {"key": "expiry_notify_enabled", "value": "true", "description": "Enable automatic membership expiry reminder notifications", "category": "notifications"},
    {"key": "expiry_notify_days_before", "value": "3", "description": "Send expiry reminder this many days before membership expires", "category": "notifications"},

    # Low Credit Warnings
    {"key": "low_credit_warning_enabled", "value": "true", "description": "Enable automatic low-credit warning messages to users", "category": "notifications"},
    {"key": "low_credit_thresholds", "value": "10,5,2", "description": "Comma-separated credit thresholds that trigger a warning (e.g. 10,5,2). User is notified once per threshold.", "category": "notifications"},

    # General
    {"key": "platform_name", "value": "Content Platform", "description": "Platform name shown in bot messages", "category": "general"},
    {"key": "support_contact", "value": "", "description": "Support contact info shown to users (e.g. @support_username)", "category": "general"},
    {"key": "require_channel_join", "value": "true", "description": "Require users to join the content channel before accessing the bot", "category": "general"},

    # Custom credits
    {"key": "credits_per_inr", "value": "1", "description": "Price per 1 credit in ₹ (e.g. 0.20 = ₹0.20/credit, 1 = ₹1/credit, 5 = ₹5/credit)", "category": "credits"},
    {"key": "custom_credits_min", "value": "10", "description": "Minimum credits a user can buy in a custom order", "category": "credits"},
    {"key": "custom_credits_max", "value": "0", "description": "Maximum credits per custom order (0 = no limit)", "category": "credits"},
]


class PlatformSettingsService:
    """Read/write platform settings from the database."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get(self, key: str, default: str = "") -> str:
        """Get a single setting value by key (cached with TTL)."""
        cached = _cache_get(key)
        if cached is not None:
            return cached
        result = await self.db.execute(
            select(PlatformSetting).where(PlatformSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        value = setting.value if setting else default
        _cache_set(key, value)
        return value

    async def get_int(self, key: str, default: int = 0) -> int:
        """Get a setting as integer."""
        val = await self.get(key, str(default))
        try:
            return int(val)
        except (ValueError, TypeError):
            return default

    async def set(self, key: str, value: str) -> PlatformSetting:
        """Set a setting value (upsert). Invalidates cache."""
        result = await self.db.execute(
            select(PlatformSetting).where(PlatformSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        if setting:
            setting.value = value
        else:
            setting = PlatformSetting(key=key, value=value)
            self.db.add(setting)
        await self.db.flush()
        _cache_invalidate(key)
        return setting

    async def get_all(self, category: str | None = None) -> list[PlatformSetting]:
        """Get all settings, optionally filtered by category."""
        query = select(PlatformSetting).order_by(PlatformSetting.category, PlatformSetting.key)
        if category:
            query = query.where(PlatformSetting.category == category)
        result = await self.db.execute(query)
        return list(result.scalars().all())

    async def bulk_update(self, updates: dict[str, str]) -> int:
        """Update multiple settings at once. Returns count updated. Clears cache."""
        count = 0
        for key, value in updates.items():
            await self.set(key, value)
            count += 1
        invalidate_settings_cache()
        return count

    async def seed_defaults(self) -> int:
        """Insert default settings if they don't exist. Returns count seeded."""
        count = 0
        for d in DEFAULTS:
            result = await self.db.execute(
                select(PlatformSetting).where(PlatformSetting.key == d["key"])
            )
            if not result.scalar_one_or_none():
                self.db.add(PlatformSetting(**d))
                count += 1
        if count:
            await self.db.flush()
            logger.info("Seeded %d default platform settings", count)
        return count

    async def delete(self, key: str) -> bool:
        """Delete a setting by key. Invalidates cache."""
        result = await self.db.execute(
            select(PlatformSetting).where(PlatformSetting.key == key)
        )
        setting = result.scalar_one_or_none()
        if setting:
            await self.db.delete(setting)
            await self.db.flush()
            _cache_invalidate(key)
            return True
        return False
