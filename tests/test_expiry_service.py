"""
Tests for Expiry Service — membership, ad-watch token, and payment order expiry.
Also tests DailyCreditService.grant_daily_credits().

Covers:
  - Deleting expired memberships, keeping active ones
  - Marking expired ad-watch tokens as used
  - Expiring stale payment orders (pending / utr_submitted)
  - run_all() aggregation
  - Daily credit granting, skip-if-already-granted, respect disabled setting
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.ad_watch_token import AdWatchToken
from backend.models.credit import Credit
from backend.models.credit_history import CreditHistory
from backend.models.membership import Membership
from backend.models.membership_plan import MembershipPlan
from backend.models.payment_order import PaymentOrder
from backend.models.platform_setting import PlatformSetting
from backend.models.user import User
from backend.services.expiry_service import ExpiryService


_NOW = datetime.now(timezone.utc)


# ── Fixtures ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(telegram_id=800001, username="expiry_user")
    db.add(u)
    await db.flush()
    db.add(Credit(user_id=u.id, balance=0))
    await db.flush()
    return u


@pytest_asyncio.fixture
async def plan(db: AsyncSession) -> MembershipPlan:
    p = MembershipPlan(
        name="expiry_plan", display_name="Expiry Plan",
        access_type="vip", price_inr=Decimal("100"), duration_days=30, is_active=True,
    )
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def expiry_svc(db: AsyncSession) -> ExpiryService:
    return ExpiryService(db)


# ── Membership expiry ──────────────────────────────────────

@pytest.mark.asyncio
async def test_expire_memberships_deletes_expired(db, expiry_svc, user):
    """Expired memberships are soft-expired (kept with expiry_at set to now)."""
    m = Membership(
        user_id=user.id, membership_type="vip",
        start_at=_NOW - timedelta(days=31),
        expiry_at=_NOW - timedelta(days=1),  # expired yesterday
    )
    db.add(m)
    await db.flush()

    count = await expiry_svc.expire_memberships()
    assert count == 1

    result = await db.execute(select(Membership).where(Membership.user_id == user.id))
    row = result.scalar_one_or_none()
    assert row is not None  # soft-expire keeps the row
    # expiry_at was updated to approximately now
    now = datetime.now(timezone.utc)
    assert abs((row.expiry_at - now).total_seconds()) < 5


@pytest.mark.asyncio
async def test_expire_memberships_keeps_active(db, expiry_svc, user):
    """Active memberships are NOT deleted."""
    m = Membership(
        user_id=user.id, membership_type="premium",
        start_at=_NOW - timedelta(days=5),
        expiry_at=_NOW + timedelta(days=25),  # still active
    )
    db.add(m)
    await db.flush()

    count = await expiry_svc.expire_memberships()
    assert count == 0

    result = await db.execute(select(Membership).where(Membership.user_id == user.id))
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_expire_memberships_null_expiry_not_touched(db, expiry_svc, user):
    """Memberships with NULL expiry (lifetime) are NOT deleted."""
    m = Membership(
        user_id=user.id, membership_type="lifetime",
        start_at=_NOW - timedelta(days=100),
        expiry_at=None,
    )
    db.add(m)
    await db.flush()

    count = await expiry_svc.expire_memberships()
    assert count == 0


# ── Ad-watch token expiry ──────────────────────────────────

@pytest.mark.asyncio
async def test_expire_ad_tokens_marks_expired(db, expiry_svc, user):
    """Expired activated ad-watch tokens are marked as used."""
    t = AdWatchToken(
        user_id=user.id, token="ad-expired-001",
        ads_completed=4, ads_required=4,
        activated=True,
        expires_at=_NOW - timedelta(hours=1),  # expired
        used=False,
    )
    db.add(t)
    await db.flush()

    count = await expiry_svc.expire_ad_tokens()
    assert count == 1

    await db.refresh(t)
    assert t.used is True


@pytest.mark.asyncio
async def test_expire_ad_tokens_skips_inactive(db, expiry_svc, user):
    """Non-activated tokens are NOT touched."""
    t = AdWatchToken(
        user_id=user.id, token="ad-inactive-001",
        ads_completed=2, ads_required=4,
        activated=False,
        expires_at=_NOW - timedelta(hours=1),
        used=False,
    )
    db.add(t)
    await db.flush()

    count = await expiry_svc.expire_ad_tokens()
    assert count == 0

    await db.refresh(t)
    assert t.used is False


@pytest.mark.asyncio
async def test_expire_ad_tokens_skips_already_used(db, expiry_svc, user):
    """Already-used tokens are NOT modified again."""
    t = AdWatchToken(
        user_id=user.id, token="ad-used-001",
        ads_completed=4, ads_required=4,
        activated=True,
        expires_at=_NOW - timedelta(hours=1),
        used=True,
    )
    db.add(t)
    await db.flush()

    count = await expiry_svc.expire_ad_tokens()
    assert count == 0


# ── Payment order expiry ───────────────────────────────────

@pytest.mark.asyncio
async def test_expire_payment_orders_pending(db, expiry_svc, user, plan):
    """Pending orders past expiry are set to expired."""
    o = PaymentOrder(
        user_id=user.id, plan_id=plan.id, amount=Decimal("100"),
        upi_id_used="test@upi", order_ref="ORD-EXP-001",
        status="pending",
        expires_at=_NOW - timedelta(minutes=5),
    )
    db.add(o)
    await db.flush()

    count = await expiry_svc.expire_payment_orders()
    assert count == 1

    await db.refresh(o)
    assert o.status == "expired"


@pytest.mark.asyncio
async def test_expire_payment_orders_utr_submitted(db, expiry_svc, user, plan):
    """utr_submitted orders past expiry are also expired."""
    o = PaymentOrder(
        user_id=user.id, plan_id=plan.id, amount=Decimal("100"),
        upi_id_used="test@upi", order_ref="ORD-EXP-002",
        status="utr_submitted",
        expires_at=_NOW - timedelta(minutes=10),
    )
    db.add(o)
    await db.flush()

    count = await expiry_svc.expire_payment_orders()
    assert count == 1

    await db.refresh(o)
    assert o.status == "expired"


@pytest.mark.asyncio
async def test_expire_payment_orders_leaves_verified(db, expiry_svc, user, plan):
    """Verified orders are NOT expired."""
    o = PaymentOrder(
        user_id=user.id, plan_id=plan.id, amount=Decimal("100"),
        upi_id_used="test@upi", order_ref="ORD-EXP-003",
        status="verified",
        expires_at=_NOW - timedelta(minutes=5),
    )
    db.add(o)
    await db.flush()

    count = await expiry_svc.expire_payment_orders()
    assert count == 0

    await db.refresh(o)
    assert o.status == "verified"


# ── run_all() ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_run_all(db, expiry_svc, user, plan):
    """run_all() returns counts from all three sub-routines."""
    # 1 expired membership
    db.add(Membership(
        user_id=user.id, membership_type="vip",
        start_at=_NOW - timedelta(days=31),
        expiry_at=_NOW - timedelta(days=1),
    ))
    # 1 expired ad-watch token
    db.add(AdWatchToken(
        user_id=user.id, token="ad-runall-001",
        ads_completed=4, ads_required=4,
        activated=True,
        expires_at=_NOW - timedelta(hours=1),
        used=False,
    ))
    # 1 expired payment order
    db.add(PaymentOrder(
        user_id=user.id, plan_id=plan.id, amount=Decimal("100"),
        upi_id_used="test@upi", order_ref="ORD-RUNALL-001",
        status="pending",
        expires_at=_NOW - timedelta(minutes=5),
    ))
    await db.flush()

    result = await expiry_svc.run_all()
    assert result["memberships"] == 1
    assert result["ad_tokens"] == 1
    assert result["payment_orders"] == 1


# ── Daily Credit Service ───────────────────────────────────

@pytest.mark.asyncio
async def test_daily_credits_grants_to_new_users(db, user):
    """grant_daily_credits() adds credits to users who haven't received today."""
    from backend.services.daily_credit_service import DailyCreditService
    from backend.services.platform_settings_service import invalidate_settings_cache

    invalidate_settings_cache()
    # Set up platform settings
    db.add(PlatformSetting(key="daily_credits_enabled", value="true"))
    db.add(PlatformSetting(key="daily_credits_amount", value="50"))
    await db.flush()

    svc = DailyCreditService(db)
    count = await svc.grant_daily_credits()
    assert count == 1

    # Check credit balance
    cr = await db.execute(select(Credit).where(Credit.user_id == user.id))
    credit = cr.scalar_one()
    assert credit.balance == 50


