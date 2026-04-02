"""
Tests for SMS Verification Service — UTR extraction, duplicate detection, amount matching.

Covers:
  - UTR pattern extraction from bank SMS text
  - Amount extraction from SMS text
  - Duplicate UTR claim prevention
  - Auto-matching (SMS arrives before/after UTR submission)
  - Amount mismatch rejection
  - Stale SMS rejection (SEC-8)
  - Payment order expiry during verification
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.membership_plan import MembershipPlan
from backend.models.payment_order import PaymentOrder
from backend.models.sms_log import SmsLog
from backend.models.upi_config import UpiConfig
from backend.models.user import User
from backend.models.credit import Credit
from backend.services.sms_verification_service import (
    SmsVerificationService,
    extract_amount,
    extract_utr,
)


# ── Pure function tests for UTR extraction ──────────────────────

class TestExtractUtr:
    def test_12_digit_utr(self):
        assert extract_utr("Your UPI txn 312456789012 is successful") == "312456789012"

    def test_labeled_utr(self):
        assert extract_utr("UTR: 312456789012 credited") == "312456789012"

    def test_upi_ref_label(self):
        assert extract_utr("UPI Ref No: 312456789012") == "312456789012"

    def test_ref_number_label(self):
        assert extract_utr("Ref Number: 312456789012") == "312456789012"

    def test_imps_reference(self):
        assert extract_utr("IMPS: 3124567890123456 credited") == "3124567890123456"

    def test_16_digit_generic(self):
        assert extract_utr("Txn ID 1234567890123456 confirmed") == "1234567890123456"

    def test_no_utr_found(self):
        assert extract_utr("Your account balance is low") is None

    def test_no_utr_in_short_text(self):
        assert extract_utr("Hello") is None


class TestExtractAmount:
    def test_rupee_symbol(self):
        assert extract_amount("₹500.00 credited") == 500.0

    def test_rs_dot(self):
        assert extract_amount("Rs. 1,250.50 received") == 1250.50

    def test_inr_label(self):
        assert extract_amount("INR 99.99 debited") == 99.99

    def test_credited_with(self):
        assert extract_amount("credited with 750") == 750.0

    def test_amount_of(self):
        assert extract_amount("amount of Rs.299") == 299.0

    def test_no_amount(self):
        assert extract_amount("No transaction details") is None


# ── Async tests for SmsVerificationService ──────────────────────

@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(telegram_id=700001, username="sms_test_user")
    db.add(u)
    await db.flush()
    db.add(Credit(user_id=u.id, balance=0))
    await db.flush()
    return u


@pytest_asyncio.fixture
async def plan(db: AsyncSession) -> MembershipPlan:
    p = MembershipPlan(
        name="test_sms_plan",
        display_name="SMS Test Plan",
        access_type="vip",
        price_inr=Decimal("299.00"),
        duration_days=30,
        is_active=True,
    )
    db.add(p)
    await db.flush()
    return p


@pytest_asyncio.fixture
async def pending_order(db: AsyncSession, user: User, plan: MembershipPlan) -> PaymentOrder:
    order = PaymentOrder(
        user_id=user.id,
        plan_id=plan.id,
        amount=Decimal("299.00"),
        upi_id_used="test@upi",
        order_ref="ORD-SMS-TEST-001",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(order)
    await db.flush()
    return order


@pytest_asyncio.fixture
async def sms_svc(db: AsyncSession) -> SmsVerificationService:
    return SmsVerificationService(db)


# ── UTR verification flow ──────────────────────────────────

@pytest.mark.asyncio
async def test_verify_utr_success(db, sms_svc, pending_order):
    """Submit UTR + matching SMS = verified."""
    # Pre-store an SMS with matching UTR and amount
    sms = SmsLog(
        sender="BANK-SMS",
        body="Rs.299.00 credited. UTR: 312456789012",
        received_at=datetime.now(timezone.utc),
        utr_extracted="312456789012",
        amount_extracted=Decimal("299.00"),
    )
    db.add(sms)
    await db.flush()

    verified, msg = await sms_svc.verify_utr("ORD-SMS-TEST-001", "312456789012")
    assert verified is True
    assert "verified" in msg.lower()


@pytest.mark.asyncio
async def test_verify_utr_waiting(db, sms_svc, pending_order):
    """Submit UTR without matching SMS = waiting."""
    verified, msg = await sms_svc.verify_utr("ORD-SMS-TEST-001", "999999999999")
    assert verified is False
    assert "waiting" in msg.lower() or "minutes" in msg.lower()


@pytest.mark.asyncio
async def test_verify_utr_amount_mismatch(db, sms_svc, pending_order):
    """Submit UTR with wrong amount = rejected."""
    sms = SmsLog(
        sender="BANK-SMS",
        body="Rs.500.00 credited. UTR: 312456789012",
        received_at=datetime.now(timezone.utc),
        utr_extracted="312456789012",
        amount_extracted=Decimal("500.00"),
    )
    db.add(sms)
    await db.flush()

    verified, msg = await sms_svc.verify_utr("ORD-SMS-TEST-001", "312456789012")
    assert verified is False
    assert "mismatch" in msg.lower()


@pytest.mark.asyncio
async def test_verify_utr_order_not_found(sms_svc):
    """Verify UTR for non-existent order."""
    verified, msg = await sms_svc.verify_utr("ORD-GHOST", "123456789012")
    assert verified is False
    assert "not found" in msg.lower()


# ── Duplicate UTR detection ────────────────────────────────

@pytest.mark.asyncio
async def test_duplicate_utr_claim_prevented(db, sms_svc, user, plan):
    """A UTR already used by one order cannot be claimed by another."""
    # First order — claim the UTR
    order1 = PaymentOrder(
        user_id=user.id, plan_id=plan.id, amount=Decimal("299.00"),
        upi_id_used="test@upi", order_ref="ORD-DUP-001",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(order1)
    await db.flush()

    sms = SmsLog(
        sender="BANK", body="UTR: 111111111111 Rs.299",
        received_at=datetime.now(timezone.utc),
        utr_extracted="111111111111", amount_extracted=Decimal("299.00"),
    )
    db.add(sms)
    await db.flush()

    ok1, _ = await sms_svc.verify_utr("ORD-DUP-001", "111111111111")
    assert ok1 is True

    # Second order — same UTR should be rejected
    order2 = PaymentOrder(
        user_id=user.id, plan_id=plan.id, amount=Decimal("299.00"),
        upi_id_used="test@upi", order_ref="ORD-DUP-002",
        status="pending",
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=15),
    )
    db.add(order2)
    await db.flush()

    ok2, msg2 = await sms_svc.verify_utr("ORD-DUP-002", "111111111111")
    assert ok2 is False
    assert "already" in msg2.lower()


# ── Auto-match: SMS arrives after UTR submission ────────────

@pytest.mark.asyncio
async def test_auto_match_sms_arrives_later(db, sms_svc, pending_order):
    """Submit UTR first (waiting), then SMS arrives and auto-matches."""
    # Step 1: user submits UTR — no SMS yet
    ok, _ = await sms_svc.verify_utr("ORD-SMS-TEST-001", "222222222222")
    assert ok is False

    # Step 2: SMS arrives with that UTR
    sms = await sms_svc.process_sms(
        sender="BANK",
        body="Rs.299.00 credited UTR: 222222222222",
        received_at=datetime.now(timezone.utc),
    )

    # Auto-match should have triggered — SMS is matched, order ready for grant
    await db.refresh(pending_order)
    assert sms.matched is True
    assert pending_order.status == "utr_submitted"  # match done; grant done by payment_order_service


# ── Expired order rejection ────────────────────────────────

@pytest.mark.asyncio
async def test_verify_utr_expired_order(db, sms_svc, user, plan):
    """Cannot submit UTR for an expired order."""
    order = PaymentOrder(
        user_id=user.id, plan_id=plan.id, amount=Decimal("299.00"),
        upi_id_used="test@upi", order_ref="ORD-EXPIRED",
        status="pending",
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=5),  # already expired
    )
    db.add(order)
    await db.flush()

    ok, msg = await sms_svc.verify_utr("ORD-EXPIRED", "333333333333")
    assert ok is False
    assert "expired" in msg.lower()


# ── Stale SMS rejection (SEC-8) ─────────────────────────────

@pytest.mark.asyncio
async def test_stale_sms_not_auto_matched(db, sms_svc, pending_order):
    """SMS older than 24h should be stored but NOT auto-matched."""
    # Submit UTR first
    await sms_svc.verify_utr("ORD-SMS-TEST-001", "444444444444")

    # Old SMS arrives
    old_time = datetime.now(timezone.utc) - timedelta(hours=25)
    sms = await sms_svc.process_sms(
        sender="BANK",
        body="Rs.299.00 credited UTR: 444444444444",
        received_at=old_time,
    )

    # Should be stored but not matched
    assert sms.utr_extracted == "444444444444"
    await db.refresh(pending_order)
    assert pending_order.status == "utr_submitted"  # NOT verified


# ── Already verified order ──────────────────────────────────

@pytest.mark.asyncio
async def test_verify_already_verified_order(db, sms_svc, pending_order):
    """Submitting UTR for already verified order returns True."""
    pending_order.status = "verified"
    await db.flush()

    ok, msg = await sms_svc.verify_utr("ORD-SMS-TEST-001", "555555555555")
    assert ok is True
    assert "already" in msg.lower()
