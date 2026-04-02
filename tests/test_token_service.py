"""
Tests for TokenService — creation, validation, usage tracking.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engines.token_service import TokenService
from backend.models.content_pack import ContentPack
from backend.models.token import Token
from backend.models.user import User


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(telegram_id=700001, username="tokenuser")
    db.add(u)
    await db.flush()
    return u


@pytest_asyncio.fixture
async def pack(db: AsyncSession) -> ContentPack:
    p = ContentPack(title="Token Pack", access_type="free", credit_cost=0)
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def svc(db: AsyncSession) -> TokenService:
    return TokenService(db)


# ── create ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_token(svc, pack):
    token = await svc.create(pack.id, expires_in_hours=48)
    assert token.pack_id == pack.id
    assert len(token.token) > 20
    assert token.expires_at > datetime.now(timezone.utc)
    assert token.used_count == 0


@pytest.mark.asyncio
async def test_create_single_use_token(svc, pack):
    token = await svc.create(pack.id, single_use=True)
    assert token.single_use is True


@pytest.mark.asyncio
async def test_create_bound_token(svc, pack, user):
    token = await svc.create(pack.id, bound_user_id=user.id)
    assert token.bound_user_id == user.id


# ── validate ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_validate_valid_token(svc, pack):
    token = await svc.create(pack.id)
    ok, reason = await svc.validate(token.token)
    assert ok is True
    assert reason == "Valid"


@pytest.mark.asyncio
async def test_validate_nonexistent_token(svc):
    ok, reason = await svc.validate("does-not-exist")
    assert ok is False
    assert "not found" in reason.lower()


@pytest.mark.asyncio
async def test_validate_expired_token(svc, db, pack):
    token = await svc.create(pack.id, expires_in_hours=1)
    # Manually expire it
    token.expires_at = datetime.now(timezone.utc) - timedelta(hours=1)
    await db.flush()

    ok, reason = await svc.validate(token.token)
    assert ok is False
    assert "expired" in reason.lower()


@pytest.mark.asyncio
async def test_validate_used_single_use(svc, db, pack):
    token = await svc.create(pack.id, single_use=True)
    token.used_count = 1
    await db.flush()

    ok, reason = await svc.validate(token.token)
    assert ok is False
    assert "used" in reason.lower()


@pytest.mark.asyncio
async def test_validate_bound_wrong_user(svc, pack, user):
    token = await svc.create(pack.id, bound_user_id=user.id)
    ok, reason = await svc.validate(token.token, user_id=99999)
    assert ok is False
    assert "bound" in reason.lower()


@pytest.mark.asyncio
async def test_validate_bound_correct_user(svc, pack, user):
    token = await svc.create(pack.id, bound_user_id=user.id)
    ok, reason = await svc.validate(token.token, user_id=user.id)
    assert ok is True


# ── mark_used ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_mark_used_increments(svc, pack):
    token = await svc.create(pack.id)
    assert token.used_count == 0

    updated = await svc.mark_used(token.token)
    assert updated.used_count == 1


@pytest.mark.asyncio
async def test_mark_used_nonexistent_raises(svc):
    with pytest.raises(ValueError, match="not found"):
        await svc.mark_used("ghost-token")


# ── get / get_pack_for_token ────────────────────────────────────

@pytest.mark.asyncio
async def test_get_returns_token(svc, pack):
    created = await svc.create(pack.id)
    found = await svc.get(created.token)
    assert found is not None
    assert found.token == created.token


@pytest.mark.asyncio
async def test_get_pack_for_token(svc, pack):
    token = await svc.create(pack.id)
    found_pack = await svc.get_pack_for_token(token.token)
    assert found_pack is not None
    assert found_pack.id == pack.id