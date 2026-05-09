"""
Admin backup management - list, trigger, download database backups.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel

from backend.services.backup_service import BACKUP_DIR, human_size, run_backup

router = APIRouter()


class BackupInfo(BaseModel):
    filename: str
    size_bytes: int
    size_human: str
    created: str


class BackupListResponse(BaseModel):
    backups: list[BackupInfo]
    total: int
    last_status: dict | None


class TriggerResponse(BaseModel):
    success: bool
    message: str
    output: str


def _list_backups() -> list[BackupInfo]:
    """Return backup files sorted newest-first."""
    if not BACKUP_DIR.exists():
        return []

    items: list[BackupInfo] = []
    for backup_file in BACKUP_DIR.glob("db_backup_*.sql.gz"):
        stat = backup_file.stat()
        items.append(BackupInfo(
            filename=backup_file.name,
            size_bytes=stat.st_size,
            size_human=human_size(stat.st_size),
            created=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
        ))
    items.sort(key=lambda item: item.created, reverse=True)
    return items


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
            last_status = None

    return BackupListResponse(backups=backups, total=len(backups), last_status=last_status)


@router.post("/trigger", response_model=TriggerResponse)
async def trigger_backup():
    """Trigger a manual database backup and GitHub upload when configured."""
    try:
        result = await run_backup(push_to_github=True)
        github = result.get("github", {})

        message = f"Backup created: {result['file']} ({result['size']})"
        if github.get("uploaded"):
            message += f" and uploaded to GitHub: {github.get('path')}"
        elif github.get("enabled") is False:
            message += " (GitHub upload not configured)"
        else:
            message += " (GitHub upload did not complete)"

        return TriggerResponse(
            success=True,
            message=message,
            output=result.get("stderr", "OK"),
        )
    except Exception as exc:
        return TriggerResponse(success=False, message=str(exc), output="")


@router.get("/{filename}/download")
async def download_backup(filename: str):
    """Download a backup file."""
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
