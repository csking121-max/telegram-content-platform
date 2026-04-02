"""Secure token generation utilities."""
from __future__ import annotations

import secrets
import string


def generate_token(length: int = 32) -> str:
    """URL-safe random token (base64)."""
    return secrets.token_urlsafe(length)


def generate_invite_code(length: int = 8) -> str:
    """Short alphanumeric invite code for referrals."""
    alphabet = string.ascii_uppercase + string.digits
    return "".join(secrets.choice(alphabet) for _ in range(length))