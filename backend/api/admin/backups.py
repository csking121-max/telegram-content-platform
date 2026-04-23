"""
Admin backup management — list, trigger, download database backups.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.config import settings

router = APIRouter()

BACKUP_DIR = Path("/app/backups")


# ── Response models ──────────────────────────────────────────

class BackupInfo(BaseModel):
    filename: str
    size_bytes: int
    size_human: str
    created: str           # ISO-8601 UTC


class BackupListResponse(BaseModel):
    backups: list[BackupInfo]
    total: int
    last_status: dict | None


class TriggerResponse(BaseModel):
    success: bool
    message: str
    output: str


# ── Helpers ──────────────────────────────────────────────────

def _human_size(nbytes: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if nbytes < 1024:
            return f"{nbytes:.1f} {unit}"
        nbytes /= 1024  # type: ignore[assignment]
    return f"{nbytes:.1f} TB"


def _list_backups() -> list[BackupInfo]:
    """Return backup files sorted newest-first."""
    if not BACKUP_DIR.exists():
        return []
    items: list[BackupInfo] = []
    for f in BACKUP_DIR.glob("db_backup_*.sql.gz"):
        stat = f.stat()
        items.append(BackupInfo(
            filename=f.name,
            size_bytes=stat.st_size,
            size_human=_human_size(stat.st_size),
            created=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        ))
    items.sort(key=lambda b: b.created, reverse=True)
    return items


def _parse_db_url() -> tuple[str, str, str, str, str]:
    """Parse DATABASE_URL_SYNC to get host, port, user, password, dbname."""
    # postgresql://user:pass@host:port/dbname
    url = os.environ.get("DATABASE_URL_SYNC", "")
    if not url:
        raise RuntimeError("DATABASE_URL_SYNC not set")
    # strip scheme
    rest = url.split("://", 1)[1]
    userpass, hostrest = rest.split("@", 1)
    user, password = userpass.split(":", 1)
    hostport, dbname = hostrest.split("/", 1)
    if ":" in hostport:
        host, port = hostport.split(":", 1)
    else:
        host, port = hostport, "5432"
    return host, port, user, password, dbname


# ── Endpoints ────────────────────────────────────────────────

@router.get("", response_model=BackupListResponse)
async def list_backups():
    """List all available database backups."""
    backups = _list_backups()

    last_status: dict | None = None
    status_file = BACKUP_DIR / "last_backup.json"
    if status_file.exists():
        try:
            last_status = json.loads(status_file.read_text())
        except Exception:
            pass

    return BackupListResponse(backups=backups, total=len(backups), last_status=last_status)


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_backup():
    """Trigger a manual database backup using pg_dump directly."""
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"db_backup_{timestamp}.sql.gz"

    try:
        host, port, user, password, dbname = _parse_db_url()
    except Exception as exc:
        return TriggerResponse(success=False, message=f"DB config error: {exc}", output="")

    try:
        # pg_dump piped through gzip
        cmd = (
            f'PGPASSWORD="{password}" pg_dump -h {host} -p {port} -U {user} '
            f'-d {dbname} --clean --if-exists --no-owner '
            f'| gzip > "{backup_file}"'
        )
        proc = await asyncio.create_subprocess_shell(
            cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=120)
        stderr_text = stderr.decode(errors="replace") if stderr else ""

        if proc.returncode != 0 or not backup_file.exists() or backup_file.stat().st_size == 0:
            return TriggerResponse(
                success=False,
                message=f"pg_dump failed (exit {proc.returncode})",
                output=stderr_text[-2000:],
            )

        size = backup_file.stat().st_size
        size_human = _human_size(size)

        # Write status JSON
        status = {
            "file": backup_file.name,
            "size": size_human,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "success",
        }
        (BACKUP_DIR / "last_backup.json").write_text(json.dumps(status))

        return TriggerResponse(
            success=True,
            message=f"Backup created: {backup_file.name} ({size_human})",
            output=stderr_text[-2000:] if stderr_text else "OK",
        )
    except asyncio.TimeoutError:
        return TriggerResponse(success=False, message="Backup timed out after 120 seconds", output="")
    except Exception as exc:
        return TriggerResponse(success=False, message=str(exc), output="")


@router.get("/{filename}/download")
async def download_backup(filename: str):
    """Download a backup file."""
    # Sanitize filename to prevent path traversal
    safe_name = Path(filename).name
    if safe_name != filename or ".." in filename:
        raise HTTPException(status_code=400, detail="Invalid filename")
    if not safe_name.endswith(".sql.gz"):
        raise HTTPException(status_code=400, detail="Invalid backup file type")

    filepath = BACKUP_DIR / safe_name
    if not filepath.exists():
        raise HTTPException(status_code=404, detail="Backup file not found")

    return FileResponse(
        path=str(filepath),
        filename=safe_name,
        media_type="application/gzip",
    )