@pytest.mark.asyncio
async def test_daily_credits_skips_already_granted(db, user):
    """Running twice on the same day only grants once."""
    from datetime import date
    from backend.services.daily_credit_service import DailyCreditService
    from backend.services.platform_settings_service import invalidate_settings_cache

    invalidate_settings_cache()
    db.add(PlatformSetting(key="daily_credits_enabled", value="true"))
    db.add(PlatformSetting(key="daily_credits_amount", value="50"))
    await db.flush()

    svc = DailyCreditService(db)

    # First run
    count1 = await svc.grant_daily_credits()
    assert count1 == 1

    # Second run same day
    count2 = await svc.grant_daily_credits()
    assert count2 == 0

    # Balance is still 50, not 100
    cr = await db.execute(select(Credit).where(Credit.user_id == user.id))
    assert cr.scalar_one().balance == 50


@pytest.mark.asyncio
async def test_daily_credits_disabled(db, user):
    """When daily_credits_enabled is false, no credits are granted."""
    from backend.services.daily_credit_service import DailyCreditService
    from backend.services.platform_settings_service import invalidate_settings_cache

    invalidate_settings_cache()
    db.add(PlatformSetting(key="daily_credits_enabled", value="false"))
    db.add(PlatformSetting(key="daily_credits_amount", value="50"))
    await db.flush()

    svc = DailyCreditService(db)
    count = await svc.grant_daily_credits()
    assert count == 0
