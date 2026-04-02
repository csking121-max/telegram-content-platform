"""
Redis-backed rate limiter (sliding window counter).
"""
from __future__ import annotations

import logging

from fastapi import HTTPException

from backend.config import settings
from backend.redis_client import RedisClient

logger = logging.getLogger(__name__)


class RateLimiter:
    """
    Usage:
        limiter = RateLimiter(redis)
        limiter.check(f"user:{telegram_id}")  # raises 429 if exceeded
    """

    def __init__(
        self,
        redis: RedisClient | None = None,
        max_requests: int | None = None,
        window_seconds: int | None = None,
    ) -> None:
        self.redis = redis or RedisClient.get()
        self.max_requests = max_requests or settings.RATE_LIMIT_REQUESTS
        self.window_seconds = window_seconds or settings.RATE_LIMIT_WINDOW_SECONDS

    def check(self, key: str) -> None:
        """Raise HTTPException(429) if rate limit exceeded."""
        full_key = f"rl:{key}"
        count = self.redis.incr_with_ttl(full_key, self.window_seconds)
        if count > self.max_requests:
            logger.warning("Rate limit exceeded for key=%s (count=%d)", key, count)
            raise HTTPException(
                status_code=429,
                detail="Rate limit exceeded. Please slow down.",
            )

    def remaining(self, key: str) -> int:
        """How many requests left in the current window."""
        count = self.redis.get_int(f"rl:{key}")
        return max(0, self.max_requests - count)