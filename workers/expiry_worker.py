"""
Expiry Worker - proactively expires memberships, ad-watch tokens, and stale payment orders.

Runs periodically (every 5 minutes by default).
Uses the ExpiryService from the backend.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from backend.database import AsyncSessionLocal
from backend.services.expiry_service import ExpiryService

logger = logging.getLogger(__name__)


class ExpiryWorker:
    """Periodically runs expiry checks."""

    def __init__(self, interval_seconds: int = 300):
        # Default: every 5 minutes
        self.interval = interval_seconds

    async def run(self) -> None:
        logger.info("ExpiryWorker started (interval=%ds)", self.interval)
        while True:
            try:
                async with AsyncSessionLocal() as db:
                    service = ExpiryService(db)
                    results = await service.run_all()
                    total = sum(results.values())
                    if total > 0:
                        logger.info("Expiry run: %s", results)
                    await db.commit()
            except Exception:
                logger.exception("ExpiryWorker error")

            await asyncio.sleep(self.interval)


if __name__ == "__main__":
    logging.basicConfig(level="INFO", format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
    asyncio.run(ExpiryWorker(interval_seconds=60).run())
