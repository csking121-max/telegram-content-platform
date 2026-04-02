"""
Credit worker — processes queued credit operations.

Reads from ``queue:credit`` in Redis.
Each job: {user_id, amount, reason, operation: "add"|"deduct", job_id?}.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging

from backend.database import AsyncSessionLocal
from backend.engines.credit_engine import CreditEngine
from backend.config import settings
from backend.redis_client import RedisClient

logger = logging.getLogger(__name__)

QUEUE = "queue:credit"
POLL_INTERVAL = settings.WORKER_POLL_INTERVAL
_DEDUP_TTL = 3600  # 1 hour — ignore duplicate jobs within this window


class CreditWorker:
    async def run(self) -> None:
        rc = RedisClient.get()
        logger.info("CreditWorker listening on %s", QUEUE)

        while True:
            raw = rc.client.lpop(QUEUE)
            if not raw:
                await asyncio.sleep(POLL_INTERVAL)
                continue

            try:
                job = json.loads(raw)
                user_id = job["user_id"]
                amount = job["amount"]
                reason = job.get("reason", "worker")
                operation = job.get("operation", "add")

                # Idempotency: derive a dedup key from job content
                job_id = job.get("job_id") or hashlib.sha256(raw.encode() if isinstance(raw, str) else raw).hexdigest()[:16]
                dedup_key = f"credit_job:{job_id}"
                if rc.client.set(dedup_key, "1", nx=True, ex=_DEDUP_TTL) is None:
                    logger.info("Duplicate credit job skipped: %s", job_id)
                    continue

                async with AsyncSessionLocal() as db:
                    engine = CreditEngine(db)
                    if operation == "deduct":
                        credit = await engine.deduct(
                            user_id=user_id, amount=amount, reason=reason,
                        )
                    else:
                        credit = await engine.add(
                            user_id=user_id, amount=amount, reason=reason,
                        )

                if credit:
                    logger.info(
                        "Credit %s user=%d amount=%d → balance=%d",
                        operation, user_id, amount, credit.balance,
                    )
                else:
                    logger.warning(
                        "Credit %s failed user=%d amount=%d", operation, user_id, amount,
                    )
            except Exception as exc:
                logger.exception("CreditWorker error — sending job to DLQ")
                try:
                    rc.send_to_dlq(QUEUE, raw, error=str(exc))
                except Exception:
                    logger.warning("Failed to send job to DLQ")