"""
Tests for ReferralService — invite creation, usage, reward granting.
"""
import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.credit import Credit
from backend.models.user import User
from backend.services.referral_service import ReferralService


@pytest_asyncio.fixture
async def referrer(db: AsyncSession) -> User:
    u = User(telegram_id=1000001, username="referrer")
    db.add(u)
    await db.flush()
    db.add(Credit(user_id=u.id, balance=0))
    await db.flush()
    return u


@pytest_asyncio.fixture
async def referee(db: AsyncSession) -> User:
    u = User(telegram_id=1000002, username="referee")
    db.add(u)
    await db.flush()
    db.add(Credit(user_id=u.id, balance=0))
    await db.flush()
    return u


@pytest_asyncio.fixture
async def svc(db: AsyncSession) -> ReferralService:
    return ReferralService(db)


# ── create_invite ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_invite(svc, referrer):
    ref = await svc.create_invite(referrer.id)
    assert ref.invite_code is not None
    assert len(ref.invite_code) > 0
    assert ref.referrer_user_id == referrer.id


# ── use_invite ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_use_invite(svc, referrer, referee):
    ref = await svc.create_invite(referrer.id)
    used = await svc.use_invite(ref.invite_code, referee.id)
    assert used is not None
    assert used.used_by_user_id == referee.id


@pytest.mark.asyncio
async def test_use_invite_nonexistent(svc, referee):
    result = await svc.use_invite("FAKE-CODE", referee.id)
    assert result is None


@pytest.mark.asyncio
async def test_use_invite_already_used(svc, referrer, referee):
    ref = await svc.create_invite(referrer.id)
    await svc.use_invite(ref.invite_code, referee.id)
    # Try to use again
    result = await svc.use_invite(ref.invite_code, 99999)
    assert result is None


@pytest.mark.asyncio
async def test_cannot_use_own_invite(svc, referrer):
    ref = await svc.create_invite(referrer.id)
    result = await svc.use_invite(ref.invite_code, referrer.id)
    assert result is None


# ── try_grant_reward ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grant_reward(svc, db, referrer, referee):
    ref = await svc.create_invite(referrer.id)
    await svc.use_invite(ref.invite_code, referee.id)
    granted = await svc.try_grant_reward(referee.id)
    assert granted is True

    # Check referrer got credits
    from sqlalchemy import select
    from backend.models.credit import Credit
    result = await db.execute(select(Credit).where(Credit.user_id == referrer.id))
    credit = result.scalar_one()
    assert credit.balance > 0


@pytest.mark.asyncio
async def test_grant_reward_idempotent(svc, referrer, referee):
    ref = await svc.create_invite(referrer.id)
    await svc.use_invite(ref.invite_code, referee.id)
    await svc.try_grant_reward(referee.id)
    second = await svc.try_grant_reward(referee.id)
    assert second is False  # Already granted


# ── get_user_referrals / count ──────────────────────────────────

@pytest.mark.asyncio
async def test_get_user_referrals(svc, referrer):
    await svc.create_invite(referrer.id)
    await svc.create_invite(referrer.id)
    refs = await svc.get_user_referrals(referrer.id)
    assert len(refs) == 2


@pytest.mark.asyncio
async def test_count_successful(svc, referrer, referee):
    ref = await svc.create_invite(referrer.id)
    await svc.use_invite(ref.invite_code, referee.id)
    count = await svc.count_successful(referrer.id)
    assert count == 1