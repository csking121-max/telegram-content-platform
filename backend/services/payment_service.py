"""
Payment Service — pluggable payment processing.

The actual payment provider is abstracted behind this service.
After verification it notifies the CreditEngine.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.engines.credit_engine import CreditEngine
from backend.models.payment import Payment
from backend.schemas.payment import PaymentCreate, PaymentVerify
from backend.services.activity_logger import ActivityLogger

logger = logging.getLogger(__name__)


class PaymentService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.credit_engine = CreditEngine(db)
        self.activity = ActivityLogger(db)

    async def create_payment(self, data: PaymentCreate) -> Payment:
        """Record a new pending payment."""
        payment = Payment(
            user_id=data.user_id,
            amount=data.amount,
            method=data.method,
            reference=data.reference,
            status="pending",
        )
        self.db.add(payment)
        await self.db.flush()
        logger.info("Payment created id=%s ref=%s", payment.id, payment.reference)
        return payment

    async def verify_payment(self, data: PaymentVerify) -> Optional[Payment]:
        """
        Called by payment webhook or admin.
        If status == 'completed', credit the user.
        """
        result = await self.db.execute(
            select(Payment).where(Payment.reference == data.reference)
        )
        payment = result.scalar_one_or_none()
        if payment is None:
            logger.warning("Payment not found for ref=%s", data.reference)
            return None

        if payment.status != "pending":
            logger.warning("Payment ref=%s already processed (status=%s)", data.reference, payment.status)
            return payment

        payment.status = data.status
        if data.status == "completed":
            payment.completed_at = datetime.now(timezone.utc)
            credits_to_add = int(payment.amount)
            if credits_to_add <= 0:
                logger.warning("Invalid payment amount %s for ref=%s", payment.amount, data.reference)
                payment.status = "failed"
                await self.db.flush()
                return payment
            await self.credit_engine.add(
                payment.user_id, credits_to_add, f"payment:{payment.reference}"
            )
            await self.activity.log(
                payment.user_id, "payment_completed", {"ref": payment.reference, "credits": credits_to_add}
            )

        await self.db.flush()
        logger.info("Payment ref=%s → %s", data.reference, data.status)
        return payment

    async def get_by_reference(self, reference: str) -> Optional[Payment]:
        result = await self.db.execute(
            select(Payment).where(Payment.reference == reference)
        )
        return result.scalar_one_or_none()

    async def get_user_payments(self, user_id: int) -> list[Payment]:
        result = await self.db.execute(
            select(Payment).where(Payment.user_id == user_id).order_by(Payment.created_at.desc())
        )
        return list(result.scalars().all())