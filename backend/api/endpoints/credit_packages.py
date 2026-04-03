"""
Public credit packages endpoint — lists available credit packages for purchase.
Also handles credit package purchase flow.
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.engines.credit_engine import CreditEngine
from backend.models.payment_order import PaymentOrder
from backend.services.credit_package_service import CreditPackageService
from backend.services.platform_settings_service import PlatformSettingsService
from backend.services.upi_service import UpiService, build_upi_link, generate_upi_qr_data_url
from backend.services.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("")
async def list_credit_packages(db: AsyncSession = Depends(get_db)):
    """List all active credit packages — shown in bot purchase menu."""
    svc = CreditPackageService(db)
    pkgs = await svc.list_active()
    return [
        {
            "id": p.id,
            "name": p.name,
            "display_name": p.display_name,
            "description": p.description or "",
            "credits": p.credits,
            "price_inr": float(p.price_inr),
        }
        for p in pkgs
    ]


class CreditPurchaseRequest(BaseModel):
    telegram_id: int
    package_id: int


class CustomCreditPurchaseRequest(BaseModel):
    telegram_id: int
    credits_amount: int


@router.post("/buy")
async def buy_credit_package(body: CreditPurchaseRequest, db: AsyncSession = Depends(get_db)):
    """Create a payment order for a credit package purchase."""
    user_svc = UserService(db)
    user = await user_svc.get_by_telegram_id(body.telegram_id)
    if not user:
        raise HTTPException(404, "User not registered")

    pkg_svc = CreditPackageService(db)
    pkg = await pkg_svc.get_by_id(body.package_id)
    if not pkg or not pkg.is_active:
        raise HTTPException(404, "Credit package not found or inactive")

    # Get active UPI config
    upi_svc = UpiService(db)
    upi = await upi_svc.get_active()
    if not upi:
        raise HTTPException(503, "No active UPI configuration")

    settings_svc = PlatformSettingsService(db)
    expiry_minutes = await settings_svc.get_int("payment_expiry_minutes", 60)

    order_ref = f"CRD-{secrets.token_hex(8).upper()}"
    amount = float(pkg.price_inr)

    order = PaymentOrder(
        user_id=user.id,
        plan_id=None,  # NULL means credit package, not membership plan
        package_id=pkg.id,  # link to the credit package purchased
        amount=amount,
        upi_id_used=upi.upi_id,
        order_ref=order_ref,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(minutes=expiry_minutes),
    )
    db.add(order)
    await db.flush()

    # Generate QR
    upi_link = build_upi_link(upi.upi_id, upi.payee_name, amount, order_ref)
    qr_data = generate_upi_qr_data_url(upi_link)

    await db.commit()

    return {
        "order_ref": order_ref,
        "amount": amount,
        "package_name": pkg.display_name,
        "credits": pkg.credits,
        "upi_link": upi_link,
        "qr_url": qr_data,
        "qr_data_url": qr_data,
        "expires_at": order.expires_at.isoformat(),
    }


@router.post("/buy-custom")
async def buy_custom_credits(body: CustomCreditPurchaseRequest, db: AsyncSession = Depends(get_db)):
    """Create a payment order for a custom credits amount."""
    if body.credits_amount <= 0:
        raise HTTPException(400, "credits_amount must be positive")

    user_svc = UserService(db)
    user = await user_svc.get_by_telegram_id(body.telegram_id)
    if not user:
        raise HTTPException(404, "User not registered")

    settings_svc = PlatformSettingsService(db)
    price_per_credit = float(await settings_svc.get("credits_per_inr", "1") or "1")
    min_credits = int(await settings_svc.get("custom_credits_min", "10") or "10")
    max_credits = int(await settings_svc.get("custom_credits_max", "0") or "0")
    expiry_minutes = await settings_svc.get_int("payment_expiry_minutes", 60)

    if body.credits_amount < min_credits:
        raise HTTPException(400, f"Minimum order is {min_credits} credits")
    if max_credits > 0 and body.credits_amount > max_credits:
        raise HTTPException(400, f"Maximum order is {max_credits} credits")

    if price_per_credit <= 0:
        price_per_credit = 1.0
    amount = round(body.credits_amount * price_per_credit, 2)

    upi_svc = UpiService(db)
    upi = await upi_svc.get_active()
    if not upi:
        raise HTTPException(503, "No active UPI configuration")

    order_ref = f"CUS-{secrets.token_hex(8).upper()}"

    from backend.models.payment_order import PaymentOrder as _PO
    order = _PO(
        user_id=user.id,
        plan_id=None,
        package_id=None,
        custom_credits=body.credits_amount,
        amount=amount,
        upi_id_used=upi.upi_id,
        order_ref=order_ref,
        status="pending",
        expires_at=datetime.utcnow() + timedelta(minutes=expiry_minutes),
    )
    db.add(order)
    await db.flush()

    upi_link = build_upi_link(upi.upi_id, upi.payee_name, amount, order_ref)
    qr_data = generate_upi_qr_data_url(upi_link)

    await db.commit()

    return {
        "order_ref": order_ref,
        "amount": amount,
        "credits": body.credits_amount,
        "upi_link": upi_link,
        "qr_data_url": qr_data,
        "expires_at": order.expires_at.isoformat(),
    }
