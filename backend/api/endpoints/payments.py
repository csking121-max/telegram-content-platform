"""
Payment verification endpoint.

Receives payment confirmation webhooks from external payment
providers (e.g. Stripe, crypto processors) and credits the user.
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.schemas.payment import PaymentVerify, PaymentRead
from backend.services.payment_service import PaymentService
from backend.services.activity_logger import ActivityLogger
from backend.utils.helpers import format_response
from backend.api.endpoints.internal import verify_internal_key

router = APIRouter()


@router.post("/verify", response_model=PaymentRead)
async def verify_payment(
    body: PaymentVerify,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """
    Verify a payment and credit the user if successful.

    Called by the payment provider webhook or the bot gateway.
    """
    svc = PaymentService(db)
    payment = await svc.verify_payment(body)

    if not payment:
        raise HTTPException(status_code=400, detail="Payment verification failed")

    al = ActivityLogger(db)
    await al.log(
        user_id=payment.user_id,
        action="payment_verified",
        payload={
            "payment_id": payment.id,
            "provider": payment.method,
            "amount": str(payment.amount),
        },
    )

    return payment