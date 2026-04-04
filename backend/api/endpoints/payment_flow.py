"""
Public payment flow endpoints:
  - POST /payments/create-order   → generate QR for a plan
  - POST /payments/submit-utr     → submit UTR after payment
  - GET  /payments/order/{ref}    → check order status
  - GET  /payments/plans          → list active membership plans
  - POST /payments/group-utr      → receive bank SMS text from Telegram group
"""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta, timezone

from backend.dependencies import get_db
from backend.models.payment_order import PaymentOrder
from backend.models.membership_plan import MembershipPlan
from backend.models.user import User
from backend.schemas.payment_order import (
    PaymentOrderCreate,
    PaymentOrderRead,
    QrCodeResponse,
    UtrSubmit,
    UtrVerifyResponse,
)
from backend.schemas.membership_plan import MembershipPlanRead
from backend.services.payment_order_service import PaymentOrderService
from backend.services.platform_settings_service import PlatformSettingsService
from backend.services.sms_verification_service import SmsVerificationService
from backend.services.user_service import UserService
from backend.engines.credit_engine import CreditEngine
from backend.engines.membership_engine import MembershipEngine
from backend.api.endpoints.internal import verify_internal_key

router = APIRouter()


@router.get("/plans", response_model=list[MembershipPlanRead])
async def list_plans(db: AsyncSession = Depends(get_db)):
    """List all active membership plans with pricing."""
    svc = PaymentOrderService(db)
    plans = await svc.get_active_plans()
    return plans


