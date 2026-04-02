"""
Ad-Watch endpoints — handles the full ad-watching flow.

- POST /ad-watch/start     → begin an ad-watch session (called by bot)
- POST /ad-watch/step      → record completion of an ad step (called by web page)
- POST /ad-watch/activate  → activate 12-hour free access (called by bot on deep-link return)
- GET  /ad-watch/status     → check user's ad-watch access status
- GET  /ad-watch/page       → serve the ad web page
"""
from __future__ import annotations

import logging
import os
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.models.user import User
from backend.schemas.ad_watch import (
    AdStepComplete,
    AdStepCompleteResponse,
    AdWatchActivate,
    AdWatchActivateResponse,
    AdWatchStart,
    AdWatchStartResponse,
)
from backend.services.ad_watch_service import AdWatchService
from backend.services.platform_settings_service import PlatformSettingsService
from backend.services.user_service import UserService

logger = logging.getLogger(__name__)
router = APIRouter()

_AD_PAGE_PATH = Path(__file__).resolve().parent.parent.parent / "static" / "ad_page.html"


@router.post("/start", response_model=AdWatchStartResponse)
async def start_ad_watch(body: AdWatchStart, request: Request, db: AsyncSession = Depends(get_db)):
    """Begin an ad-watch session. Returns a token and the ad page URL."""
    user_svc = UserService(db)
    user = await user_svc.get_by_telegram_id(body.telegram_id)
    if not user:
        raise HTTPException(404, "User not registered")

    settings_svc = PlatformSettingsService(db)
    if (await settings_svc.get("ad_watch_enabled", "true")).lower() not in ("true", "1", "yes"):
        raise HTTPException(400, "Ad watch is currently disabled")

    svc = AdWatchService(db)

    # Check if user already has active ad access
    existing = await svc.has_active_ad_access(user.id)
    if existing:
        raise HTTPException(400, f"You already have free access until {existing.expires_at.isoformat()}")

    session = await svc.start_session(user.id)
    await db.commit()

    timer = await settings_svc.get_int("ad_watch_timer_seconds", 15)
    free_hours = await settings_svc.get_int("ad_watch_free_hours", 12)
    # Use public_base_url setting if set (required for Telegram HTTPS URLs)
    public_url = (await settings_svc.get("public_base_url", "")).rstrip("/")
    base_url = public_url or str(request.base_url).rstrip("/")
    bot_username = body.bot_username or ""

    ad_page_url = (
        f"{base_url}/ad-watch/page"
        f"?token={session.token}"
        f"&step=1"
        f"&total={session.ads_required}"
        f"&timer={timer}"
        f"&bot={bot_username}"
        f"&api={base_url}"
        f"&hours={free_hours}"
    )

    return AdWatchStartResponse(
        token=session.token,
        ads_required=session.ads_required,
        ad_page_url=ad_page_url,
        free_hours=free_hours,
    )


@router.post("/step", response_model=AdStepCompleteResponse)
async def complete_ad_step(body: AdStepComplete, db: AsyncSession = Depends(get_db)):
    """Record completion of an ad step."""
    svc = AdWatchService(db)
    try:
        token = await svc.complete_step(body.token, body.step)
    except ValueError as e:
        raise HTTPException(400, str(e))

    all_done = token.ads_completed >= token.ads_required
    redirect = None

    if all_done:
        # Auto-activate when all steps done
        try:
            token = await svc.activate(body.token)
            if body.bot_username:
                redirect = f"https://t.me/{body.bot_username}?start=adwatch_{body.token}"
        except ValueError:
            pass

    await db.commit()

    return AdStepCompleteResponse(
        step_completed=token.ads_completed,
        ads_remaining=max(0, token.ads_required - token.ads_completed),
        all_done=all_done,
        redirect_deep_link=redirect,
    )


@router.post("/activate", response_model=AdWatchActivateResponse)
async def activate_ad_access(body: AdWatchActivate, db: AsyncSession = Depends(get_db)):
    """Activate 12-hour free access after all ads watched. Called by the bot on return."""
    svc = AdWatchService(db)
    token = await svc.get_by_token(body.token)

    if not token:
        raise HTTPException(400, "Invalid ad-watch token")

    if token.activated and token.is_active:
        return AdWatchActivateResponse(
            activated=True,
            expires_at=token.expires_at.isoformat() if token.expires_at else None,
            message="Free access already active!",
        )

    if not token.activated:
        try:
            token = await svc.activate(body.token)
        except ValueError as e:
            raise HTTPException(400, str(e))

    await db.commit()

    return AdWatchActivateResponse(
        activated=True,
        expires_at=token.expires_at.isoformat() if token.expires_at else None,
        message=f"🎉 Free access activated! Valid for {(token.expires_at - token.activated_at).total_seconds() / 3600:.0f} hours.",
    )


@router.get("/status")
async def check_ad_access(telegram_id: int, db: AsyncSession = Depends(get_db)):
    """Check if user has active ad-watch free access."""
    user_svc = UserService(db)
    user = await user_svc.get_by_telegram_id(telegram_id)
    if not user:
        raise HTTPException(404, "User not registered")

    svc = AdWatchService(db)
    active = await svc.has_active_ad_access(user.id)

    if active:
        return {
            "has_access": True,
            "expires_at": active.expires_at.isoformat() if active.expires_at else None,
        }
    return {"has_access": False, "expires_at": None}


@router.get("/page", response_class=HTMLResponse)
async def serve_ad_page():
    """Serve the ad viewing web page."""
    if _AD_PAGE_PATH.exists():
        return HTMLResponse(_AD_PAGE_PATH.read_text(encoding="utf-8"))
    return HTMLResponse("<h1>Ad page not found</h1>", status_code=404)



