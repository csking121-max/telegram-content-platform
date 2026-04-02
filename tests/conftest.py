"""
Shared pytest fixtures for the Telegram Content Platform test suite.

Uses an async SQLite in-memory database so tests don't require PostgreSQL/Redis.
"""
from __future__ import annotations

import asyncio
import json
import os
from datetime import datetime, timedelta, timezone
from typing import AsyncGenerator
from unittest.mock import MagicMock

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from backend.database import Base
from backend.models import (
    Bot,
    ContentPack,
    Credit,
    Membership,
    PackItem,
    Payment,
    Token,
    User,
)

# ── Override settings BEFORE importing app ──────────────────────

os.environ.setdefault("DATABASE_URL", "sqlite+aiosqlite:///")
os.environ.setdefault("DATABASE_URL_SYNC", "sqlite:///")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/15")
os.environ.setdefault("ADMIN_USERNAME", "admin")
os.environ.setdefault("ADMIN_PASSWORD", "testpass")
os.environ.setdefault("ADMIN_JWT_SECRET", "test-jwt-secret")
os.environ.setdefault("TELEGRAM_BOTS", "testbot:123456:test_hmac_secret")


# ── Async engine for tests (SQLite in-memory) ──────────────────

TEST_DATABASE_URL = "sqlite+aiosqlite://"

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)
TestSessionLocal = async_sessionmaker(
    bind=test_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ── Event loop ──────────────────────────────────────────────────

@pytest.fixture(scope="session")
def event_loop():
    """Use a single event loop for the whole test session."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


# ── Database setup / teardown ───────────────────────────────────

@pytest_asyncio.fixture(autouse=True)
async def setup_database():
    """Create all tables before each test, drop after."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def db() -> AsyncGenerator[AsyncSession, None]:
    """Provide a clean async session per test."""
    async with TestSessionLocal() as session:
        yield session
        await session.rollback()


# ── Mock Redis ──────────────────────────────────────────────────

class FakeRedis:
    """In-memory fake Redis for testing queue operations."""

    def __init__(self):
        self._data: dict[str, list] = {}
        self._kv: dict[str, str] = {}
        self._ttl: dict[str, int] = {}

    def enqueue(self, queue_name: str, data: dict | str) -> None:
        payload = json.dumps(data) if isinstance(data, dict) else data
        self._data.setdefault(queue_name, []).insert(0, payload)

    def dequeue(self, queue_name: str, timeout: int = 0) -> str | None:
        lst = self._data.get(queue_name, [])
        return lst.pop() if lst else None

    def queue_length(self, queue_name: str) -> int:
        return len(self._data.get(queue_name, []))

    def incr_with_ttl(self, key: str, ttl: int) -> int:
        val = int(self._kv.get(key, "0")) + 1
        self._kv[key] = str(val)
        self._ttl[key] = ttl
        return val

    def get_int(self, key: str) -> int:
        return int(self._kv.get(key, "0"))

    def set_json(self, key: str, data, ttl: int | None = None) -> None:
        self._kv[key] = json.dumps(data)

    def get_json(self, key: str):
        raw = self._kv.get(key)
        return json.loads(raw) if raw else None

    @property
    def client(self):
        mock = MagicMock()
        mock.ping.return_value = True
        return mock

    def close(self):
        pass


@pytest.fixture
def fake_redis() -> FakeRedis:
    return FakeRedis()


# ── Sample data fixtures ────────────────────────────────────────

@pytest_asyncio.fixture
async def sample_user(db: AsyncSession) -> User:
    user = User(telegram_id=123456789, username="testuser", level=1)
    db.add(user)
    await db.flush()
    return user


@pytest_asyncio.fixture
async def sample_bot(db: AsyncSession) -> Bot:
    bot = Bot(
        bot_username="testbot",
        bot_token="123456:ABC-DEF",
        webhook_secret="test_hmac_secret",
        status="active",
    )
    db.add(bot)
    await db.flush()
    return bot


@pytest_asyncio.fixture
async def sample_pack(db: AsyncSession) -> ContentPack:
    pack = ContentPack(
        title="Test Pack",
        description="A test content pack",
        access_type="free",
        credit_cost=0,
        deletion_seconds=3600,
    )
    db.add(pack)
    await db.flush()
    return pack


@pytest_asyncio.fixture
async def sample_pack_items(db: AsyncSession, sample_pack: ContentPack) -> list[PackItem]:
    items = []
    for i in range(3):
        item = PackItem(
            pack_id=sample_pack.id,
            storage_chat_id=100000 + i,
            storage_message_id=200000 + i,
            media_type="photo" if i % 2 == 0 else "video",
            order_index=i,
        )
        db.add(item)
        items.append(item)
    await db.flush()
    return items


@pytest_asyncio.fixture
async def sample_token(db: AsyncSession, sample_pack: ContentPack, sample_user: User) -> Token:
    token = Token(
        token="test-token-abc",
        pack_id=sample_pack.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        single_use=False,
        bound_user_id=None,
        used_count=0,
    )
    db.add(token)
    await db.flush()
    return token


@pytest_asyncio.fixture
async def sample_credit(db: AsyncSession, sample_user: User) -> Credit:
    credit = Credit(user_id=sample_user.id, balance=100)
    db.add(credit)
    await db.flush()
    return credit


@pytest_asyncio.fixture
async def sample_membership(db: AsyncSession, sample_user: User) -> Membership:
    membership = Membership(
        user_id=sample_user.id,
        membership_type="vip",
        expiry_at=datetime.now(timezone.utc) + timedelta(days=30),
    )
    db.add(membership)
    await db.flush()
    return membership


@pytest_asyncio.fixture
async def sample_payment(db: AsyncSession, sample_user: User) -> Payment:
    payment = Payment(
        user_id=sample_user.id,
        amount=50.00,
        method="card",
        reference="PAY-TEST-001",
        status="pending",
    )
    db.add(payment)
    await db.flush()
    return payment