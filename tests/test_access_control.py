"""
Tests for AccessControlEngine.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engines.access_control import AccessControlEngine
from backend.models.content_pack import ContentPack
from backend.models.credit import Credit
from backend.models.membership import Membership
from backend.models.token import Token
from backend.models.user import User


@pytest_asyncio.fixture
async def engine(db: AsyncSession) -> AccessControlEngine:
    return AccessControlEngine(db)


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(telegram_id=111111, username="acluser", level=1)
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def free_pack(db: AsyncSession) -> ContentPack:
    p = ContentPack(title="Free Pack", access_type="free", credit_cost=0)
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def credit_pack(db: AsyncSession) -> ContentPack:
    p = ContentPack(title="Credit Pack", access_type="credits", credit_cost=50, credit_mode="per_pack")
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def vip_pack(db: AsyncSession) -> ContentPack:
    p = ContentPack(title="VIP Pack", access_type="vip", credit_cost=0)
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def free_token(db: AsyncSession, free_pack: ContentPack) -> Token:
    t = Token(
        token="free-token-001",
        pack_id=free_pack.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        single_use=False,
        used_count=0,
    )
    db.add(t)
    await db.flush()
    return t


# ── Access allowed tests ────────────────────────────────────────


@pytest.mark.asyncio
async def test_free_pack_allowed(engine, user, free_token):
    result = await engine.check(user.telegram_id, free_token.token)
    assert result.allowed is True
    assert result.pack_id == free_token.pack_id


@pytest.mark.asyncio
async def test_credit_pack_allowed_with_balance(engine, db, user, credit_pack):
    # Give user enough credits
    db.add(Credit(user_id=user.id, balance=100))
    token = Token(
        token="credit-token-001", pack_id=credit_pack.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        single_use=False, used_count=0,
    )
    db.add(token)
    await db.flush()

    result = await engine.check(user.telegram_id, "credit-token-001")
    assert result.allowed is True


@pytest.mark.asyncio
async def test_vip_pack_allowed_with_membership(engine, db, user, vip_pack):
    db.add(Membership(
        user_id=user.id, membership_type="vip",
        expiry_at=datetime.now(timezone.utc) + timedelta(days=30),
    ))
    token = Token(
        token="vip-token-001", pack_id=vip_pack.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        single_use=False, used_count=0,
    )
    db.add(token)
    await db.flush()

    result = await engine.check(user.telegram_id, "vip-token-001")
    assert result.allowed is True


# ── Access denied tests ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_invalid_token(engine, user):
    result = await engine.check(user.telegram_id, "nonexistent-token")
    assert result.allowed is False
    assert "not exist" in result.reason.lower()


@pytest.mark.asyncio
async def test_expired_token(engine, db, user, free_pack):
    t = Token(
        token="expired-token",
        pack_id=free_pack.id,
        expires_at=datetime.now(timezone.utc) - timedelta(hours=1),
        single_use=False, used_count=0,
    )
    db.add(t)
    await db.flush()

    result = await engine.check(user.telegram_id, "expired-token")
    assert result.allowed is False
    assert "expired" in result.reason.lower()


@pytest.mark.asyncio
async def test_single_use_token_already_used(engine, db, user, free_pack):
    t = Token(
        token="single-use-token",
        pack_id=free_pack.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        single_use=True, used_count=1,  # already used
    )
    db.add(t)
    await db.flush()

    result = await engine.check(user.telegram_id, "single-use-token")
    assert result.allowed is False
    assert "used" in result.reason.lower()


@pytest.mark.asyncio
async def test_token_bound_to_different_user(engine, db, user, free_pack):
    t = Token(
        token="bound-token",
        pack_id=free_pack.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        single_use=False, used_count=0,
        bound_user_id=99999,  # different user
    )
    db.add(t)
    await db.flush()

    result = await engine.check(user.telegram_id, "bound-token")
    assert result.allowed is False
    assert "bound" in result.reason.lower()


@pytest.mark.asyncio
async def test_blocked_user(engine, db, free_token):
    blocked_user = User(
        telegram_id=222222, username="blocked",
        blocked_until=datetime.now(timezone.utc) + timedelta(days=1),
    )
    db.add(blocked_user)
    await db.flush()

    result = await engine.check(blocked_user.telegram_id, free_token.token)
    assert result.allowed is False
    assert "blocked" in result.reason.lower()


@pytest.mark.asyncio
async def test_unregistered_user(engine, free_token):
    result = await engine.check(telegram_id=999999, token_str=free_token.token)
    assert result.allowed is False
    assert "not registered" in result.reason.lower()


@pytest.mark.asyncio
async def test_insufficient_credits(engine, db, user, credit_pack):
    db.add(Credit(user_id=user.id, balance=10))  # Need 50
    token = Token(
        token="low-credit-token", pack_id=credit_pack.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        single_use=False, used_count=0,
    )
    db.add(token)
    await db.flush()

    result = await engine.check(user.telegram_id, "low-credit-token")
    assert result.allowed is False
    assert "insufficient" in result.reason.lower()


@pytest.mark.asyncio
async def test_vip_pack_denied_without_membership(engine, db, user, vip_pack):
    token = Token(
        token="vip-no-member", pack_id=vip_pack.id,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
        single_use=False, used_count=0,
    )
    db.add(token)
    await db.flush()

    result = await engine.check(user.telegram_id, "vip-no-member")
    assert result.allowed is False
    assert "vip" in result.reason.lower()
    assert result.upgrade_options is not None