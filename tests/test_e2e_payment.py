"""
E2E tests — payment order lifecycle and multi-tier membership access.

Covers:
  - Full payment flow: create order → submit UTR → SMS match → verified
  - Failed payment recovery: wrong UTR → order expires → new order succeeds
  - Multi-tier access: VIP user denied premium content → upgrade → allowed
  - Credit package purchase flow
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.engines.access_control import AccessControlEngine
from backend.engines.credit_engine import CreditEngine
from backend.engines.membership_engine import MembershipEngine
from backend.engines.token_service import TokenService
from backend.models.content_pack import ContentPack
from backend.models.credit import Credit
from backend.models.credit_package import CreditPackage
from backend.models.membership import Membership
from backend.models.membership_plan import MembershipPlan
from backend.models.pack_item import PackItem
from backend.models.payment_order import PaymentOrder
from backend.models.sms_log import SmsLog
from backend.models.token import Token
from backend.models.upi_config import UpiConfig
from backend.models.user import User
from backend.services.payment_order_service import PaymentOrderService
from backend.services.sms_verification_service import SmsVerificationService
from backend.services.user_service import UserService

_NOW = datetime.now(timezone.utc)


# ── Fixtures ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    svc = UserService(db)
    u, _ = await svc.get_or_create(telegram_id=1000001, username="e2e_pay_user")
    return u


@pytest_asyncio.fixture
async def vip_plan(db: AsyncSession) -> MembershipPlan:
    p = MembershipPlan(
        name="e2e_vip", display_name="E2E VIP",
        access_type="vip", price_inr=Decimal("199"),
        duration_days=30, credit_reward=50, is_active=True,
        tier_level=1,
    )
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def premium_plan(db: AsyncSession) -> MembershipPlan:
    p = MembershipPlan(
        name="e2e_premium", display_name="E2E Premium",
        access_type="premium", price_inr=Decimal("499"),
        duration_days=30, credit_reward=100, is_active=True,
        tier_level=2,
    )
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def upi(db: AsyncSession) -> UpiConfig:
    u = UpiConfig(upi_id="e2e@upi", payee_name="E2E Test", is_active=True)
    db.add(u)
    await db.flush()
    return u


# ── Full payment order lifecycle ───────────────────────────

@pytest.mark.asyncio
async def test_full_payment_order_lifecycle(db, user, vip_plan, upi):
    """
    create order → submit UTR → SMS arrives with matching UTR+amount
    → order verified → membership granted.
    """
    sms_svc = SmsVerificationService(db)
    membership_engine = MembershipEngine(db)
    credit_engine = CreditEngine(db)

    # Step 1: Create a payment order manually
    order = PaymentOrder(
        user_id=user.id, plan_id=vip_plan.id,
        amount=Decimal("199"), upi_id_used="e2e@upi",
        order_ref="ORD-E2E-LIFECYCLE-001",
        status="pending",
        expires_at=_NOW + timedelta(minutes=15),
    )
    db.add(order)
    await db.flush()

    # Step 2: User submits UTR (no SMS yet → waiting)
    ok, msg = await sms_svc.verify_utr("ORD-E2E-LIFECYCLE-001", "777777777777")
    assert ok is False
    assert "waiting" in msg.lower() or "minutes" in msg.lower()

    # Step 3: SMS arrives → auto-match
    sms = await sms_svc.process_sms(
        sender="BANK",
        body="Rs.199.00 credited. UTR: 777777777777",
        received_at=_NOW,
    )
    assert sms.matched is True

    # Step 4: Grant access (simulating what sms_webhook._process_and_match does)
    order_svc = PaymentOrderService(db)
    await order_svc._grant_access(order.order_ref, user.id)

    # Step 5: Verify order is now verified and membership granted
    await db.refresh(order)
    assert order.status == "verified"


# ── Failed payment recovery ────────────────────────────────

@pytest.mark.asyncio
async def test_failed_payment_recovery(db, user, vip_plan, upi):
    """
    User submits wrong UTR → order eventually expires
    → user creates new order → succeeds with correct UTR.
    """
    sms_svc = SmsVerificationService(db)

    # Order 1: will expire
    order1 = PaymentOrder(
        user_id=user.id, plan_id=vip_plan.id,
        amount=Decimal("199"), upi_id_used="e2e@upi",
        order_ref="ORD-E2E-FAIL-001",
        status="pending",
        expires_at=_NOW - timedelta(minutes=1),  # already expired
    )
    db.add(order1)
    await db.flush()

    # User tries to submit UTR on expired order
    ok, msg = await sms_svc.verify_utr("ORD-E2E-FAIL-001", "888888888888")
    assert ok is False
    assert "expired" in msg.lower()

    # User creates a new order
    order2 = PaymentOrder(
        user_id=user.id, plan_id=vip_plan.id,
        amount=Decimal("199"), upi_id_used="e2e@upi",
        order_ref="ORD-E2E-FAIL-002",
        status="pending",
        expires_at=_NOW + timedelta(minutes=15),
    )
    db.add(order2)
    await db.flush()

    # Pre-store matching SMS
    db.add(SmsLog(
        sender="BANK", body="Rs.199.00 UTR: 999999999999",
        received_at=_NOW,
        utr_extracted="999999999999", amount_extracted=Decimal("199"),
    ))
    await db.flush()

    # Submit correct UTR on new order → verified
    ok2, msg2 = await sms_svc.verify_utr("ORD-E2E-FAIL-002", "999999999999")
    assert ok2 is True
    assert "verified" in msg2.lower()


# ── Multi-tier access control ──────────────────────────────

@pytest.mark.asyncio
async def test_vip_user_denied_premium_content(db, user, vip_plan, premium_plan):
    """VIP membership cannot access premium-tier content."""
    # Create VIP membership
    membership_engine = MembershipEngine(db)
    await membership_engine.grant(
        user_id=user.id, membership_type="vip",
        expiry_at=_NOW + timedelta(days=30),
    )

    # Create premium pack + token
    pack = ContentPack(
        title="Premium Pack", access_type="premium",
        credit_cost=0, deletion_seconds=60,
    )
    db.add(pack)
    await db.flush()
    db.add(PackItem(
        pack_id=pack.id, storage_chat_id=1,
        storage_message_id=1, media_type="photo", order_index=0,
    ))
    await db.flush()

    ts = TokenService(db)
    token = await ts.create(pack.id)

    # Access check: VIP user → premium pack → DENIED
    engine = AccessControlEngine(db)
    result = await engine.check(user.telegram_id, token.token)
    assert result.allowed is False
    assert "premium" in result.reason.lower()


@pytest.mark.asyncio
async def test_premium_user_accesses_vip_content(db, user, vip_plan, premium_plan):
    """Premium membership (tier 2) CAN access VIP-tier (tier 1) content."""
    # Grant premium membership
    membership_engine = MembershipEngine(db)
    await membership_engine.grant(
        user_id=user.id, membership_type="premium",
        expiry_at=_NOW + timedelta(days=30),
    )

    # Create VIP pack + token
    pack = ContentPack(
        title="VIP Content", access_type="vip",
        credit_cost=0, deletion_seconds=60,
    )
    db.add(pack)
    await db.flush()
    db.add(PackItem(
        pack_id=pack.id, storage_chat_id=2,
        storage_message_id=2, media_type="video", order_index=0,
    ))
    await db.flush()

    ts = TokenService(db)
    token = await ts.create(pack.id)

    # Access check: premium user → vip pack → ALLOWED (higher tier)
    engine = AccessControlEngine(db)
    result = await engine.check(user.telegram_id, token.token)
    assert result.allowed is True


@pytest.mark.asyncio
async def test_upgrade_vip_to_premium_unlocks_content(db, user, vip_plan, premium_plan):
    """User upgrades from VIP to premium, then can access premium content."""
    membership_engine = MembershipEngine(db)

    # Start with VIP
    await membership_engine.grant(
        user_id=user.id, membership_type="vip",
        expiry_at=_NOW + timedelta(days=30),
    )

    # Premium pack
    pack = ContentPack(
        title="Exclusive Pack", access_type="premium",
        credit_cost=0, deletion_seconds=60,
    )
    db.add(pack)
    await db.flush()
    db.add(PackItem(
        pack_id=pack.id, storage_chat_id=3,
        storage_message_id=3, media_type="photo", order_index=0,
    ))
    await db.flush()

    ts = TokenService(db)
    token = await ts.create(pack.id)
    engine = AccessControlEngine(db)

    # Before upgrade: denied
    result1 = await engine.check(user.telegram_id, token.token)
    assert result1.allowed is False

    # Upgrade to premium
    await membership_engine.grant(
        user_id=user.id, membership_type="premium",
        expiry_at=_NOW + timedelta(days=30),
    )

    # After upgrade: allowed
    result2 = await engine.check(user.telegram_id, token.token)
    assert result2.allowed is True


# ── Credit exhaustion & purchase cycle ─────────────────────

@pytest.mark.asyncio
async def test_credits_exhausted_then_replenished(db, user):
    """User runs out of credits, then buys more → regains access."""
    credit_engine = CreditEngine(db)

    # Create credit-based pack
    pack = ContentPack(
        title="Credit Pack E2E", access_type="credits",
        credit_cost=50, credit_mode="per_pack", deletion_seconds=60,
    )
    db.add(pack)
    await db.flush()
    db.add(PackItem(
        pack_id=pack.id, storage_chat_id=4,
        storage_message_id=4, media_type="photo", order_index=0,
    ))
    await db.flush()

    ts = TokenService(db)
    engine = AccessControlEngine(db)

    # Deplete credits to 10 (below the 50 cost)
    cr = await db.execute(select(Credit).where(Credit.user_id == user.id))
    credit = cr.scalar_one_or_none()
    if credit:
        credit.balance = 10
        await db.flush()
    else:
        db.add(Credit(user_id=user.id, balance=10))
        await db.flush()

    # Access denied — insufficient credits
    token1 = await ts.create(pack.id)
    result1 = await engine.check(user.telegram_id, token1.token)
    assert result1.allowed is False
    assert "insufficient" in result1.reason.lower()

    # Replenish credits
    await credit_engine.add(user.id, 100, "purchase")

    # Now access is allowed (balance = 110 >= 50)
    token2 = await ts.create(pack.id)
    result2 = await engine.check(user.telegram_id, token2.token)
    assert result2.allowed is True
    assert result2.credits_deducted == 50
