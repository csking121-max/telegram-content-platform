"""
Tests for worker modules — unit tests for processing functions.

Workers depend on Redis and DB, so we test the logic with mocks.
"""
import json

import pytest
from tests.conftest import FakeRedis


# ── Queue operation tests ───────────────────────────────────────

def test_fake_redis_enqueue_dequeue():
    """Verify FakeRedis queue behaves like real Redis (FIFO via LPUSH/RPOP)."""
    r = FakeRedis()
    r.enqueue("test_q", {"id": 1})
    r.enqueue("test_q", {"id": 2})
    assert r.queue_length("test_q") == 2

    first = json.loads(r.dequeue("test_q"))
    assert first["id"] == 1

    second = json.loads(r.dequeue("test_q"))
    assert second["id"] == 2

    assert r.dequeue("test_q") is None


def test_delivery_job_format():
    """Verify delivery jobs have the expected structure."""
    job = {
        "user_id": 1,
        "telegram_id": 123456,
        "bot_username": "test_bot",
        "pack_id": 10,
        "batch_index": 0,
        "total_batches": 1,
        "items": [
            {
                "pack_item_id": 1,
                "storage_chat_id": 100,
                "storage_message_id": 200,
                "media_type": "photo",
                "order_index": 0,
            }
        ],
        "deletion_seconds": 3600,
        "delay_ms": 500,
    }
    r = FakeRedis()
    r.enqueue("queue:delivery", job)
    raw = r.dequeue("queue:delivery")
    parsed = json.loads(raw)
    assert parsed["user_id"] == 1
    assert len(parsed["items"]) == 1
    assert parsed["items"][0]["media_type"] == "photo"


def test_deletion_job_format():
    """Verify deletion jobs have the expected structure."""
    job = {
        "delivered_message_id": 42,
        "telegram_message_id": 9999,
        "chat_id": 123456,
        "bot_id": 1,
        "delete_at": "2024-01-01T12:00:00+00:00",
    }
    r = FakeRedis()
    r.enqueue("queue:deletion", job)
    raw = r.dequeue("queue:deletion")
    parsed = json.loads(raw)
    assert parsed["delivered_message_id"] == 42
    assert "delete_at" in parsed


def test_credit_job_format():
    """Verify credit worker job format."""
    job = {
        "user_id": 5,
        "operation": "add",
        "amount": 100,
        "reason": "payment:REF-001",
    }
    r = FakeRedis()
    r.enqueue("queue:credit", job)
    raw = r.dequeue("queue:credit")
    parsed = json.loads(raw)
    assert parsed["operation"] == "add"
    assert parsed["amount"] == 100


# ── Rate-limit counter tests ───────────────────────────────────

def test_fake_redis_incr_with_ttl():
    r = FakeRedis()
    assert r.incr_with_ttl("rl:test", 60) == 1
    assert r.incr_with_ttl("rl:test", 60) == 2
    assert r.get_int("rl:test") == 2


def test_fake_redis_json():
    r = FakeRedis()
    r.set_json("cache:user:1", {"name": "test", "balance": 100})
    data = r.get_json("cache:user:1")
    assert data["name"] == "test"
    assert data["balance"] == 100

    assert r.get_json("nonexistent") is None