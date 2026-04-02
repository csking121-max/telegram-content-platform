"""
Reusable FastAPI dependencies.
"""
from __future__ import annotations

from fastapi import Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.database import get_async_session
from backend.redis_client import RedisClient, get_redis


async def get_db(session: AsyncSession = Depends(get_async_session)) -> AsyncSession:
    """Alias for route injection — keeps endpoint signatures clean."""
    return session


def get_redis_client(rc: RedisClient = Depends(get_redis)) -> RedisClient:
    """Alias for route injection."""
    return rc