"""
Shared HTTP utilities for the Telegram gateway.

Extracted here to avoid circular imports between bot_manager and handlers.
"""
from __future__ import annotations

import asyncio
import hashlib
import hmac
import json
import logging
import os
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BACKEND_URL = os.getenv("BACKEND_INTERNAL_URL", "http://localhost:8000")
INTERNAL_API_KEY = os.getenv("INTERNAL_API_KEY", "")

MAX_RETRIES = 3
RETRY_BACKOFF = 1.0  # seconds, doubles each retry


def _internal_headers() -> dict[str, str]:
    """Headers for all internal API calls."""
    headers: dict[str, str] = {}
    if INTERNAL_API_KEY:
        headers["X-Internal-Key"] = INTERNAL_API_KEY
    return headers


def _sign_payload(payload: bytes, secret: str) -> str:
    """Produce HMAC-SHA256 hex digest for webhook validation."""
    return hmac.new(secret.encode(), payload, hashlib.sha256).hexdigest()


async def forward_to_backend(
    bot_username: str,
    hmac_secret: str,
    data: dict[str, Any],
) -> dict[str, Any] | None:
    """POST ``data`` to ``/webhook/{bot_username}`` with HMAC header.

    Retries up to MAX_RETRIES times with exponential backoff on transient
    errors (connection failures, 5xx responses).  Returns None on failure
    instead of raising, for consistency with api_post/api_get.
    """
    body = json.dumps(data).encode()
    sig = _sign_payload(body, hmac_secret)
    url = f"{BACKEND_URL}/webhook/{bot_username}"

    last_exc: Exception | None = None
    for attempt in range(MAX_RETRIES):
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.post(
                    url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Signature": sig,
                    },
                )
                if resp.status_code < 500:
                    resp.raise_for_status()
                    return resp.json()
                # 5xx → retry
                logger.warning(
                    "forward_to_backend %s attempt %d → %s",
                    url, attempt + 1, resp.status_code,
                )
        except (httpx.ConnectError, httpx.ReadTimeout, httpx.WriteTimeout) as exc:
            last_exc = exc
            logger.warning(
                "forward_to_backend %s attempt %d → %s",
                url, attempt + 1, exc,
            )
        except httpx.HTTPStatusError as exc:
            # Non-5xx error already raised above; don't retry client errors
            logger.error("forward_to_backend %s → %s", url, exc)
            return None
        except Exception as exc:
            logger.exception("forward_to_backend %s unexpected error", url)
            return None

        if attempt < MAX_RETRIES - 1:
            await asyncio.sleep(RETRY_BACKOFF * (2 ** attempt))

    logger.error(
        "forward_to_backend %s failed after %d attempts: %s",
        url, MAX_RETRIES, last_exc,
    )
    return None


async def api_get(path: str) -> dict | list | None:
    """Simple GET to the backend API."""
    async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=15) as client:
        resp = await client.get(path, headers=_internal_headers())
        if resp.status_code == 200:
            return resp.json()
        logger.warning("GET %s → %s", path, resp.status_code)
    return None


async def api_post(path: str, payload: Any) -> dict | None:
    """Simple POST to the backend API."""
    try:
        async with httpx.AsyncClient(base_url=BACKEND_URL, timeout=15) as client:
            resp = await client.post(path, json=payload, headers=_internal_headers())
            if resp.status_code in (200, 201):
                return resp.json()
            logger.warning("POST %s → %s %s", path, resp.status_code, resp.text[:200])
            # Return error detail from backend if available
            try:
                body = resp.json()
                if isinstance(body, dict) and "detail" in body:
                    return {"_error": True, "status": "failed", "message": body["detail"]}
            except Exception:
                pass
    except httpx.ConnectError:
        logger.error("POST %s → connection refused (backend down?)", path)
    except Exception:
        logger.exception("POST %s failed", path)
    return None
