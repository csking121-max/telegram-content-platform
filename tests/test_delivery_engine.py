"""
Tests for DeliveryEngine — enqueue, record, deletion scheduling.
"""
import json
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engines.delivery_engine import DeliveryEngine
from backend.models.content_pack import ContentPack
from backend.models.delivered_message import DeliveredMessage
from backend.models.pack_item import PackItem
from backend.models.user import User
from backend.models.bot import Bot
from tests.conftest import FakeRedis


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(telegram_id=600001, username="delivuser")
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def bot(db: AsyncSession) -> Bot:
    b = Bot(bot_username="deliv_bot", bot_token="tok", webhook_secret="sec")
    db.add(b)
    await db.flush()
    return b


@pytest_asyncio.fixture
async def pack_with_items(db: AsyncSession):
    pack = ContentPack(title="Delivery Pack", access_type="free", credit_cost=0, deletion_seconds=3600)
    db.add(pack)
    await db.flush()
    items = []
    for i in range(5):
        item = PackItem(
            pack_id=pack.id, storage_chat_id=1000 + i,
            storage_message_id=2000 + i, media_type="photo", order_index=i,
        )
        db.add(item)
        items.append(item)
    await db.flush()
    return pack, items


@pytest_asyncio.fixture
async def engine(db: AsyncSession, fake_redis: FakeRedis) -> DeliveryEngine:
    return DeliveryEngine(db, redis=fake_redis)


# ── enqueue_delivery ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_enqueue_delivery_creates_jobs(engine, fake_redis, user, pack_with_items):
    pack, items = pack_with_items
    result = await engine.enqueue_delivery(
        user_id=user.id, telegram_id=user.telegram_id,
        pack_id=pack.id, bot_username="deliv_bot",
    )
    assert result["total_items"] == 5
    assert result["batches"] >= 1
    assert fake_redis.queue_length("queue:delivery") >= 1


@pytest.mark.asyncio
async def test_enqueue_empty_pack(engine, db, user):
    pack = ContentPack(title="Empty", access_type="free", credit_cost=0)
    db.add(pack)
    await db.flush()

    result = await engine.enqueue_delivery(
        user_id=user.id, telegram_id=user.telegram_id,
        pack_id=pack.id, bot_username="deliv_bot",
    )
    assert "error" in result


@pytest.mark.asyncio
async def test_enqueue_delivery_job_structure(engine, fake_redis, user, pack_with_items):
    pack, items = pack_with_items
    await engine.enqueue_delivery(
        user_id=user.id, telegram_id=user.telegram_id,
        pack_id=pack.id, bot_username="deliv_bot",
    )
    raw = fake_redis.dequeue("queue:delivery")
    job = json.loads(raw)
    assert "user_id" in job
    assert "telegram_id" in job
    assert "items" in job
    assert isinstance(job["items"], list)
    assert job["items"][0]["media_type"] == "photo"


# ── record_delivered ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_record_delivered_with_deletion(engine, db, user, bot, fake_redis):
    await engine.record_delivered(
        user_id=user.id, bot_id=bot.id,
        telegram_message_id=12345, chat_id=user.telegram_id,
        deletion_seconds=3600,
    )
    await db.flush()

    from sqlalchemy import select
    result = await db.execute(select(DeliveredMessage))
    msgs = list(result.scalars().all())
    assert len(msgs) == 1
    assert msgs[0].telegram_message_id == 12345
    assert fake_redis.queue_length("queue:deletion") == 1


@pytest.mark.asyncio
async def test_record_delivered_without_deletion(engine, db, user, bot, fake_redis):
    await engine.record_delivered(
        user_id=user.id, bot_id=bot.id,
        telegram_message_id=99999, chat_id=user.telegram_id,
        deletion_seconds=None,
    )
    await db.flush()

    from sqlalchemy import select
    result = await db.execute(select(DeliveredMessage))
    msgs = list(result.scalars().all())
    assert len(msgs) == 1
    assert fake_redis.queue_length("queue:deletion") == 0