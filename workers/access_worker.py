"""
Access worker — processes queued access-check jobs.

Reads from ``queue:access`` in Redis, evaluates via AccessControlEngine,
and pushes the result back to a per-request result key.
"""

from __future__ import annotations

import asyncio
import json
import logging

from backend.config import settings
from backend.database import AsyncSessionLocal
from backend.engines.access_control import AccessControlEngine
from backend.config import settings
from backend.redis_client import RedisClient

logger = logging.getLogger(__name__)

QUEUE = "queue:access"
POLL_INTERVAL = settings.WORKER_POLL_INTERVAL


class AccessWorker:
    async def run(self) -> None:
        rc = RedisClient.get()
        logger.info("AccessWorker listening on %s", QUEUE)

        while True:
            raw = rc.client.lpop(QUEUE)
            if not raw:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            try:
                job = json.loads(raw)
                user_id = job["user_id"]
                token = job.get("token", "")
                bot_id = job.get("bot_id", 0)
                result_key = job.get("result_key")

                async with AsyncSessionLocal() as db:
                    engine = AccessControlEngine(db)
                    result = await engine.check(
                        telegram_id=user_id, token_str=token,
                    )

                if result_key:
                    rc.client.setex(result_key, 60, json.dumps(result.model_dump()))

                logger.info("Access check user=%d → %s", user_id, result.status)
            except Exception:
                logger.exception("AccessWorker error")
                await asyncio.sleep(POLL_INTERVAL)