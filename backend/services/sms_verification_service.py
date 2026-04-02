"""
SMS Verification Service — parses forwarded bank SMS, extracts UTR & amount,
and matches against pending payment orders.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple


def _utcnow() -> datetime:
    """Return timezone-aware UTC now."""
    return datetime.now(timezone.utc)

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.sms_log import SmsLog
from backend.models.payment_order import PaymentOrder

logger = logging.getLogger(__name__)

# Maximum age of an SMS to be accepted for matching (prevents old SMS reuse)
SMS_MAX_AGE_HOURS = 24
# Amount tolerance for matching (₹0.01 for rounding only)
AMOUNT_TOLERANCE = 0.01

# ── UTR / Reference extraction patterns ────────────────────────
# UPI transaction IDs are typically 12-digit numbers
# Bank reference numbers vary: UPI ref, IMPS ref, NEFT ref etc.
UTR_PATTERNS = [
    # UPI: 12-digit transaction reference
    r'\b(\d{12})\b',
    # UTR with label: "UTR: 123456789012" or "Ref No: 123456789012"
    r'(?:UTR|UPI\s*Ref|Ref\.?\s*(?:No|Number|ID|#)?)\s*[:\-]?\s*(\d{12,16})',
    # IMPS reference (usually starts with specific digits)
    r'(?:IMPS)\s*[:\-]?\s*(\d{12,16})',
    # Generic long number that looks like a transaction ID
    r'\b(\d{16})\b',
]

AMOUNT_PATTERNS = [
    # Rs. 100.00 or Rs 100 or INR 100.00
    r'(?:Rs\.?|INR|₹)\s*([0-9,]+\.?\d{0,2})',
    # "credited with 100" or "debited for 100"
    r'(?:credited|debited|received|paid)\s*(?:with|for|of)?\s*(?:Rs\.?|INR|₹)?\s*([0-9,]+\.?\d{0,2})',
    # Amount at end: "of 100.00"
    r'(?:of|for|amount)\s*(?:Rs\.?|INR|₹)?\s*([0-9,]+\.?\d{0,2})',
]


def extract_utr(sms_body: str) -> Optional[str]:
    """Extract UTR / UPI reference number from SMS body."""
    # Try labeled patterns first (more specific)
    for pattern in UTR_PATTERNS[1:]:
        match = re.search(pattern, sms_body, re.IGNORECASE)
        if match:
            return match.group(1)
    # Fall back to generic 12-digit (check it's not a phone number or amount)
    match = re.search(UTR_PATTERNS[0], sms_body)
    if match:
        candidate = match.group(1)
        # Exclude phone numbers (start with 91, 7, 8, 9 for Indian numbers)
        # and amounts (usually have decimal context)
        if not re.search(r'(?:call|mobile|phone|contact)\s*[:\-]?\s*' + re.escape(candidate), sms_body, re.IGNORECASE):
            return candidate
    return None


def extract_amount(sms_body: str) -> Optional[float]:
    """Extract payment amount from SMS body."""
    for pattern in AMOUNT_PATTERNS:
        match = re.search(pattern, sms_body, re.IGNORECASE)
        if match:
            amount_str = match.group(1).replace(",", "")
            try:
                return float(amount_str)
            except ValueError:
                continue
    return None


class SmsVerificationService:
    """Processes forwarded SMS and matches UTRs against pending orders."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def process_sms(
        self,
        sender: str,
        body: str,
        received_at: Optional[datetime] = None,
        source_chat_id: Optional[int] = None,
    ) -> SmsLog:
        """
        Parse incoming SMS, extract UTR and amount, store in DB,
        and attempt auto-matching against pending orders.
        """
        if received_at is None:
            received_at = _utcnow()

        # SEC-8: Reject SMS that are too old to prevent replay attacks
        age = _utcnow() - (received_at if received_at.tzinfo else received_at.replace(tzinfo=timezone.utc))
        if age > timedelta(hours=SMS_MAX_AGE_HOURS):
            logger.warning("Rejected stale SMS (age=%s hours): sender=%s", age.total_seconds() / 3600, sender)
            # Still store for audit, but don't auto-match
            utr = extract_utr(body)
            amount = extract_amount(body)
            sms = SmsLog(
                sender=sender, body=body, received_at=received_at,
                utr_extracted=utr, amount_extracted=amount,
                source_chat_id=source_chat_id,
            )
            self.db.add(sms)
            await self.db.flush()
            return sms

        utr = extract_utr(body)
        amount = extract_amount(body)

        sms = SmsLog(
            sender=sender,
            body=body,
            received_at=received_at,
            utr_extracted=utr,
            amount_extracted=amount,
            source_chat_id=source_chat_id,
        )
        self.db.add(sms)
        await self.db.flush()

        logger.info("SMS processed: sender=%s utr=%s amount=%s", sender, utr, amount)

        # Auto-match: if UTR was extracted, try matching against submitted UTRs
        if utr:
            await self._try_auto_match(sms)

        return sms

    async def verify_utr(self, order_ref: str, utr_submitted: str) -> Tuple[bool, str]:
        """
        Called when user submits a UTR for a payment order.
        1. Records the UTR on the order.
        2. Checks if we have an SMS with that UTR.
        3. If found, verifies amount matches.
        """
        # Find the order
        result = await self.db.execute(
            select(PaymentOrder).where(PaymentOrder.order_ref == order_ref)
        )
        order = result.scalar_one_or_none()
        if not order:
            return False, "Order not found"

        if order.status == "verified":
            return True, "Already verified"

        if order.status not in ("pending", "utr_submitted"):
            return False, f"Order is in {order.status} state"

        # Check if expired
        expires_at = order.expires_at
        if expires_at is not None:
            _exp = expires_at if expires_at.tzinfo else expires_at.replace(tzinfo=timezone.utc)
            if _utcnow() > _exp:
                order.status = "expired"
                await self.db.flush()
                return False, "Order has expired"

        # Check if this UTR is already claimed by another order
        existing = await self.db.execute(
            select(PaymentOrder).where(
                PaymentOrder.utr_submitted == utr_submitted.strip(),
                PaymentOrder.order_ref != order_ref,
                PaymentOrder.status.in_(["utr_submitted", "verified"]),
            )
        )
        if existing.scalar_one_or_none():
            return False, "This UTR has already been used for another payment."

        # Atomic UTR claim: UPDATE only if order is still in eligible state
        claim_result = await self.db.execute(
            update(PaymentOrder)
            .where(
                PaymentOrder.order_ref == order_ref,
                PaymentOrder.status.in_(["pending", "utr_submitted"]),
            )
            .values(utr_submitted=utr_submitted.strip(), status="utr_submitted")
        )
        if claim_result.rowcount == 0:
            return False, "Order is no longer eligible for UTR submission."
        await self.db.flush()

        # Refresh the order object so _match_utr_against_sms sees the new UTR
        await self.db.refresh(order)

        # Look for matching SMS
        matched, msg = await self._match_utr_against_sms(order)
        return matched, msg

    async def _match_utr_against_sms(self, order: PaymentOrder) -> Tuple[bool, str]:
        """Check SMS logs for a matching UTR + amount."""
        result = await self.db.execute(
            select(SmsLog).where(
                SmsLog.utr_extracted == order.utr_submitted,
                SmsLog.matched == False,  # noqa: E712
            )
        )
        sms = result.scalar_one_or_none()

        if not sms:
            # UTR not found yet — SMS may arrive later
            logger.info("UTR %s not found in SMS logs yet (order=%s)", order.utr_submitted, order.order_ref)
            return False, "UTR submitted. Waiting for payment confirmation. This may take a few minutes."

        # Verify amount matches (tight tolerance for rounding only)
        if sms.amount_extracted is not None:
            if abs(float(sms.amount_extracted) - float(order.amount)) > AMOUNT_TOLERANCE:
                logger.warning(
                    "Amount mismatch: SMS=%.2f, Order=%.2f for UTR=%s",
                    sms.amount_extracted, order.amount, order.utr_submitted,
                )
                return False, f"Amount mismatch. Expected ₹{order.amount:.2f}, SMS shows ₹{sms.amount_extracted:.2f}."

        # Match is good — mark SMS as matched; _grant_access will set order.status='verified'
        sms.matched = True
        sms.matched_order_id = order.id
        await self.db.flush()

        logger.info("Payment matched: order=%s utr=%s amount=%.2f", order.order_ref, order.utr_submitted, order.amount)
        return True, "Payment verified successfully!"

    async def _try_auto_match(self, sms: SmsLog) -> None:
        """
        When a new SMS arrives with UTR, check if any order has submitted that UTR.
        If so, auto-verify.
        """
        if not sms.utr_extracted:
            return

        result = await self.db.execute(
            select(PaymentOrder).where(
                PaymentOrder.utr_submitted == sms.utr_extracted,
                PaymentOrder.status == "utr_submitted",
            )
        )
        order = result.scalar_one_or_none()
        if not order:
            return

        # Verify amount
        if sms.amount_extracted is not None and abs(float(sms.amount_extracted) - float(order.amount)) > AMOUNT_TOLERANCE:
            logger.warning("Auto-match: amount mismatch for UTR %s", sms.utr_extracted)
            return

        # Mark SMS as matched; _grant_access will set order.status='verified'
        sms.matched = True
        sms.matched_order_id = order.id
        await self.db.flush()
        logger.info("Auto-matched: order=%s utr=%s", order.order_ref, sms.utr_extracted)

    async def get_recent_sms(self, limit: int = 50) -> List[SmsLog]:
        result = await self.db.execute(
            select(SmsLog).order_by(SmsLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())

    async def get_unmatched_sms(self, limit: int = 50) -> List[SmsLog]:
        result = await self.db.execute(
            select(SmsLog).where(
                SmsLog.matched == False,  # noqa: E712
                SmsLog.utr_extracted.isnot(None),
            ).order_by(SmsLog.created_at.desc()).limit(limit)
        )
        return list(result.scalars().all())
