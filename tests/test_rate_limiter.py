"""
Tests for RateLimiter — Redis-backed sliding window.
"""
import pytest
from unittest.mock import patch

from fastapi import HTTPException

from backend.security.rate_limiter import RateLimiter
from tests.conftest import FakeRedis


@pytest.fixture
def limiter(fake_redis: FakeRedis) -> RateLimiter:
    return RateLimiter(redis=fake_redis, max_requests=5, window_seconds=60)


def test_allows_under_limit(limiter):
    """Requests under limit should not raise."""
    for _ in range(5):
        limiter.check("user:1")  # Should not raise


def test_blocks_over_limit(limiter):
    """Exceeding the limit should raise 429."""
    for _ in range(5):
        limiter.check("user:2")
    with pytest.raises(HTTPException) as exc_info:
        limiter.check("user:2")
    assert exc_info.value.status_code == 429


def test_different_keys_independent(limiter):
    """Different keys have separate counters."""
    for _ in range(5):
        limiter.check("user:a")
    # user:b should still be allowed
    limiter.check("user:b")  # Should not raise


def test_remaining_count(limiter):
    """remaining() should reflect used requests."""
    assert limiter.remaining("user:3") == 5
    limiter.check("user:3")
    assert limiter.remaining("user:3") == 4
    for _ in range(4):
        limiter.check("user:3")
    assert limiter.remaining("user:3") == 0