@router.post("/create-order", response_model=QrCodeResponse)
async def create_payment_order(
    body: PaymentOrderCreate,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a payment order for a membership plan.
    Returns UPI QR code data URL for the user to scan and pay.
    """
    # Ensure user exists
    user_svc = UserService(db)
    user = await user_svc.get_by_telegram_id(body.telegram_id)
    if not user:
        raise HTTPException(404, "User not registered. Send /start to the bot first.")

    # Tier guard — block UPI purchase of same-tier or lower-tier plans
    result = await db.execute(
        select(MembershipPlan).where(
            MembershipPlan.id == body.plan_id,
            MembershipPlan.is_active == True,
        )
    )
    plan = result.scalar_one_or_none()
    if plan and plan.tier_level > 0:
        membership_engine = MembershipEngine(db)
        user_max_tier = await membership_engine.get_user_max_tier_level(user.id)
        if user_max_tier > plan.tier_level:
            raise HTTPException(
                400,
                "You already have a higher-tier membership. This plan would be a downgrade.",
            )
        # Same-tier is allowed (renewal / extension)

    svc = PaymentOrderService(db)
    try:
        qr = await svc.create_order(user_id=user.id, plan_id=body.plan_id)
    except ValueError as e:
        raise HTTPException(400, str(e))

    await db.commit()
    return qr


@router.post("/submit-utr", response_model=UtrVerifyResponse)
async def submit_utr(
    body: UtrSubmit,
    db: AsyncSession = Depends(get_db),
):
    """
    User submits UTR number after making UPI payment.
    System verifies against forwarded bank SMS.
    """
    user_svc = UserService(db)
    user = await user_svc.get_by_telegram_id(body.telegram_id)
    if not user:
        raise HTTPException(404, "User not registered.")

    svc = PaymentOrderService(db)
    result = await svc.submit_utr(
        order_ref=body.order_ref,
        utr=body.utr,
        user_id=user.id,
    )
    await db.commit()
    return result


@router.get("/order/{order_ref}", response_model=PaymentOrderRead)
async def get_order_status(
    order_ref: str,
    db: AsyncSession = Depends(get_db),
):
    """Check the status of a payment order."""
    svc = PaymentOrderService(db)
    order = await svc.get_order_by_ref(order_ref)
    if not order:
        raise HTTPException(404, "Order not found")
    return order


# ── Retry failed/expired payment order ───────────────────────

class RetryOrderPayload(BaseModel):
    telegram_id: int
    order_ref: str


@router.post("/retry-order")
async def retry_payment_order(
    body: RetryOrderPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Retry a failed or expired payment order — resets it to 'pending'
    with a fresh expiry so the user can re-submit UTR without creating
    a brand-new order.
    """
    user_svc = UserService(db)
    user = await user_svc.get_by_telegram_id(body.telegram_id)
    if not user:
        raise HTTPException(404, "User not registered.")

    svc = PaymentOrderService(db)
    order = await svc.retry_order(body.order_ref, user.id)
    if not order:
        raise HTTPException(400, "Cannot retry this order. It may not be failed/expired or the plan is no longer active.")

    await db.commit()
    return {
        "ok": True,
        "order_ref": order.order_ref,
        "status": order.status,
        "expires_at": order.expires_at.isoformat(),
        "amount": float(order.amount),
    }


# ── Pending orders for a user ────────────────────────────────

@router.get("/my-pending/{telegram_id}")
async def get_my_pending_orders(
    telegram_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """Return active (pending / utr_submitted) non-expired orders for a user."""
    user_svc = UserService(db)
    user = await user_svc.get_by_telegram_id(telegram_id)
    if not user:
        return []

    now = datetime.now(timezone.utc)
    result = await db.execute(
        select(PaymentOrder)
        .where(
            PaymentOrder.user_id == user.id,
            PaymentOrder.status.in_(["pending", "utr_submitted"]),
        )
        .order_by(PaymentOrder.created_at.desc())
    )
    orders = list(result.scalars().all())

    # Filter expired in Python to avoid naive/aware mismatch in SQLite
    out = []
    for o in orders:
        exp = o.expires_at
        if exp is not None:
            if exp.tzinfo is None:
                exp = exp.replace(tzinfo=timezone.utc)
            if now > exp:
                continue
        out.append({
            "order_ref": o.order_ref,
            "amount": float(o.amount),
            "status": o.status,
            "utr_submitted": o.utr_submitted,
            "expires_at": o.expires_at.isoformat() if o.expires_at else None,
            "created_at": o.created_at.isoformat() if o.created_at else None,
            "custom_credits": o.custom_credits,
            "package_id": o.package_id,
            "plan_id": o.plan_id,
        })
    return out


# ── Telegram Group UTR endpoint ──────────────────────────────

class GroupUtrPayload(BaseModel):
    chat_id: int
    message_text: str
    sender_name: str = ""
    message_id: int = 0


@router.post("/group-utr")
async def receive_group_utr(
    body: GroupUtrPayload,
    db: AsyncSession = Depends(get_db),
):
    """
    Receive bank SMS text forwarded via Telegram group.
    The bot in the UTR verification group sends messages here.
    Extracts UTR and auto-matches against pending payment orders.
    """
    # Verify this is from the authorised UTR group
    settings_svc = PlatformSettingsService(db)
    allowed_chat_id = await settings_svc.get("utr_group_chat_id", "")

    if not allowed_chat_id:
        raise HTTPException(403, "UTR group chat ID not configured")

    # Allow matching (handle both string formats)
    if str(body.chat_id) != allowed_chat_id.strip():
        raise HTTPException(403, "Unauthorized group")

    # Process the message through SMS verification service
    sms_svc = SmsVerificationService(db)
    sms = await sms_svc.process_sms(
        sender=body.sender_name or "TG_GROUP",
        body=body.message_text,
        source_chat_id=body.chat_id,
    )
    await db.flush()

    order_svc = PaymentOrderService(db)

    # Recheck all pending orders (catches orders whose SMS arrived earlier)
    _verified_count, recheck_user_ids = await order_svc.recheck_pending_orders()
    await db.flush()

    # If this specific SMS auto-matched, also grant access
    matched_telegram_id = None
    if sms.matched and sms.matched_order_id:
        result = await db.execute(
            select(PaymentOrder).where(PaymentOrder.id == sms.matched_order_id)
        )
        order = result.scalar_one_or_none()
        if order and order.status in ("pending", "utr_submitted"):
            await order_svc._grant_access(order.order_ref, order.user_id)
            user_result = await db.execute(
                select(User.telegram_id).where(User.id == order.user_id)
            )
            matched_telegram_id = user_result.scalar_one_or_none()

    # Resolve recheck user_ids → telegram_ids for notification
    recheck_telegram_ids: list[int] = []
    if recheck_user_ids:
        tg_result = await db.execute(
            select(User.telegram_id).where(User.id.in_(recheck_user_ids))
        )
        recheck_telegram_ids = [r for r in tg_result.scalars().all() if r]

    await db.commit()

    return {
        "ok": True,
        "utr_extracted": sms.utr_extracted,
        "amount_extracted": sms.amount_extracted,
        "matched_order_id": sms.matched_order_id,
        "matched_telegram_id": matched_telegram_id,
        "recheck_telegram_ids": recheck_telegram_ids,
    }


# ── Buy membership with credits ─────────────────────────────

class CreditPurchasePayload(BaseModel):
    telegram_id: int
    plan_id: int


@router.post("/buy-with-credits")
async def buy_membership_with_credits(
    body: CreditPurchasePayload,
    db: AsyncSession = Depends(get_db),
):
    """Buy a membership plan using credits instead of UPI payment."""
    user_svc = UserService(db)
    user = await user_svc.get_by_telegram_id(body.telegram_id)
    if not user:
        raise HTTPException(404, "User not registered. Send /start to the bot first.")

    result = await db.execute(
        select(MembershipPlan).where(
            MembershipPlan.id == body.plan_id,
            MembershipPlan.is_active == True,
        )
    )
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found or inactive.")

    if plan.credit_price <= 0:
        raise HTTPException(400, "This plan cannot be purchased with credits.")

    # Tier guard — block purchase of lower-tier plans (same-tier = renewal)
    membership_engine = MembershipEngine(db)
    if plan.tier_level > 0:
        user_max_tier = await membership_engine.get_user_max_tier_level(user.id)
        if user_max_tier > plan.tier_level:
            raise HTTPException(
                400,
                "You already have a higher-tier membership. This plan would be a downgrade.",
            )
        # Same-tier is allowed (renewal / extension)

    credit_engine = CreditEngine(db)

    balance = await credit_engine.get_balance(user.id)
    if balance < plan.credit_price:
        raise HTTPException(
            400,
            f"Insufficient credits. Need {plan.credit_price}, have {balance}.",
        )

    await credit_engine.deduct(
        user_id=user.id,
        amount=plan.credit_price,
        reason=f"membership_purchase:{plan.name}",
    )

    expiry = datetime.now(timezone.utc) + timedelta(
        days=plan.duration_days,
        hours=getattr(plan, 'duration_hours', 0),
    )
    membership = await membership_engine.grant(
        user_id=user.id,
        membership_type=plan.access_type,
        expiry_at=expiry,
    )

    # Grant bonus credits if any
    if plan.credit_reward > 0:
        await credit_engine.add(
            user_id=user.id,
            amount=plan.credit_reward,
            reason=f"plan_bonus:{plan.name}",
        )

    await db.commit()

    remaining_balance = await credit_engine.get_balance(user.id)

    return {
        "ok": True,
        "plan_name": plan.display_name or plan.name,
        "membership_type": plan.access_type,
        "expiry_at": membership.expiry_at.isoformat() if membership.expiry_at else None,
        "credits_deducted": plan.credit_price,
        "bonus_credits": plan.credit_reward,
        "remaining_balance": remaining_balance,
    }
