"""
Admin authentication endpoint — issue JWT tokens.
Includes rate limiting to prevent brute-force attacks.
"""

import logging
import secrets as _secrets
import time
from collections import defaultdict
from threading import Lock

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from backend.security.auth import create_access_token, verify_password
from backend.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# ── Login rate limiting (Redis-backed with in-memory fallback) ───
_LOGIN_MAX_ATTEMPTS = 5       # max failed attempts per window
_LOGIN_WINDOW_SECONDS = 900   # 15-minute lockout window

# In-memory fallback (used when Redis unavailable)
_login_attempts: dict[str, list[float]] = defaultdict(list)
_login_lock = Lock()


def _check_login_rate(client_ip: str) -> None:
    """Raise 429 if the client has exceeded the login attempt limit."""
    try:
        from backend.redis_client import RedisClient
        rc = RedisClient.get()
        key = f"login_attempts:{client_ip}"
        count = rc.client.get(key)
        if count and int(count) >= _LOGIN_MAX_ATTEMPTS:
            logger.warning("Login rate limit exceeded for IP=%s", client_ip)
            raise HTTPException(
                status_code=429,
                detail=f"Too many login attempts. Try again in {_LOGIN_WINDOW_SECONDS // 60} minutes.",
            )
        return
    except HTTPException:
        raise
    except Exception:
        pass  # Fall back to in-memory

    now = time.monotonic()
    with _login_lock:
        attempts = _login_attempts[client_ip]
        _login_attempts[client_ip] = [t for t in attempts if now - t < _LOGIN_WINDOW_SECONDS]
        if len(_login_attempts[client_ip]) >= _LOGIN_MAX_ATTEMPTS:
            logger.warning("Login rate limit exceeded for IP=%s", client_ip)
            raise HTTPException(
                status_code=429,
                detail=f"Too many login attempts. Try again in {_LOGIN_WINDOW_SECONDS // 60} minutes.",
            )


def _record_failed_attempt(client_ip: str) -> None:
    """Record a failed login attempt."""
    try:
        from backend.redis_client import RedisClient
        rc = RedisClient.get()
        key = f"login_attempts:{client_ip}"
        pipe = rc.client.pipeline()
        pipe.incr(key)
        pipe.expire(key, _LOGIN_WINDOW_SECONDS)
        pipe.execute()
        return
    except Exception:
        pass  # Fall back to in-memory

    with _login_lock:
        _login_attempts[client_ip].append(time.monotonic())


class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=LoginResponse)
async def admin_login(body: LoginRequest, request: Request, response: Response):
    """
    Authenticate admin and return a JWT.

    Credentials are validated against env vars ADMIN_USERNAME / ADMIN_PASSWORD_HASH.
    Rate-limited to prevent brute-force attacks.
    """
    client_ip = request.client.host if request.client else "unknown"
    _check_login_rate(client_ip)

    if body.username != settings.ADMIN_USERNAME:
        _record_failed_attempt(client_ip)
        raise HTTPException(401, "Invalid credentials")

    # ADMIN_PASSWORD should be a bcrypt hash in production
    stored = settings.ADMIN_PASSWORD
    try:
        if stored.startswith("$2b$") or stored.startswith("$2a$"):
            valid = verify_password(body.password, stored)
        else:
            # Plaintext fallback — constant-time comparison
            valid = _secrets.compare_digest(body.password, stored)
            if valid:
                logger.warning("ADMIN_PASSWORD is plaintext — set a bcrypt hash for production")
    except Exception:
        logger.warning("Password verification failed — ADMIN_PASSWORD may not be a bcrypt hash")
        valid = False

    if not valid:
        _record_failed_attempt(client_ip)
        raise HTTPException(401, "Invalid credentials")

    token = create_access_token(data={"sub": body.username, "role": "admin"})

    # Set httpOnly secure cookie (SEC-3)
    response.set_cookie(
        key="admin_access_token",
        value=token,
        httponly=True,
        samesite="strict",
        secure=settings.COOKIE_SECURE,
        max_age=settings.ADMIN_JWT_EXPIRY_HOURS * 3600,
        path="/",
    )
    # Also set a readable CSRF token cookie (SEC-4)
    csrf_token = _secrets.token_urlsafe(32)
    response.set_cookie(
        key="csrf_token",
        value=csrf_token,
        httponly=False,   # JS must read this
        samesite="strict",
        secure=settings.COOKIE_SECURE,
        max_age=settings.ADMIN_JWT_EXPIRY_HOURS * 3600,
        path="/",
    )

    return LoginResponse(access_token=token)


@router.post("/logout")
async def admin_logout(request: Request, response: Response):
    """Clear auth cookies and blacklist the current JWT."""
    from backend.security.auth import blacklist_token_from_request
    blacklist_token_from_request(request)

    response.delete_cookie("admin_access_token", path="/")
    response.delete_cookie("csrf_token", path="/")
    return {"detail": "Logged out"}
