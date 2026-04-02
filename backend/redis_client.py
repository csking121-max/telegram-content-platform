"""
Redis client singleton used for queuing and caching.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Optional

import redis

from backend.config import settings

logger = logging.getLogger(__name__)


class RedisClient:
    """Thin wrapper around ``redis.Redis`` with helpers for our queue pattern."""

    _instance: Optional["RedisClient"] = None

    def __init__(self) -> None:
        self._pool = redis.ConnectionPool.from_url(
            settings.REDIS_URL,
            decode_responses=True,
            max_connections=20,
        )
        self._client = redis.Redis(connection_pool=self._pool)
        try:
            self._client.ping()
            logger.info("Redis connected → %s", settings.REDIS_URL)
        except Exception:
            logger.warning("Redis not reachable at %s — queues will fail until Redis is available", settings.REDIS_URL)

    # ── Singleton accessor ───────────────────────────
    @classmethod
    def get(cls) -> "RedisClient":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    @property
    def client(self) -> redis.Redis:
        return self._client

    # ── Queue helpers ────────────────────────────────
    def enqueue(self, queue_name: str, data: dict | str) -> None:
        payload = json.dumps(data) if isinstance(data, dict) else data
        self._client.lpush(queue_name, payload)

    def dequeue(self, queue_name: str, timeout: int = 0) -> Optional[str]:
        if timeout:
            result = self._client.brpop(queue_name, timeout=timeout)
            return result[1] if result else None
        return self._client.rpop(queue_name)

    def queue_length(self, queue_name: str) -> int:
        return self._client.llen(queue_name)

    # ── Dead Letter Queue helpers ────────────────────
    def send_to_dlq(self, original_queue: str, data: dict | str, error: str = "") -> None:
        """Move a failed job to the dead-letter queue for later inspection/retry."""
        import time as _time
        payload = {
            "original_queue": original_queue,
            "job": data if isinstance(data, dict) else json.loads(data),
            "error": error,
            "failed_at": _time.time(),
        }
        self._client.lpush("dlq:" + original_queue, json.dumps(payload))

    def get_dlq_items(self, queue_name: str, start: int = 0, count: int = 50) -> list[dict]:
        """Fetch items from a dead-letter queue."""
        raw_items = self._client.lrange("dlq:" + queue_name, start, start + count - 1)
        items = []
        for raw in raw_items:
            try:
                items.append(json.loads(raw))
            except (json.JSONDecodeError, TypeError):
                items.append({"raw": str(raw)})
        return items

    def dlq_length(self, queue_name: str) -> int:
        return self._client.llen("dlq:" + queue_name)

    def retry_from_dlq(self, queue_name: str, count: int = 1) -> int:
        """Move items from DLQ back to the original queue for retry."""
        retried = 0
        for _ in range(count):
            raw = self._client.rpop("dlq:" + queue_name)
            if not raw:
                break
            try:
                item = json.loads(raw)
                job = item.get("job", item)
                self._client.lpush(queue_name, json.dumps(job))
                retried += 1
            except (json.JSONDecodeError, TypeError):
                pass
        return retried

    def purge_dlq(self, queue_name: str) -> int:
        """Delete all items from a DLQ. Returns count deleted."""
        length = self._client.llen("dlq:" + queue_name)
        if length:
            self._client.delete("dlq:" + queue_name)
        return length

    # ── Rate-limit helpers ───────────────────────────
    def incr_with_ttl(self, key: str, ttl: int) -> int:
        pipe = self._client.pipeline()
        pipe.incr(key)
        pipe.expire(key, ttl)
        results = pipe.execute()
        return results[0]

    def get_int(self, key: str) -> int:
        val = self._client.get(key)
        return int(val) if val else 0

    # ── Generic helpers ──────────────────────────────
    def set_json(self, key: str, data: Any, ttl: int | None = None) -> None:
        self._client.set(key, json.dumps(data), ex=ttl)

    def get_json(self, key: str) -> Any:
        raw = self._client.get(key)
        return json.loads(raw) if raw else None

    def close(self) -> None:
        self._pool.disconnect()


def get_redis() -> RedisClient:
    """FastAPI dependency."""
    return RedisClient.get()


def _get_pool() -> redis.ConnectionPool:
    """Lazy pool accessor for workers that import ``redis_pool`` at module level."""
    return RedisClient.get()._pool


class _LazyPool:
    """Proxy so ``from backend.redis_client import redis_pool`` works at import time."""
    def __getattr__(self, name: str):
        return getattr(_get_pool(), name)


redis_pool = _LazyPool()