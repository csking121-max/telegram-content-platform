"""
Redis-backed user state for the Telegram gateway.

Replaces in-memory dicts/sets for payment flow state so that gateway
restarts don't lose user sessions mid-transaction.
"""
from __future__ import annotations

import json
import logging
import os
from typing import Optional

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
STATE_TTL = 1800  # 30 minutes — auto-expire stale entries

_pool: redis.ConnectionPool | None = None


def _get_client() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True, max_connections=5)
    return redis.Redis(connection_pool=_pool)


# ── Pending orders: telegram_id → order_ref ──────────────────

def set_pending_order(telegram_id: int, order_ref: str) -> None:
    try:
        _get_client().setex(f"gw:pending:{telegram_id}", STATE_TTL, order_ref)
    except Exception:
        logger.debug("Redis unavailable for set_pending_order, using fallback")
        _fallback_pending[telegram_id] = order_ref


def get_pending_order(telegram_id: int) -> Optional[str]:
    try:
        val = _get_client().get(f"gw:pending:{telegram_id}")
        if val:
            return val
    except Exception:
        pass
    return _fallback_pending.get(telegram_id)


def clear_pending_order(telegram_id: int) -> None:
    try:
        _get_client().delete(f"gw:pending:{telegram_id}")
    except Exception:
        pass
    _fallback_pending.pop(telegram_id, None)


# ── Awaiting UTR: telegram_id set ────────────────────────────

def set_awaiting_utr(telegram_id: int) -> None:
    try:
        _get_client().setex(f"gw:utr:{telegram_id}", STATE_TTL, "1")
    except Exception:
        _fallback_utr.add(telegram_id)


def is_awaiting_utr(telegram_id: int) -> bool:
    try:
        return _get_client().exists(f"gw:utr:{telegram_id}") > 0
    except Exception:
        return telegram_id in _fallback_utr


def clear_awaiting_utr(telegram_id: int) -> None:
    try:
        _get_client().delete(f"gw:utr:{telegram_id}")
    except Exception:
        pass
    _fallback_utr.discard(telegram_id)


# ── Awaiting custom credits: telegram_id set ─────────────────

def set_awaiting_custom_credits(telegram_id: int) -> None:
    try:
        _get_client().setex(f"gw:custcr:{telegram_id}", STATE_TTL, "1")
    except Exception:
        _fallback_custom.add(telegram_id)


def is_awaiting_custom_credits(telegram_id: int) -> bool:
    try:
        return _get_client().exists(f"gw:custcr:{telegram_id}") > 0
    except Exception:
        return telegram_id in _fallback_custom


def clear_awaiting_custom_credits(telegram_id: int) -> None:
    try:
        _get_client().delete(f"gw:custcr:{telegram_id}")
    except Exception:
        pass
    _fallback_custom.discard(telegram_id)


# ── In-memory fallbacks (used only if Redis is down) ─────────
_fallback_pending: dict[int, str] = {}
_fallback_utr: set[int] = set()
_fallback_custom: set[int] = set()
_fallback_bug: set[int] = set()


# ── Awaiting bug report: telegram_id set ─────────────────────

def set_awaiting_bug_report(telegram_id: int) -> None:
    try:
        _get_client().setex(f"gw:bug:{telegram_id}", STATE_TTL, "1")
    except Exception:
        _fallback_bug.add(telegram_id)


def is_awaiting_bug_report(telegram_id: int) -> bool:
    try:
        return _get_client().exists(f"gw:bug:{telegram_id}") > 0
    except Exception:
        return telegram_id in _fallback_bug


def clear_awaiting_bug_report(telegram_id: int) -> None:
    try:
        _get_client().delete(f"gw:bug:{telegram_id}")
    except Exception:
        pass
    _fallback_bug.discard(telegram_id)
