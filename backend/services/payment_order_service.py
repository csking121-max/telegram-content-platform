"""
Payment Order Service — orchestrates the full UPI payment flow:
  1. Create order → generate QR
  2. User submits UTR
  3. Verify UTR against SMS logs
  4. Grant membership + credits on success
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.engines.credit_engine import CreditEngine
from backend.engines.membership_engine import MembershipEngine
from backend.models.credit_package import CreditPackage
from backend.models.membership_plan import MembershipPlan
from backend.models.payment_order import PaymentOrder
from backend.models.user import User
from backend.schemas.payment_order import QrCodeResponse, UtrVerifyResponse
from backend.services.activity_logger import ActivityLogger
from backend.services.sms_verification_service import SmsVerificationService
from backend.services.upi_service import UpiService, build_upi_link, generate_upi_qr_data_url

logger = logging.getLogger(__name__)

ORDER_EXPIRY_MINUTES = 60


def _utcnow() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)


class PaymentOrderService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.upi_svc = UpiService(db)
        self.sms_svc = SmsVerificationService(db)
        self.credit_engine = CreditEngine(db)
        self.membership_engine = MembershipEngine(db)
        self.activity = ActivityLogger(db)

    # ── Step 1: Create order + QR ────────────────────────

    async def create_order(self, user_id: int, plan_id: int) -> QrCodeResponse:
        """
        Create a payment order for the given plan and return QR code.
        """
        # Get plan
        plan = await self._get_plan(plan_id)
        if not plan:
            raise ValueError("Membership plan not found")
        if not plan.is_active:
            raise ValueError("Membership plan is not active")
        if plan.price_inr <= 0:
            raise ValueError("Plan has no price set")

        # Prevent duplicate pending orders for same user+plan
        existing = await self.db.execute(
            select(PaymentOrder).where(
                PaymentOrder.user_id == user_id,
                PaymentOrder.plan_id == plan_id,
                PaymentOrder.status == "pending",
                PaymentOrder.expires_at > _utcnow(),
            )
        )
        if existing.scalar_one_or_none():
            raise ValueError("You already have a pending order for this plan. Please complete or wait for it to expire.")

        # Get active UPI
        upi = await self.upi_svc.get_active()
        if not upi:
            raise ValueError("No active UPI ID configured. Contact admin.")

        # Generate unique order reference
        order_ref = f"ORD-{secrets.token_hex(6).upper()}"
        expires_at = _utcnow() + timedelta(minutes=ORDER_EXPIRY_MINUTES)

        # Create order
        order = PaymentOrder(
            user_id=user_id,
            plan_id=plan_id,
            amount=float(plan.price_inr),
            upi_id_used=upi.upi_id,
            order_ref=order_ref,
            status="pending",
            expires_at=expires_at,
        )
        self.db.add(order)
        await self.db.flush()

        # Build UPI link and QR
        upi_link = build_upi_link(
            upi_id=upi.upi_id,
            payee_name=upi.payee_name,
            amount=float(plan.price_inr),
            note=f"Payment for {plan.display_name}",
            txn_ref=order_ref,
        )
        qr_data_url = generate_upi_qr_data_url(upi_link)

        await self.activity.log(
            user_id=user_id,
            action="payment_order_created",
            payload={"order_ref": order_ref, "plan": plan.name, "amount": float(plan.price_inr)},
        )

        logger.info("Payment order created: ref=%s plan=%s amount=%.2f", order_ref, plan.name, plan.price_inr)

        return QrCodeResponse(
            order_ref=order_ref,
            amount=float(plan.price_inr),
            upi_id=upi.upi_id,
            payee_name=upi.payee_name,
            upi_link=upi_link,
            qr_data_url=qr_data_url,
            plan_name=plan.display_name,
            expires_at=expires_at,
        )

    # ── Step 2: User submits UTR ─────────────────────────

    async def submit_utr(self, order_ref: str, utr: str, user_id: int) -> UtrVerifyResponse:
        """
        User submits UTR. Try to verify against SMS logs.
        If verified, grant access.
        """
        verified, message = await self.sms_svc.verify_utr(order_ref, utr)

        if verified:
            # Grant access!
            await self._grant_access(order_ref, user_id)
            return UtrVerifyResponse(
                order_ref=order_ref,
                status="verified",
                message="✅ Payment verified! Your access has been granted.",
            )

        # Check if it's a "waiting" scenario vs actual failure
        order = await self._get_order(order_ref)
        if order and order.status == "utr_submitted":
            return UtrVerifyResponse(
                order_ref=order_ref,
                status="pending_verification",
                message=message,
            )

        return UtrVerifyResponse(
            order_ref=order_ref,
            status="failed",
            message=message,
        )

    # ── Step 3: Re-check pending orders (called by worker) ──

    async def recheck_pending_orders(self) -> tuple[int, list[int]]:
        """
        Scan orders in 'utr_submitted' state and re-try matching.
        Returns (count_of_verified, list_of_verified_user_ids).
        """
        result = await self.db.execute(
            select(PaymentOrder).where(
                PaymentOrder.status == "utr_submitted",
            )
        )
        orders = list(result.scalars().all())
        now = _utcnow()
        # Filter expired in Python to avoid naive/aware mismatch in SQLite
        orders = [
            o for o in orders
            if o.expires_at is None or (
                o.expires_at if o.expires_at.tzinfo else o.expires_at.replace(tzinfo=timezone.utc)
            ) > now
        ]
        verified_count = 0
        verified_user_ids: list[int] = []

        for order in orders:
            matched, _ = await self.sms_svc._match_utr_against_sms(order)
            if matched:
                await self._grant_access(order.order_ref, order.user_id)
                verified_count += 1
                verified_user_ids.append(order.user_id)

        return verified_count, verified_user_ids

    # ── Grant access after verification ──────────────────

    async def _grant_access(self, order_ref: str, user_id: int) -> None:
        """Grant membership + optional credits (for plans) or credits (for credit packages)."""
        order = await self._get_order(order_ref)
        if not order:
            return

        # Guard: prevent double-grant if order already verified
        if order.status == "verified":
            logger.debug("Order %s already verified — skipping grant", order_ref)
            return

        # ── Credit package order (plan_id == 0) ─────────────
        if order.plan_id == 0:
            # Custom-amount credit order (no fixed package)
            custom_credits = getattr(order, "custom_credits", None)
            if custom_credits:
                await self.credit_engine.add(
                    user_id=user_id,
                    amount=custom_credits,
                    reason=f"custom_credit_purchase:{order_ref}",
                )
                await self.activity.log(
                    user_id=user_id,
                    action="custom_credits_purchased",
                    payload={
                        "order_ref": order_ref,
                        "credits": custom_credits,
                        "amount": float(order.amount),
                    },
                )
                logger.info(
                    "Custom credits granted: user=%d credits=%d amount=%.2f",
                    user_id, custom_credits, order.amount,
                )
            else:
                # Fixed credit package
                pkg = await self._get_credit_package(order)
                if not pkg:
                    logger.warning("Credit package not found for order %s", order_ref)
                    return

                await self.credit_engine.add(
                    user_id=user_id,
                    amount=pkg.credits,
                    reason=f"credit_purchase:{pkg.name}:{order_ref}",
                )
                await self.activity.log(
                    user_id=user_id,
                    action="credit_package_purchased",
                    payload={
                        "order_ref": order_ref,
                        "package": pkg.name,
                        "credits": pkg.credits,
                        "amount": float(order.amount),
                    },
                )
                logger.info(
                    "Credit package granted: user=%d pkg=%s credits=%d",
                    user_id, pkg.name, pkg.credits,
                )
            # Mark order as verified after successful credit grant
            order.status = "verified"
            order.verified_at = _utcnow()
            await self.db.flush()
            return

        # ── Membership plan order ────────────────────────────
        plan = await self._get_plan(order.plan_id)
        if not plan:
            return

        # Grant membership
        expiry = _utcnow() + timedelta(days=plan.duration_days, hours=getattr(plan, 'duration_hours', 0))
        await self.membership_engine.grant(
            user_id=user_id,
            membership_type=plan.access_type,
            expiry_at=expiry,
        )

        # Grant bonus credits if any
        if plan.credit_reward > 0:
            await self.credit_engine.add(
                user_id=user_id,
                amount=plan.credit_reward,
                reason=f"plan_purchase:{plan.name}:{order_ref}",
            )

        await self.activity.log(
            user_id=user_id,
            action="payment_verified",
            payload={
                "order_ref": order_ref,
                "plan": plan.name,
                "amount": float(order.amount),
                "membership_type": plan.access_type,
                "duration_days": plan.duration_days,
                "credit_reward": plan.credit_reward,
            },
        )

        # Mark order as verified after successful membership grant
        order.status = "verified"
        order.verified_at = _utcnow()
        await self.db.flush()

        logger.info(
            "Access granted: user=%d plan=%s membership=%s for %d days",
            user_id, plan.name, plan.access_type, plan.duration_days,
        )

    # ── Lookups ──────────────────────────────────────────

    async def _get_plan(self, plan_id: int) -> Optional[MembershipPlan]:
        result = await self.db.execute(
            select(MembershipPlan).where(MembershipPlan.id == plan_id)
        )
        return result.scalar_one_or_none()

    async def _get_credit_package(self, order: PaymentOrder) -> Optional[CreditPackage]:
        """Resolve the credit package for a credit-package order.
        Uses order.package_id if set, otherwise falls back to amount-based lookup."""
        if getattr(order, "package_id", None):
            result = await self.db.execute(
                select(CreditPackage).where(CreditPackage.id == order.package_id)
            )
            pkg = result.scalar_one_or_none()
            if pkg:
                return pkg

        # Fallback: match by exact price (for legacy orders without package_id)
        result = await self.db.execute(
            select(CreditPackage).where(
                CreditPackage.price_inr == order.amount,
                CreditPackage.is_active == True,  # noqa: E712
            )
        )
        return result.scalars().first()

    async def _get_order(self, order_ref: str) -> Optional[PaymentOrder]:
        result = await self.db.execute(
            select(PaymentOrder).where(PaymentOrder.order_ref == order_ref)
        )
        return result.scalar_one_or_none()

    async def get_user_orders(self, user_id: int, limit: int = 20) -> List[PaymentOrder]:
        result = await self.db.execute(
            select(PaymentOrder)
            .where(PaymentOrder.user_id == user_id)
            .order_by(PaymentOrder.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_order_by_ref(self, order_ref: str) -> Optional[PaymentOrder]:
        return await self._get_order(order_ref)

    async def get_active_plans(self) -> List[MembershipPlan]:
        result = await self.db.execute(
            select(MembershipPlan)
            .where(MembershipPlan.is_active == True)  # noqa: E712
            .order_by(MembershipPlan.sort_order, MembershipPlan.price_inr)
        )
        return list(result.scalars().all())

    async def expire_stale_orders(self) -> int:
        """Mark expired pending orders. Called periodically by worker."""
        result = await self.db.execute(
            select(PaymentOrder).where(
                PaymentOrder.status.in_(["pending", "utr_submitted"]),
                PaymentOrder.expires_at < _utcnow(),
            )
        )
        orders = list(result.scalars().all())
        for order in orders:
            order.status = "expired"
        await self.db.flush()
        return len(orders)

    async def retry_order(self, order_ref: str, user_id: int) -> Optional[PaymentOrder]:
        """Reset a failed/expired order back to 'pending' with a fresh expiry.

        Returns the updated order, or None if retry is not allowed.
        """
        order = await self._get_order(order_ref)
        if not order:
            return None

        # Only allow retry for failed or expired orders
        if order.status not in ("failed", "expired"):
            return None

        # Must belong to the requesting user
        if order.user_id != user_id:
            return None

        # Check that the plan is still active
        plan = await self._get_plan(order.plan_id)
        if not plan or not plan.is_active:
            return None

        # Reset order state
        order.status = "pending"
        order.utr_submitted = None
        order.verified_at = None
        order.expires_at = _utcnow() + timedelta(minutes=ORDER_EXPIRY_MINUTES)
        await self.db.flush()

        await self.activity.log(
            user_id=user_id,
            action="payment_order_retried",
            payload={"order_ref": order_ref},
        )
        logger.info("Payment order retried: ref=%s", order_ref)
        return order
