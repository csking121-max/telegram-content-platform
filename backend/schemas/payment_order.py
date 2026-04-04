"""Pydantic schemas for Payment Order (UPI flow)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


class PaymentOrderCreate(BaseModel):
    """User requests to pay for a plan — triggers QR generation."""
    telegram_id: int
    plan_id: int
    package_id: Optional[int] = None


class UtrSubmit(BaseModel):
    """User submits UTR number after payment."""
    telegram_id: int
    order_ref: str
    utr: str


class PaymentOrderRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    plan_id: Optional[int] = None
    package_id: Optional[int] = None
    amount: float
    upi_id_used: str
    order_ref: str
    status: str
    utr_submitted: Optional[str] = None
    verified_at: Optional[datetime] = None
    expires_at: datetime
    created_at: datetime


class QrCodeResponse(BaseModel):
    """Response after creating a payment order — includes QR data URL."""
    order_ref: str
    amount: float
    upi_id: str
    payee_name: str
    upi_link: str
    qr_data_url: str
    plan_name: str
    expires_at: datetime


class UtrVerifyResponse(BaseModel):
    """Response after UTR submission."""
    order_ref: str
    status: str  # verified | pending_verification | failed
    message: str
