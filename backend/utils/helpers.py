"""Miscellaneous utility helpers."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict


def utcnow() -> datetime:
    """Timezone-aware UTC now."""
    return datetime.now(timezone.utc)


def format_response(data: Any, message: str = "", status: int = 200) -> Dict[str, Any]:
    return {"status": status, "message": message, "data": data}


def seconds_from_now(seconds: int) -> datetime:
    from datetime import timedelta
    return utcnow() + timedelta(seconds=seconds)