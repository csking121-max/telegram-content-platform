"""Admin endpoints for Dead Letter Queue management."""

from fastapi import APIRouter, Query
from backend.redis_client import RedisClient

router = APIRouter()

QUEUES = ["queue:delivery", "queue:deletion", "queue:credit"]


@router.get("/summary")
async def dlq_summary():
    """Get DLQ item counts per queue."""
    rc = RedisClient.get()
    return {
        q: rc.dlq_length(q)
        for q in QUEUES
    }


@router.get("/items")
async def dlq_items(
    queue: str = Query(..., description="Queue name, e.g. queue:delivery"),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
):
    """List dead-letter items for a specific queue."""
    if queue not in QUEUES:
        return {"detail": "Unknown queue", "items": []}
    rc = RedisClient.get()
    items = rc.get_dlq_items(queue, start=skip, count=limit)
    total = rc.dlq_length(queue)
    return {"queue": queue, "total": total, "items": items}


@router.post("/retry")
async def dlq_retry(
    queue: str = Query(...),
    count: int = Query(1, ge=1, le=100),
):
    """Move items from DLQ back to original queue for retry."""
    if queue not in QUEUES:
        return {"detail": "Unknown queue", "retried": 0}
    rc = RedisClient.get()
    retried = rc.retry_from_dlq(queue, count=count)
    return {"queue": queue, "retried": retried}


@router.delete("/purge")
async def dlq_purge(queue: str = Query(...)):
    """Delete all items from a DLQ."""
    if queue not in QUEUES:
        return {"detail": "Unknown queue", "purged": 0}
    rc = RedisClient.get()
    purged = rc.purge_dlq(queue)
    return {"queue": queue, "purged": purged}
