"""
End-to-end flow test — simulates the full user journey:

1. User registers (get_or_create)
2. Token created for a free pack
3. Access check → ALLOWED
4. Delivery enqueued
5. Credits deducted (for credit-based pack)
6. Referral reward granted

Uses the async test database, no real Redis/Telegram.
"""
from datetime import datetime, timedelta, timezone

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engines.access_control import AccessControlEngine
from backend.engines.credit_engine import CreditEngine
from backend.engines.delivery_engine import DeliveryEngine
from backend.engines.token_service import TokenService
from backend.models.content_pack import ContentPack
from backend.models.credit import Credit
from backend.models.pack_item import PackItem
from backend.models.token import Token
from backend.models.user import User
from backend.services.referral_service import ReferralService
from backend.services.user_service import UserService
from tests.conftest import FakeRedis


@pytest.mark.asyncio
async def test_full_free_pack_flow(db: AsyncSession, fake_redis: FakeRedis):
    """Free pack: register → token → access check → delivery."""
    # 1. User registers
    svc = UserService(db)
    user, created = await svc.get_or_create(telegram_id=5555555, username="e2e_user")
    assert created is True
    assert user.id is not None

    # 2. Create a free pack + token
    pack = ContentPack(title="E2E Free Pack", access_type="free", credit_cost=0, deletion_seconds=60)
    db.add(pack)
    await db.flush()
    item = PackItem(pack_id=pack.id, storage_chat_id=1, storage_message_id=1, media_type="photo", order_index=0)
    db.add(item)
    await db.flush()

    ts = TokenService(db)
    token = await ts.create(pack.id)

    # 3. Access check
    engine = AccessControlEngine(db)
    result = await engine.check(user.telegram_id, token.token)
    assert result.allowed is True

    # 4. Delivery enqueue
    delivery = DeliveryEngine(db, redis=fake_redis)
    summary = await delivery.enqueue_delivery(
        user_id=user.id, telegram_id=user.telegram_id,
        pack_id=pack.id, bot_username="e2e_bot",
    )
    assert summary["total_items"] == 1
    assert fake_redis.queue_length("queue:delivery") == 1

    # 5. Mark token used
    await ts.mark_used(token.token)
    updated = await ts.get(token.token)
    assert updated.used_count == 1


@pytest.mark.asyncio
async def test_credit_pack_flow(db: AsyncSession, fake_redis: FakeRedis):
    """Credit pack: register → fund credits → access check → deduct."""
    svc = UserService(db)
    user, _ = await svc.get_or_create(telegram_id=6666666, username="credit_e2e")

    credit_engine = CreditEngine(db)
    await credit_engine.add(user.id, 200, "e2e_fund")

    pack = ContentPack(title="E2E Credit Pack", access_type="credits", credit_cost=75, credit_mode="per_pack", deletion_seconds=300)
    db.add(pack)
    await db.flush()
    db.add(PackItem(pack_id=pack.id, storage_chat_id=2, storage_message_id=2, media_type="video", order_index=0))
    await db.flush()

    ts = TokenService(db)
    token = await ts.create(pack.id)

    engine = AccessControlEngine(db)
    result = await engine.check(user.telegram_id, token.token)
    assert result.allowed is True
    assert result.credits_deducted == 75

    # access check already deducted 75; user started with 100 (default) + 200 = 300
    balance = await credit_engine.get_balance(user.id)
    assert balance == 225  # 300 - 75


@pytest.mark.asyncio
async def test_referral_reward_flow(db: AsyncSession):
    """Referral: create invite → referee uses → reward granted."""
    svc = UserService(db)
    referrer, _ = await svc.get_or_create(telegram_id=7777777, username="ref_owner")
    referee, _ = await svc.get_or_create(telegram_id=8888888, username="ref_user")

    ref_svc = ReferralService(db)
    invite = await ref_svc.create_invite(referrer.id)

    used = await ref_svc.use_invite(invite.invite_code, referee.id)
    assert used is not None

    granted = await ref_svc.try_grant_reward(referee.id)
    assert granted is True

    credit_engine = CreditEngine(db)
    balance = await credit_engine.get_balance(referrer.id)
    assert balance > 0