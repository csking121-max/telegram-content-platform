"""
Centralised configuration — loaded once from environment variables.
Every module imports `settings` from here.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import List

from dotenv import load_dotenv

# Load .env from project root (parent of /backend)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)


def _list_from_env(key: str, default: str = "[]") -> List[str]:
    raw = os.getenv(key, default)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return [s.strip() for s in raw.split(",") if s.strip()]


class Settings:
    """Plain-object settings – no Pydantic BaseSettings to keep deps minimal."""

    def __repr__(self) -> str:
        return "<Settings [secrets hidden]>"

    # ── Core ─────────────────────────────────────────
    DEBUG: bool = os.getenv("DEBUG", "False").lower() in ("true", "1", "yes")
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
    SECRET_KEY: str = os.getenv("SECRET_KEY", "change-me")
    CORS_ORIGINS: List[str] = _list_from_env("CORS_ORIGINS", '[]')

    # ── Database ─────────────────────────────────────
    # SQLite default for local dev; use postgresql+asyncpg:// in production
    DATABASE_URL: str = os.getenv(
        "DATABASE_URL",
        "sqlite+aiosqlite:///./data/platform.db",
    )
    DATABASE_URL_SYNC: str = os.getenv(
        "DATABASE_URL_SYNC",
        "sqlite:///./data/platform.db",
    )

    # ── Redis ────────────────────────────────────────
    REDIS_URL: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")

    # ── Telegram Bots ────────────────────────────────
    # Format per bot: "username:token:hmac_secret"
    TELEGRAM_BOTS_RAW: str = os.getenv("TELEGRAM_BOTS", "")

    # ── Delivery ─────────────────────────────────────
    DELIVERY_BATCH_SIZE: int = int(os.getenv("DELIVERY_BATCH_SIZE", "10"))
    DELIVERY_BATCH_DELAY_MS: int = int(os.getenv("DELIVERY_BATCH_DELAY_MS", "500"))

    # ── Credits ──────────────────────────────────────
    DEFAULT_CREDIT_BALANCE: int = int(os.getenv("DEFAULT_CREDIT_BALANCE", "100"))
    CREDIT_FRAUD_WINDOW_SECONDS: int = int(os.getenv("CREDIT_FRAUD_WINDOW_SECONDS", "60"))
    CREDIT_FRAUD_MAX_DEDUCTIONS: int = int(os.getenv("CREDIT_FRAUD_MAX_DEDUCTIONS", "10"))


    # ── Rate Limiting ────────────────────────────────
    RATE_LIMIT_REQUESTS: int = int(os.getenv("RATE_LIMIT_REQUESTS", "30"))
    RATE_LIMIT_WINDOW_SECONDS: int = int(os.getenv("RATE_LIMIT_WINDOW_SECONDS", "60"))

    # ── Admin ────────────────────────────────────────
    ADMIN_USERNAME: str = os.getenv("ADMIN_USERNAME", "admin")
    ADMIN_PASSWORD: str = os.getenv("ADMIN_PASSWORD", "change-me")
    ADMIN_JWT_SECRET: str = os.getenv("ADMIN_JWT_SECRET", "change-me-jwt")
    ADMIN_JWT_EXPIRY_HOURS: int = int(os.getenv("ADMIN_JWT_EXPIRY_HOURS", "24"))

    # ── Internal API Auth ────────────────────────────
    INTERNAL_API_KEY: str = os.getenv("INTERNAL_API_KEY", "")

    # ── Error Notifications (Telegram) ───────────────
    # Set both to enable sending ERROR/CRITICAL logs to a Telegram chat.
    ADMIN_NOTIFY_BOT_TOKEN: str = os.getenv("ADMIN_NOTIFY_BOT_TOKEN", "")
    ADMIN_NOTIFY_CHAT_ID: str = os.getenv("ADMIN_NOTIFY_CHAT_ID", "")

    # ── Workers ──────────────────────────────────────
    # Seconds between Redis queue polls for delivery/access/credit/deletion workers.
    # Increase to 5-10 on free Redis tiers with command limits (e.g. Upstash free).
    WORKER_POLL_INTERVAL: float = float(os.getenv("WORKER_POLL_INTERVAL", "1.0"))

    # ── Derived ──────────────────────────────────────
    def validate_secrets(self) -> None:
        """Raise on startup if critical secrets still have default values."""
        issues: list[str] = []
        if self.SECRET_KEY == "change-me":
            issues.append("SECRET_KEY")
        if self.ADMIN_PASSWORD == "change-me":
            issues.append("ADMIN_PASSWORD")
        if self.ADMIN_JWT_SECRET == "change-me-jwt":
            issues.append("ADMIN_JWT_SECRET")
        if issues and not self.DEBUG:
            raise RuntimeError(
                f"SECURITY: The following secrets still have default values and "
                f"must be set via environment variables: {', '.join(issues)}"
            )
        if issues:
            import logging as _log
            _log.getLogger(__name__).warning(
                "SECURITY WARNING: Default secrets detected (DEBUG mode): %s",
                ", ".join(issues),
            )

    @property
    def COOKIE_SECURE(self) -> bool:
        """True only when serving over HTTPS (any CORS origin starts with https://).
        When running on plain HTTP (IP-only, no SSL), returns False so cookies work.
        Can be forced via env var COOKIE_SECURE=true/false."""
        env_val = os.getenv("COOKIE_SECURE", "")
        if env_val.lower() in ("true", "1", "yes"):
            return True
        if env_val.lower() in ("false", "0", "no"):
            return False
        # Auto-detect: secure only if at least one CORS origin is HTTPS
        return any(o.startswith("https://") for o in self.CORS_ORIGINS)

    @property
    def telegram_bots(self) -> list[dict]:
        """Parse TELEGRAM_BOTS env into list of dicts."""
        bots: list[dict] = []
        for entry in self.TELEGRAM_BOTS_RAW.split(","):
            entry = entry.strip()
            if not entry:
                continue
            parts = entry.split(":")
            if len(parts) >= 3:
                bots.append({
                    "username": parts[0],
                    "token": parts[1],
                    "hmac_secret": parts[2],
                })
        return bots


settings = Settings()