"""
Admin JWT authentication + password hashing.
Supports both Bearer token (API) and httpOnly cookie (admin UI).
Includes JWT blacklist for token revocation.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Cookie, Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError, jwt
from passlib.context import CryptContext

from backend.config import settings
from backend.redis_client import RedisClient

logger = logging.getLogger(__name__)

_bearer = HTTPBearer(auto_error=False)  # auto_error=False so we can fall back to cookie
_pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")

ALGORITHM = "HS256"

# ── Redis-backed JWT blacklist ──────────────────────────────────
_BLACKLIST_PREFIX = "jwt:blacklist:"

# In-memory fallback if Redis is unavailable
_blacklisted_jtis: set[str] = set()
_blacklist_expiry: dict[str, float] = {}


def _prune_blacklist() -> None:
    """Remove expired entries from the in-memory fallback blacklist."""
    now = datetime.now(timezone.utc).timestamp()
    expired = [jti for jti, exp in _blacklist_expiry.items() if exp < now]
    for jti in expired:
        _blacklisted_jtis.discard(jti)
        _blacklist_expiry.pop(jti, None)


def _is_jti_blacklisted(jti: str) -> bool:
    """Check if a JTI is blacklisted, using Redis with in-memory fallback."""
    try:
        rc = RedisClient.get()
        return rc.client.exists(f"{_BLACKLIST_PREFIX}{jti}") > 0
    except Exception:
        return jti in _blacklisted_jtis


def _add_jti_to_blacklist(jti: str, exp_timestamp: float) -> None:
    """Add a JTI to the blacklist with TTL matching token expiry."""
    ttl = max(int(exp_timestamp - datetime.now(timezone.utc).timestamp()), 1)
    try:
        rc = RedisClient.get()
        rc.client.setex(f"{_BLACKLIST_PREFIX}{jti}", ttl, "1")
    except Exception:
        _blacklisted_jtis.add(jti)
        _blacklist_expiry[jti] = exp_timestamp


# ── Password helpers ────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return _pwd_ctx.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return _pwd_ctx.verify(plain, hashed)


# ── JWT helpers ─────────────────────────────────────────────────

def create_access_token(data: dict, expires_delta: timedelta | None = None) -> str:
    """Generic JWT creation with unique jti for revocation support."""
    expire = datetime.now(timezone.utc) + (
        expires_delta or timedelta(hours=settings.ADMIN_JWT_EXPIRY_HOURS)
    )
    payload = {**data, "exp": expire, "jti": uuid.uuid4().hex}
    return jwt.encode(payload, settings.ADMIN_JWT_SECRET, algorithm=ALGORITHM)


def create_admin_token(username: str) -> str:
    """Convenience: create a JWT for an authenticated admin."""
    return create_access_token(data={"sub": username, "type": "admin"})


def verify_admin_token(token: str) -> Optional[str]:
    """Returns the username if valid and not blacklisted, else None."""
    try:
        payload = jwt.decode(token, settings.ADMIN_JWT_SECRET, algorithms=[ALGORITHM])
        jti = payload.get("jti")
        if jti and _is_jti_blacklisted(jti):
            return None
        return payload.get("sub")
    except JWTError:
        return None


def blacklist_token(token: str) -> None:
    """Add a JWT's jti to the blacklist so it can't be reused."""
    _prune_blacklist()
    try:
        payload = jwt.decode(
            token, settings.ADMIN_JWT_SECRET, algorithms=[ALGORITHM],
            options={"verify_exp": False},
        )
        jti = payload.get("jti")
        exp = payload.get("exp", 0)
        if jti:
            _add_jti_to_blacklist(jti, float(exp))
    except JWTError:
        pass


def blacklist_token_from_request(request: Request) -> None:
    """Extract JWT from request (header or cookie) and blacklist it."""
    token = None
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
    if not token:
        token = request.cookies.get("admin_access_token")
    if token:
        blacklist_token(token)


async def require_admin(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(_bearer),
) -> str:
    """
    FastAPI dependency — protect admin routes.
    Reads JWT from Bearer header first, falls back to httpOnly cookie.
    Validates CSRF header on state-changing requests when using cookie auth.
    Returns admin username on success.
    """
    token: str | None = None
    using_cookie = False

    # 1. Try Bearer header
    if credentials and credentials.credentials:
        token = credentials.credentials
    # 2. Fall back to httpOnly cookie
    if not token:
        token = request.cookies.get("admin_access_token")
        if token:
            using_cookie = True

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Not authenticated",
        )

    username = verify_admin_token(token)
    if username is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired admin token",
        )

    # CSRF check for cookie-based auth on state-changing methods (SEC-4)
    if using_cookie and request.method in ("POST", "PUT", "PATCH", "DELETE"):
        csrf_cookie = request.cookies.get("csrf_token", "")
        csrf_header = request.headers.get("x-csrf-token", "")
        if not csrf_cookie or csrf_cookie != csrf_header:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="CSRF token missing or invalid",
            )

    return username