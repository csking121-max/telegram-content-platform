from __future__ import annotations

import asyncio
import logging
import os

from backend.services.backup_service import run_backup

logger = logging.getLogger(__name__)


class BackupWorker:
    """Runs database backups on a fixed interval."""

    def __init__(self) -> None:
        self.interval_seconds = max(60, int(os.getenv("BACKUP_INTERVAL_SECONDS", "17280")))
        enabled_value = os.getenv("BACKUP_ENABLED", "").strip().lower()
        github_configured = bool(
            (os.getenv("BACKUP_GITHUB_TOKEN") or os.getenv("GITHUB_TOKEN"))
            and os.getenv("BACKUP_GITHUB_REPO")
        )
        self.enabled = enabled_value in ("1", "true", "yes", "on") or (
            enabled_value == "" and github_configured
        )

    async def run(self) -> None:
        if not self.enabled:
            logger.info("BackupWorker disabled. Set BACKUP_ENABLED=true and GitHub backup env vars to enable.")
            while True:
                await asyncio.sleep(3600)

        logger.info("BackupWorker enabled; interval=%ss", self.interval_seconds)
        while True:
            try:
                result = await run_backup(push_to_github=True)
                github = result.get("github", {})
                logger.info(
                    "Backup completed: file=%s size=%s github_uploaded=%s",
                    result.get("file"),
                    result.get("size"),
                    github.get("uploaded", False),
                )
            except Exception:
                logger.exception("Scheduled backup failed")

            await asyncio.sleep(self.interval_seconds)
