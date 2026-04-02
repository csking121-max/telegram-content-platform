"""
Tests for CreditEngine — balance queries, add, deduct, admin_set.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engines.credit_engine import CreditEngine
from backend.models.credit import Credit
from backend.models.credit_history import CreditHistory
from backend.models.user import User
from sqlalchemy import select


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(telegram_id=500001, username="credituser")
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def engine(db: AsyncSession) -> CreditEngine:
    return CreditEngine(db)


# ── ensure_account ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_account_creates_new(engine, user):
    credit = await engine.ensure_account(user.id, initial=50)
    assert credit.balance == 50
    assert credit.user_id == user.id


@pytest.mark.asyncio
async def test_ensure_account_returns_existing(engine, db, user):
    db.add(Credit(user_id=user.id, balance=75))
    await db.flush()

    credit = await engine.ensure_account(user.id, initial=0)
    assert credit.balance == 75  # Not overwritten


# ── get_balance ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_balance_no_account(engine, user):
    balance = await engine.get_balance(user.id)
    assert balance == 0


@pytest.mark.asyncio
async def test_get_balance_with_account(engine, db, user):
    db.add(Credit(user_id=user.id, balance=200))
    await db.flush()
    balance = await engine.get_balance(user.id)
    assert balance == 200


# ── add ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_add_credits(engine, user):
    new_balance = await engine.add(user.id, 100, "test_add")
    assert new_balance == 100


@pytest.mark.asyncio
async def test_add_credits_cumulative(engine, user):
    await engine.add(user.id, 50, "first")
    balance = await engine.add(user.id, 30, "second")
    assert balance == 80


@pytest.mark.asyncio
async def test_add_negative_raises(engine, user):
    with pytest.raises(ValueError, match="positive"):
        await engine.add(user.id, -10, "bad")


@pytest.mark.asyncio
async def test_add_records_history(engine, db, user):
    await engine.add(user.id, 100, "grant")
    result = await db.execute(
        select(CreditHistory).where(CreditHistory.user_id == user.id)
    )
    history = list(result.scalars().all())
    assert len(history) == 1
    assert history[0].change_amount == 100
    assert history[0].reason == "grant"


# ── deduct ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_deduct_credits(engine, user):
    await engine.add(user.id, 100, "setup")
    balance = await engine.deduct(user.id, 40, "purchase")
    assert balance == 60


@pytest.mark.asyncio
async def test_deduct_insufficient_raises(engine, user):
    await engine.add(user.id, 10, "small")
    with pytest.raises(ValueError, match="Insufficient"):
        await engine.deduct(user.id, 50, "too_much")


@pytest.mark.asyncio
async def test_deduct_negative_raises(engine, user):
    with pytest.raises(ValueError, match="positive"):
        await engine.deduct(user.id, -5, "bad")


@pytest.mark.asyncio
async def test_deduct_records_history(engine, db, user):
    await engine.add(user.id, 100, "setup")
    await engine.deduct(user.id, 25, "content_access")
    result = await db.execute(
        select(CreditHistory).where(
            CreditHistory.user_id == user.id,
            CreditHistory.change_amount < 0,
        )
    )
    entries = list(result.scalars().all())
    assert len(entries) == 1
    assert entries[0].change_amount == -25


# ── admin_set ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_set(engine, user):
    await engine.add(user.id, 100, "init")
    balance = await engine.admin_set(user.id, 500, "admin_override")
    assert balance == 500


@pytest.mark.asyncio
async def test_admin_set_records_history(engine, db, user):
    await engine.admin_set(user.id, 250, "set_balance")
    result = await db.execute(
        select(CreditHistory).where(CreditHistory.user_id == user.id)
    )
    history = list(result.scalars().all())
    assert len(history) == 1
    assert history[0].change_amount == 250
    assert "admin_set" in history[0].reason