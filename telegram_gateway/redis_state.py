"""
Redis-backed user state for the Telegram gateway.

Replaces in-memory dicts/sets for payment flow state so that gateway
restarts don't lose user sessions mid-transaction.
"""
from __future__ import annotations

import json
import logging
import os
import time
from collections import OrderedDict
from typing import Optional

import redis

logger = logging.getLogger(__name__)

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
STATE_TTL = 1800  # 30 minutes — auto-expire stale entries

_pool: redis.ConnectionPool | None = None

# ── Bounded fallback structures (used only if Redis is down) ──
_FALLBACK_MAX_SIZE = 500
_FALLBACK_TTL = 1800  # 30 minutes — same as Redis TTL


def _get_client() -> redis.Redis:
    global _pool
    if _pool is None:
        _pool = redis.ConnectionPool.from_url(REDIS_URL, decode_responses=True, max_connections=5)
    return redis.Redis(connection_pool=_pool)


# ── In-memory fallbacks (used only if Redis is down) ─────────
# Bounded OrderedDicts with timestamps for TTL enforcement.
_fallback_pending: OrderedDict[int, tuple[str, float]] = OrderedDict()   # tid → (value, ts)
_fallback_utr: OrderedDict[int, float] = OrderedDict()                  # tid → ts
_fallback_custom: OrderedDict[int, float] = OrderedDict()               # tid → ts
_fallback_bug: OrderedDict[int, float] = OrderedDict()                  # tid → ts


def _fb_prune(store: OrderedDict, max_size: int = _FALLBACK_MAX_SIZE) -> None:
    """Remove expired entries and evict oldest if over max size."""
    now = time.monotonic()
    expired = [k for k, v in store.items()
               if now - (v[1] if isinstance(v, tuple) else v) > _FALLBACK_TTL]
    for k in expired:
        store.pop(k, None)
    while len(store) > max_size:
        store.popitem(last=False)


def _fb_set_val(store: OrderedDict, key: int, val: object) -> None:
    """Set a value in a fallback dict with TTL and size enforcement."""
    _fb_prune(store)
    store[key] = val
    store.move_to_end(key)


def _fb_get_pending(tid: int) -> Optional[str]:
    entry = _fallback_pending.get(tid)
    if entry is None:
        return None
    val, ts = entry
    if time.monotonic() - ts > _FALLBACK_TTL:
        _fallback_pending.pop(tid, None)
        return None
    return val


def _fb_has(store: OrderedDict, tid: int) -> bool:
    ts = store.get(tid)
    if ts is None:
        return False
    if time.monotonic() - ts > _FALLBACK_TTL:
        store.pop(tid, None)
        return False
    return True


# ── Pending orders: telegram_id → order_ref ──────────────────

def set_pending_order(telegram_id: int, order_ref: str) -> None:
    try:
        _get_client().setex(f"gw:pending:{telegram_id}", STATE_TTL, order_ref)
    except Exception:
        logger.debug("Redis unavailable for set_pending_order, using fallback")
        _fb_set_val(_fallback_pending, telegram_id, (order_ref, time.monotonic()))


def get_pending_order(telegram_id: int) -> Optional[str]:
    try:
        val = _get_client().get(f"gw:pending:{telegram_id}")
        if val:
            return val
    except Exception:
        pass
    return _fb_get_pending(telegram_id)


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
        _fb_set_val(_fallback_utr, telegram_id, time.monotonic())


def is_awaiting_utr(telegram_id: int) -> bool:
    try:
        return _get_client().exists(f"gw:utr:{telegram_id}") > 0
    except Exception:
        return _fb_has(_fallback_utr, telegram_id)


def clear_awaiting_utr(telegram_id: int) -> None:
    try:
        _get_client().delete(f"gw:utr:{telegram_id}")
    except Exception:
        pass
    _fallback_utr.pop(telegram_id, None)


# ── Awaiting custom credits: telegram_id set ─────────────────

def set_awaiting_custom_credits(telegram_id: int) -> None:
    try:
        _get_client().setex(f"gw:custcr:{telegram_id}", STATE_TTL, "1")
    except Exception:
        _fb_set_val(_fallback_custom, telegram_id, time.monotonic())


def is_awaiting_custom_credits(telegram_id: int) -> bool:
    try:
        return _get_client().exists(f"gw:custcr:{telegram_id}") > 0
    except Exception:
        return _fb_has(_fallback_custom, telegram_id)


def clear_awaiting_custom_credits(telegram_id: int) -> None:
    try:
        _get_client().delete(f"gw:custcr:{telegram_id}")
    except Exception:
        pass
    _fallback_custom.pop(telegram_id, None)


# ── Awaiting bug report: telegram_id set ─────────────────────

def set_awaiting_bug_report(telegram_id: int) -> None:
    try:
        _get_client().setex(f"gw:bug:{telegram_id}", STATE_TTL, "1")
    except Exception:
        _fb_set_val(_fallback_bug, telegram_id, time.monotonic())


def is_awaiting_bug_report(telegram_id: int) -> bool:
    try:
        return _get_client().exists(f"gw:bug:{telegram_id}") > 0
    except Exception:
        return _fb_has(_fallback_bug, telegram_id)


def clear_awaiting_bug_report(telegram_id: int) -> None:
    try:
        _get_client().delete(f"gw:bug:{telegram_id}")
    except Exception:
        pass
    _fallback_bug.pop(telegram_id, None)
