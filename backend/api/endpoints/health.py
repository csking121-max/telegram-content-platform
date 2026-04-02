"""
Health-check endpoint – used by Docker HEALTHCHECK and load balancers.
"""

from fastapi import APIRouter
from sqlalchemy import text

from backend.database import AsyncSessionLocal
from backend.redis_client import RedisClient

router = APIRouter()


@router.get("")
async def health_check():
    """Return 200 when the service is alive."""
    checks: dict = {"api": True, "database": False, "redis": False}

    # ── Postgres ────────────────────────────────────────────────
    try:
        async with AsyncSessionLocal() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:
        pass

    # ── Redis ───────────────────────────────────────────────────
    try:
        rc = RedisClient.get()
        rc.client.ping()
        checks["redis"] = True
    except Exception:
        pass

    healthy = all(checks.values())
    return {"status": "healthy" if healthy else "degraded", "checks": checks}