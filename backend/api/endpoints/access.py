"""
Public access-check endpoint.

Called by bots (or directly) to verify a user's access right
to a content pack via token, credits, or membership.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.schemas.access import AccessRequest, AccessResponse
from backend.engines.access_control import AccessControlEngine
from backend.models.credit import Credit
from backend.models.membership import Membership
from backend.models.user import User
from backend.services.activity_logger import ActivityLogger
from backend.services.cooldown_service import CooldownService
from backend.services.platform_settings_service import PlatformSettingsService
from backend.api.endpoints.internal import verify_internal_key

router = APIRouter()


@router.post("/check", response_model=AccessResponse)
async def check_access(
    body: AccessRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Evaluate whether a user may access a pack.

    Returns AccessResponse with allowed/denied + reason.
    
    Checks:
    1. Cooldown: User must not be in cooldown period (exceeded link access limit)
    2. Access Control: Token, credits, membership validation
    """
    # Resolve user_id from telegram_id
    log_user_id: int = 0
    if body.telegram_id:
        from sqlalchemy import select as _sel
        _u = await db.execute(_sel(User.id).where(User.telegram_id == body.telegram_id))
        log_user_id = _u.scalar_one_or_none() or 0

    # Check cooldown BEFORE access control
    if log_user_id:
        cooldown_svc = CooldownService(db)
        active_cooldown = await cooldown_svc.get_cooldown_for_user(log_user_id)
        if active_cooldown:
            remaining = int((active_cooldown.cooldown_until - __import__("datetime").datetime.now(__import__("datetime").timezone.utc)).total_seconds())
            reason = f"User is in cooldown. Remaining time: {max(remaining, 0)} seconds"
            
            # Log denied access
            activity = ActivityLogger(db)
            await activity.log(
                user_id=log_user_id,
                action="access_check",
                payload={"token": body.token, "allowed": False, "reason": "cooldown_active", "remaining_seconds": max(remaining, 0)},
            )
            await db.commit()
            raise HTTPException(status_code=429, detail=reason)

    # Perform standard access control check
    engine = AccessControlEngine(db)
    result: AccessResponse = await engine.check(
        telegram_id=body.telegram_id,
        token_str=body.token,
    )

    # If access is allowed, increment link access count
    if result.allowed and log_user_id:
        cooldown_svc = CooldownService(db)
        settings_svc = PlatformSettingsService(db)
        
        cooldown_links_limit = await settings_svc.get_int("cooldown_links_limit", 5)
        cooldown_seconds = await settings_svc.get_int("cooldown_seconds", 3600)
        
        access_count, should_cooldown = await cooldown_svc.increment_access_count(
            log_user_id,
            cooldown_links_limit,
            cooldown_seconds,
        )
        
        if should_cooldown:
            # Apply cooldown
            await cooldown_svc.apply_cooldown(
                user_id=log_user_id,
                cooldown_seconds=cooldown_seconds,
                access_count=access_count,
                cooldown_links_limit=cooldown_links_limit,
            )
            await db.commit()
            reason = f"Link access limit ({cooldown_links_limit}) exceeded. Cooldown applied for {cooldown_seconds} seconds."
            raise HTTPException(status_code=429, detail=reason)

    # Log access check
    activity = ActivityLogger(db)
    if log_user_id:
        await activity.log(
            user_id=log_user_id,
            action="access_check",
            payload={"token": body.token, "allowed": result.allowed, "reason": result.reason},
        )
    await db.commit()

    if not result.allowed:
        raise HTTPException(status_code=403, detail=result.reason)

    return result


@router.get("/profile/{telegram_id}")
async def get_user_profile(
    telegram_id: int,
    db: AsyncSession = Depends(get_db),
    _auth: None = Depends(verify_internal_key),
):
    """
    Get user profile with membership, credit, ad-watch, daily-pass, and referral info.
    Called by the Telegram bot to show user dashboard.

    Optimised: uses parallel queries and JOINs to avoid N+1 per-field round-trips.
    """
    import asyncio
    from datetime import datetime, timezone
    from sqlalchemy import func as sa_func

    # ── 1. Find user ─────────────────────────────────────────
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    now = datetime.now(timezone.utc)

    # ── 2. Fire independent queries concurrently ─────────────
    async def _credit():
        r = await db.execute(select(Credit).where(Credit.user_id == user.id))
        c = r.scalar_one_or_none()
        return c.balance if c else 0

    async def _memberships():
        r = await db.execute(
            select(Membership)
            .where(
                Membership.user_id == user.id,
                (Membership.expiry_at.is_(None)) | (Membership.expiry_at > now),
            )
            .order_by(Membership.start_at.desc())
        )
        return list(r.scalars().all())

    async def _ad_watch():
        try:
            from backend.models.ad_watch_token import AdWatchToken
            r = await db.execute(
                select(AdWatchToken)
                .where(
                    AdWatchToken.user_id == user.id,
                    AdWatchToken.activated == True,
                    AdWatchToken.expires_at > now,
                )
                .order_by(AdWatchToken.expires_at.desc())
                .limit(1)
            )
            token = r.scalar_one_or_none()
            if token:
                return True, token.expires_at.isoformat() if token.expires_at else ""
        except Exception:
            pass
        return False, ""

    async def _referral_stats():
        try:
            from backend.models.referral import Referral
            from backend.models.credit_history import CreditHistory
            r1 = await db.execute(
                select(sa_func.count()).select_from(Referral).where(Referral.inviter_id == user.id)
            )
            count = r1.scalar() or 0
            r2 = await db.execute(
                select(sa_func.coalesce(sa_func.sum(CreditHistory.change_amount), 0))
                .where(
                    CreditHistory.user_id == user.id,
                    CreditHistory.reason.like("referral%"),
                )
            )
            credits = r2.scalar() or 0
            return count, credits
        except Exception:
            return 0, 0

    async def _streak():
        try:
            from backend.engines.streak_engine import StreakEngine
            return await StreakEngine(db).get_user_streak(user.id)
        except Exception:
            return {}

    async def _max_tier():
        try:
            from backend.engines.membership_engine import MembershipEngine
            return await MembershipEngine(db).get_user_max_tier_level(user.id)
        except Exception:
            return 0

    (
        balance,
        active_memberships,
        (ad_watch_active, ad_watch_expires),
        (referral_count, referral_credits_earned),
        streak_info,
        max_tier_level,
    ) = await asyncio.gather(
        _credit(),
        _memberships(),
        _ad_watch(),
        _referral_stats(),
        _streak(),
        _max_tier(),
    )

    membership = active_memberships[0] if active_memberships else None
    daily_pass_active = any(m.membership_type == "daily_pass" for m in active_memberships)

    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "level": user.level,
        "credits": balance,
        "membership_type": membership.membership_type if membership else "free",
        "membership_expiry": (
            membership.expiry_at.isoformat() if membership and membership.expiry_at else "N/A"
        ),
        "active_memberships": [
            {
                "type": m.membership_type,
                "expiry_at": m.expiry_at.isoformat() if m.expiry_at else None,
            }
            for m in active_memberships
        ],
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "daily_pass_active": daily_pass_active,
        "ad_watch_active": ad_watch_active,
        "ad_watch_expires": ad_watch_expires,
        "referral_count": referral_count,
        "referral_credits_earned": referral_credits_earned,
        "max_tier_level": max_tier_level,
        "streak": streak_info,
    }