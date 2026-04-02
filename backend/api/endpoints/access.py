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
    """
    engine = AccessControlEngine(db)
    result: AccessResponse = await engine.check(
        telegram_id=body.telegram_id,
        token_str=body.token,
    )

    activity = ActivityLogger(db)
    await activity.log(
        user_id=0,
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
    """
    from datetime import datetime, timezone
    from sqlalchemy import func as sa_func

    # Find user
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found")

    # Get credit balance
    credit_result = await db.execute(select(Credit).where(Credit.user_id == user.id))
    credit = credit_result.scalar_one_or_none()
    balance = credit.balance if credit else 0

    # Get active membership
    now = datetime.now(timezone.utc)
    membership_result = await db.execute(
        select(Membership)
        .where(
            Membership.user_id == user.id,
            (Membership.expiry_at.is_(None)) | (Membership.expiry_at > now),
        )
        .order_by(Membership.start_at.desc())
    )
    active_memberships = list(membership_result.scalars().all())
    membership = active_memberships[0] if active_memberships else None

    # Check daily pass
    daily_pass_active = False
    daily_result = await db.execute(
        select(Membership)
        .where(
            Membership.user_id == user.id,
            Membership.membership_type == "daily_pass",
            (Membership.expiry_at.is_(None)) | (Membership.expiry_at > now),
        )
        .limit(1)
    )
    if daily_result.scalar_one_or_none():
        daily_pass_active = True

    # Check ad-watch access
    ad_watch_active = False
    ad_watch_expires = ""
    try:
        from backend.models.ad_watch_token import AdWatchToken
        ad_result = await db.execute(
            select(AdWatchToken)
            .where(
                AdWatchToken.user_id == user.id,
                AdWatchToken.activated == True,
                AdWatchToken.expires_at > now,
            )
            .order_by(AdWatchToken.expires_at.desc())
            .limit(1)
        )
        ad_token = ad_result.scalar_one_or_none()
        if ad_token:
            ad_watch_active = True
            ad_watch_expires = ad_token.expires_at.isoformat() if ad_token.expires_at else ""
    except Exception:
        pass  # Model may not exist yet

    # Referral stats
    referral_count = 0
    referral_credits_earned = 0
    try:
        from backend.models.referral import Referral
        ref_count_result = await db.execute(
            select(sa_func.count()).select_from(Referral).where(Referral.inviter_id == user.id)
        )
        referral_count = ref_count_result.scalar() or 0

        from backend.models.credit_history import CreditHistory
        ref_credits_result = await db.execute(
            select(sa_func.coalesce(sa_func.sum(CreditHistory.change_amount), 0))
            .where(
                CreditHistory.user_id == user.id,
                CreditHistory.reason.like("referral%"),
            )
        )
        referral_credits_earned = ref_credits_result.scalar() or 0
    except Exception:
        pass

    # Streak info
    streak_info = {}
    try:
        from backend.engines.streak_engine import StreakEngine
        streak_engine = StreakEngine(db)
        streak_info = await streak_engine.get_user_streak(user.id)
    except Exception:
        pass

    # Max tier level of active memberships
    max_tier_level = 0
    try:
        from backend.engines.membership_engine import MembershipEngine
        me = MembershipEngine(db)
        max_tier_level = await me.get_user_max_tier_level(user.id)
    except Exception:
        pass

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