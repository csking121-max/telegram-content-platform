"""
Tests for MembershipEngine — grant, revoke, get_active, has_type.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engines.membership_engine import MembershipEngine
from backend.models.membership import Membership
from backend.models.user import User


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(telegram_id=800001, username="memberuser")
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def engine(db: AsyncSession) -> MembershipEngine:
    return MembershipEngine(db)


# ── grant ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_grant_membership(engine, user):
    m = await engine.grant(user.id, "vip")
    assert m.user_id == user.id
    assert m.membership_type == "vip"
    assert m.id is not None


@pytest.mark.asyncio
async def test_grant_with_expiry(engine, user):
    exp = datetime.now(timezone.utc) + timedelta(days=7)
    m = await engine.grant(user.id, "premium", expiry_at=exp)
    assert m.expiry_at is not None


# ── get_active ──────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_active_returns_valid(engine, user):
    await engine.grant(user.id, "vip", expiry_at=datetime.now(timezone.utc) + timedelta(days=30))
    active = await engine.get_active(user.id)
    assert len(active) == 1
    assert active[0].membership_type == "vip"


@pytest.mark.asyncio
async def test_get_active_excludes_expired(engine, db, user):
    m = Membership(
        user_id=user.id, membership_type="old",
        expiry_at=datetime.now(timezone.utc) - timedelta(days=1),
    )
    db.add(m)
    await db.flush()

    active = await engine.get_active(user.id)
    assert len(active) == 0


@pytest.mark.asyncio
async def test_get_active_includes_no_expiry(engine, user):
    await engine.grant(user.id, "lifetime")  # No expiry
    active = await engine.get_active(user.id)
    assert len(active) == 1


# ── has_type ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_has_type_true(engine, user):
    await engine.grant(user.id, "vip", expiry_at=datetime.now(timezone.utc) + timedelta(days=30))
    assert await engine.has_type(user.id, "vip") is True


@pytest.mark.asyncio
async def test_has_type_false(engine, user):
    assert await engine.has_type(user.id, "vip") is False


# ── revoke ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_revoke_membership(engine, user):
    m = await engine.grant(user.id, "vip", expiry_at=datetime.now(timezone.utc) + timedelta(days=30))
    revoked = await engine.revoke(m.id)
    assert revoked is True

    # Should no longer be active
    active = await engine.get_active(user.id)
    assert len(active) == 0


@pytest.mark.asyncio
async def test_revoke_nonexistent(engine):
    result = await engine.revoke(99999)
    assert result is False


# ── get_user_memberships ────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_all_memberships(engine, user):
    await engine.grant(user.id, "vip")
    await engine.grant(user.id, "premium")
    all_m = await engine.get_user_memberships(user.id)
    assert len(all_m) == 2