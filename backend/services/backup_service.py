from __future__ import annotations

import asyncio
import base64
import json
import logging
import os
import shlex
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import httpx

logger = logging.getLogger(__name__)

BACKUP_DIR = Path(os.getenv("BACKUP_DIR", "/app/backups"))


def human_size(nbytes: int) -> str:
    size = float(nbytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def parse_db_url() -> tuple[str, str, str, str, str]:
    url = os.environ.get("DATABASE_URL_SYNC", "")
    if not url:
        raise RuntimeError("DATABASE_URL_SYNC not set")
    parsed = urlparse(url)
    if parsed.scheme not in ("postgresql", "postgres"):
        raise RuntimeError("DATABASE_URL_SYNC must be a PostgreSQL URL for pg_dump backups")
    if not parsed.hostname or not parsed.username:
        raise RuntimeError("DATABASE_URL_SYNC is missing host or user")

    dbname = unquote(parsed.path.lstrip("/"))
    if not dbname:
        raise RuntimeError("DATABASE_URL_SYNC is missing database name")

    return (
        parsed.hostname,
        str(parsed.port or 5432),
        unquote(parsed.username),
        unquote(parsed.password or ""),
        dbname,
    )


async def create_database_backup() -> dict:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    backup_file = BACKUP_DIR / f"db_backup_{timestamp}.sql.gz"

    host, port, user, password, dbname = parse_db_url()
    cmd = " ".join([
        "pg_dump",
        "-h", shlex.quote(host),
        "-p", shlex.quote(port),
        "-U", shlex.quote(user),
        "-d", shlex.quote(dbname),
        "--clean",
        "--if-exists",
        "--no-owner",
        "|",
        "gzip",
        ">",
        shlex.quote(str(backup_file)),
    ])
    env = os.environ.copy()
    env["PGPASSWORD"] = password
    proc = await asyncio.create_subprocess_shell(
        cmd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        env=env,
    )
    _, stderr = await asyncio.wait_for(proc.communicate(), timeout=int(os.getenv("BACKUP_TIMEOUT_SECONDS", "300")))
    stderr_text = stderr.decode(errors="replace") if stderr else ""

    if proc.returncode != 0 or not backup_file.exists() or backup_file.stat().st_size == 0:
        raise RuntimeError(f"pg_dump failed (exit {proc.returncode}): {stderr_text[-2000:]}")

    return {
        "file": backup_file.name,
        "path": str(backup_file),
        "size": human_size(backup_file.stat().st_size),
        "size_bytes": backup_file.stat().st_size,
        "stderr": stderr_text[-2000:] if stderr_text else "OK",
    }


async def push_backup_to_github(filepath: str | Path) -> dict:
    token = os.getenv("BACKUP_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN")
    repo = os.getenv("BACKUP_GITHUB_REPO", "")
    branch = os.getenv("BACKUP_GITHUB_BRANCH", "main")
    base_path = os.getenv("BACKUP_GITHUB_PATH", "database-backups").strip("/")

    if not token or not repo:
        return {"enabled": False, "uploaded": False, "message": "GitHub backup token/repo not configured"}

    path = Path(filepath)
    github_path = f"{base_path}/{path.name}" if base_path else path.name
    url = f"https://api.github.com/repos/{repo}/contents/{github_path}"

    content_b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    payload = {
        "message": f"Database backup {path.name}",
        "content": content_b64,
        "branch": branch,
    }
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }

    async with httpx.AsyncClient(timeout=120) as client:
        response = await client.put(url, headers=headers, json=payload)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"GitHub upload failed ({response.status_code}): {response.text[:500]}")

    data = response.json()
    return {
        "enabled": True,
        "uploaded": True,
        "repo": repo,
        "branch": branch,
        "path": github_path,
        "html_url": data.get("content", {}).get("html_url"),
    }


async def run_backup(push_to_github: bool = True) -> dict:
    try:
        backup = await create_database_backup()
        github = {"enabled": False, "uploaded": False}
        if push_to_github:
            github = await push_backup_to_github(backup["path"])
        status = {
            "file": backup["file"],
            "size": backup["size"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "success",
            "github": github,
        }
        (BACKUP_DIR / "last_backup.json").write_text(json.dumps(status))
        return {**backup, "github": github, "status": status}
    except Exception as exc:
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "failed",
            "error": str(exc),
        }
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        (BACKUP_DIR / "last_backup.json").write_text(json.dumps(status))
        logger.exception("Database backup failed")
        raise
