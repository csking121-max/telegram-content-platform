"""
HMAC webhook validation.

Each bot has its own webhook_secret.  The gateway signs the JSON body
with HMAC-SHA256 and passes the signature in X-Signature header.
"""
from __future__ import annotations

import hashlib
import hmac
import logging

from fastapi import HTTPException, Request

logger = logging.getLogger(__name__)


def validate_hmac(secret: str, body: bytes, signature: str) -> bool:
    """Compute HMAC-SHA256 of body and compare with provided hex signature."""
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


async def verify_webhook_signature(request: Request, secret: str) -> bytes:
    """
    FastAPI helper — reads body, validates signature from X-Signature header.
    Returns raw body bytes on success; raises 403 on failure.
    """
    body = await request.body()
    signature = request.headers.get("X-Signature", "")
    if not signature or not validate_hmac(secret, body, signature):
        logger.warning("Invalid HMAC signature from %s", request.client.host if request.client else "unknown")
        raise HTTPException(status_code=403, detail="Invalid webhook signature")
    return body