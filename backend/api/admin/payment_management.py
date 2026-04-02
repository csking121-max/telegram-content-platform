"""Admin endpoints for UTR logs and payment orders management."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func

from backend.dependencies import get_db
from backend.schemas.sms_log import SmsLogRead
from backend.schemas.payment_order import PaymentOrderRead
from backend.models.sms_log import SmsLog
from backend.models.payment_order import PaymentOrder
from backend.services.sms_verification_service import SmsVerificationService
from backend.services.payment_order_service import PaymentOrderService
from backend.services.platform_settings_service import PlatformSettingsService

router = APIRouter()


# ── UTR Logs ─────────────────────────────────────────────

@router.get("/sms", response_model=list[SmsLogRead])
async def list_sms_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    unmatched_only: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """View UTR logs filtered by configured UTR verification group."""
    # Get the configured UTR group chat_id for filtering
    settings_svc = PlatformSettingsService(db)
    utr_group_id_str = await settings_svc.get("utr_group_chat_id", "")

    utr_group_id: int | None = None
    if utr_group_id_str:
        try:
            utr_group_id = int(utr_group_id_str.strip())
        except ValueError:
            pass

    # Build query with optional group filter
    query = select(SmsLog).order_by(SmsLog.created_at.desc())

    if utr_group_id is not None:
        query = query.where(SmsLog.source_chat_id == utr_group_id)

    if unmatched_only:
        query = query.where(
            SmsLog.matched == False,  # noqa: E712
            SmsLog.utr_extracted.isnot(None),
        )

    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    return list(result.scalars().all())


# ── Payment Orders ───────────────────────────────────────

@router.get("/orders", response_model=list[PaymentOrderRead])
async def list_payment_orders(
    status: str = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    """List payment orders with optional status filter."""
    query = select(PaymentOrder).order_by(PaymentOrder.created_at.desc()).offset(skip).limit(limit)
    if status:
        query = query.where(PaymentOrder.status == status)
    result = await db.execute(query)
    return result.scalars().all()


@router.get("/orders/{order_ref}", response_model=PaymentOrderRead)
async def get_payment_order(order_ref: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(PaymentOrder).where(PaymentOrder.order_ref == order_ref))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    return order


@router.post("/orders/{order_ref}/verify")
async def admin_verify_order(order_ref: str, db: AsyncSession = Depends(get_db)):
    """Admin manually verifies a payment order (force-approve)."""
    result = await db.execute(select(PaymentOrder).where(PaymentOrder.order_ref == order_ref))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status == "verified":
        return {"detail": "Already verified"}

    from datetime import datetime, timezone
    order.status = "verified"
    order.verified_at = datetime.now(timezone.utc)
    await db.flush()

    # Grant access
    svc = PaymentOrderService(db)
    await svc._grant_access(order.order_ref, order.user_id)
    await db.commit()

    return {"detail": "Order verified and access granted"}


@router.post("/orders/{order_ref}/reject")
async def admin_reject_order(order_ref: str, db: AsyncSession = Depends(get_db)):
    """Admin manually rejects a payment order."""
    result = await db.execute(select(PaymentOrder).where(PaymentOrder.order_ref == order_ref))
    order = result.scalar_one_or_none()
    if not order:
        raise HTTPException(404, "Order not found")

    order.status = "failed"
    await db.flush()
    return {"detail": "Order rejected"}


@router.post("/orders/{order_ref}/retry")
async def admin_retry_order(order_ref: str, db: AsyncSession = Depends(get_db)):
    """Admin resets a failed/expired order back to pending for user retry."""
    svc = PaymentOrderService(db)
    order = await svc.get_order_by_ref(order_ref)
    if not order:
        raise HTTPException(404, "Order not found")
    if order.status not in ("failed", "expired"):
        raise HTTPException(400, f"Cannot retry order in '{order.status}' state")

    retried = await svc.retry_order(order_ref, order.user_id)
    if not retried:
        raise HTTPException(400, "Retry failed — plan may be inactive")
    await db.commit()
    return {"detail": "Order reset to pending", "order_ref": order_ref}


@router.get("/stats")
async def payment_stats(db: AsyncSession = Depends(get_db)):
    """Payment statistics for admin dashboard."""
    async def _count(status):
        r = await db.execute(
            select(func.count(PaymentOrder.id)).where(PaymentOrder.status == status)
        )
        return r.scalar() or 0

    total_revenue = await db.execute(
        select(func.coalesce(func.sum(PaymentOrder.amount), 0)).where(
            PaymentOrder.status == "verified"
        )
    )

    total = await db.execute(select(func.count(PaymentOrder.id)))

    return {
        "total_orders": total.scalar() or 0,
        "pending": await _count("pending"),
        "utr_submitted": await _count("utr_submitted"),
        "verified": await _count("verified"),
        "failed": await _count("failed"),
        "expired": await _count("expired"),
        "total_revenue": float(total_revenue.scalar()),
    }
