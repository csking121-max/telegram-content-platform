"""
Tests for PaymentService — create, verify, credit integration.
"""
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.credit import Credit
from backend.models.payment import Payment
from backend.models.user import User
from backend.schemas.payment import PaymentCreate, PaymentVerify
from backend.services.payment_service import PaymentService


@pytest_asyncio.fixture
async def user(db: AsyncSession) -> User:
    u = User(telegram_id=900001, username="payuser")
    db.add(u)
    await db.flush()
    # Ensure credit account exists
    db.add(Credit(user_id=u.id, balance=0))
    await db.flush()
    return u


@pytest_asyncio.fixture
async def svc(db: AsyncSession) -> PaymentService:
    return PaymentService(db)


# ── create_payment ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_payment(svc, user):
    data = PaymentCreate(
        user_id=user.id, amount=100.0, method="card", reference="REF-001",
    )
    payment = await svc.create_payment(data)
    assert payment.id is not None
    assert payment.status == "pending"
    assert payment.reference == "REF-001"


# ── verify_payment ──────────────────────────────────────────────

@pytest.mark.asyncio
async def test_verify_completed_credits_user(svc, db, user):
    data = PaymentCreate(
        user_id=user.id, amount=50.0, method="card", reference="REF-002",
    )
    await svc.create_payment(data)

    verify = PaymentVerify(reference="REF-002", status="completed")
    payment = await svc.verify_payment(verify)

    assert payment is not None
    assert payment.status == "completed"
    assert payment.completed_at is not None

    # Check credits added
    result = await db.execute(select(Credit).where(Credit.user_id == user.id))
    credit = result.scalar_one()
    assert credit.balance == 50  # 1:1 conversion


@pytest.mark.asyncio
async def test_verify_nonexistent_reference(svc):
    verify = PaymentVerify(reference="GHOST-REF", status="completed")
    result = await svc.verify_payment(verify)
    assert result is None


@pytest.mark.asyncio
async def test_verify_already_processed(svc, user):
    data = PaymentCreate(
        user_id=user.id, amount=25.0, method="card", reference="REF-003",
    )
    await svc.create_payment(data)

    verify = PaymentVerify(reference="REF-003", status="completed")
    await svc.verify_payment(verify)

    # Second verification should not re-process
    again = await svc.verify_payment(verify)
    assert again.status == "completed"


# ── get_by_reference ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_by_reference(svc, user):
    data = PaymentCreate(
        user_id=user.id, amount=10.0, method="bank", reference="REF-004",
    )
    await svc.create_payment(data)
    found = await svc.get_by_reference("REF-004")
    assert found is not None
    assert found.amount == 10.0


@pytest.mark.asyncio
async def test_get_user_payments(svc, user):
    for i in range(3):
        data = PaymentCreate(
            user_id=user.id, amount=10.0 * (i + 1),
            method="card", reference=f"REF-MULTI-{i}",
        )
        await svc.create_payment(data)

    payments = await svc.get_user_payments(user.id)
    assert len(payments) == 3