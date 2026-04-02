"""
Daily Credit Worker - grants daily credits to all active users.

Runs once per cycle (typically once per day via cron/scheduler).
Uses the DailyCreditService from the backend.
Uses a Redis distributed lock to prevent double-crediting from multiple instances.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import AsyncSessionLocal
from backend.services.daily_credit_service import DailyCreditService
from backend.redis_client import RedisClient

logger = logging.getLogger(__name__)

LOCK_KEY = "lock:daily_credit_grant"
LOCK_TTL = 300  # 5 minutes — prevent stale locks if worker crashes


class DailyCreditWorker:
    """Periodically grants daily credits to users."""

    def __init__(self, interval_seconds: int = 3600):
        # Default: check every hour, but grant only runs once per day per user
        self.interval = interval_seconds

    async def run(self) -> None:
        logger.info("DailyCreditWorker started (interval=%ds)", self.interval)
        while True:
            try:
                rc = RedisClient.get()
                # Acquire distributed lock — only one instance runs at a time
                acquired = rc.client.set(LOCK_KEY, "1", nx=True, ex=LOCK_TTL)
                if not acquired:
                    logger.debug("DailyCreditWorker: another instance holds the lock, skipping")
                else:
                    try:
                        async with AsyncSessionLocal() as db:
                            service = DailyCreditService(db)
                            count = await service.grant_daily_credits()
                            if count > 0:
                                logger.info("Daily credit grant: %d users credited", count)
                            await db.commit()
                    finally:
                        rc.client.delete(LOCK_KEY)
            except Exception:
                logger.exception("DailyCreditWorker error")

            await asyncio.sleep(self.interval)


if __name__ == "__main__":
    logging.basicConfig(level="INFO", format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    asyncio.run(DailyCreditWorker(interval_seconds=60).run())
