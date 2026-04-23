"""
Admin log viewer — streams log files from /data directory.

Log files:
  - data/backend.log  — FastAPI backend logs
  - data/gateway.log  — Telegram gateway bot logs
"""
from __future__ import annotations

import os
from collections import deque
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

from backend.config import settings
from backend.redis_client import RedisClient

router = APIRouter()

LOG_DIR = Path("data")

KNOWN_LOG_FILES = {
    "backend": "backend.log",
    "gateway": "gateway.log",
    "backup": "backup.log",
}


class LogResponse(BaseModel):
    source: str
    filename: str
    total_lines: int
    lines: list[str]
    file_size_bytes: int


@router.get("/sources")
async def list_log_sources():
    """List available log sources and their status."""
    sources = []
    for name, filename in KNOWN_LOG_FILES.items():
        path = LOG_DIR / filename
        exists = path.exists()
        size = path.stat().st_size if exists else 0
        sources.append({
            "name": name,
            "filename": filename,
            "exists": exists,
            "size_bytes": size,
            "size_human": _human_size(size),
        })
    return sources


@router.get("/{source}", response_model=LogResponse)
async def get_logs(
    source: str,
    tail: int = Query(200, ge=1, le=5000, description="Number of lines from end"),
    search: str = Query("", description="Filter lines containing this text"),
    level: str = Query("", description="Filter by level: INFO, WARNING, ERROR, DEBUG"),
):
    """Read the last N lines from a log file, with optional filtering."""
    filename = KNOWN_LOG_FILES.get(source)
    if not filename:
        raise HTTPException(404, f"Unknown log source: {source}. Available: {list(KNOWN_LOG_FILES.keys())}")

    path = LOG_DIR / filename
    if not path.exists():
        return LogResponse(
            source=source,
            filename=filename,
            total_lines=0,
            lines=[f"Log file not found: {filename}. Start the {source} service to generate logs."],
            file_size_bytes=0,
        )

    try:
        # Read last N lines efficiently
        all_lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        total = len(all_lines)

        # Apply filters
        filtered = all_lines
        if level:
            level_tag = f"[{level.upper()}]"
            filtered = [l for l in filtered if level_tag in l]
        if search:
            search_lower = search.lower()
            filtered = [l for l in filtered if search_lower in l.lower()]

        # Take last N
        result_lines = list(deque(filtered, maxlen=tail))

        return LogResponse(
            source=source,
            filename=filename,
            total_lines=total,
            lines=result_lines,
            file_size_bytes=path.stat().st_size,
        )
    except Exception as e:
        raise HTTPException(500, f"Failed to read log file: {e}")


@router.delete("/{source}")
async def clear_log(source: str):
    """Clear (truncate) a log file."""
    filename = KNOWN_LOG_FILES.get(source)
    if not filename:
        raise HTTPException(404, f"Unknown log source: {source}")

    path = LOG_DIR / filename
    if path.exists():
        path.write_text("", encoding="utf-8")
        return {"detail": f"Log file {filename} cleared."}
    return {"detail": "Log file did not exist."}


def _human_size(size_bytes: int) -> str:
    for unit in ["B", "KB", "MB", "GB"]:
        if size_bytes < 1024:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024  # type: ignore
    return f"{size_bytes:.1f} TB"


# ── Rate Limit Visibility ───────────────────────────────────

@router.get("/rate-limits/active")
async def get_active_rate_limits():
    """Scan Redis for active rate-limit keys and return current counts."""
    try:
        rc = RedisClient.get()
        cursor, keys = rc.client.scan(cursor=0, match="rl:*", count=500)
        while cursor:
            c, batch = rc.client.scan(cursor=cursor, match="rl:*", count=500)
            keys.extend(batch)
            cursor = c

        entries = []
        max_req = settings.RATE_LIMIT_REQUESTS
        for k in keys:
            count = rc.get_int(k)
            ttl = rc.client.ttl(k)
            identifier = k[3:] if isinstance(k, str) else k.decode()[3:]  # strip "rl:"
            entries.append({
                "key": identifier,
                "count": count,
                "limit": max_req,
                "remaining": max(0, max_req - count),
                "exceeded": count > max_req,
                "ttl_seconds": ttl if ttl > 0 else 0,
            })
        # Sort: exceeded first, then by count desc
        entries.sort(key=lambda e: (-e["exceeded"], -e["count"]))
        return {"total_tracked": len(entries), "entries": entries}
    except Exception as e:
        raise HTTPException(500, f"Failed to read rate limits: {e}")
