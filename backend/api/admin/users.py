"""Admin CRUD for users."""

from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.models.credit import Credit
from backend.models.membership import Membership
from backend.models.user import User
from backend.schemas.user import UserCreate, UserRead, UserUpdate
from backend.services.user_service import UserService
from backend.engines.credit_engine import CreditEngine
from backend.engines.membership_engine import MembershipEngine

router = APIRouter()


@router.get("", response_model=list[UserRead])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    svc = UserService(db)
    return await svc.list_all(limit=limit, offset=skip)


@router.get("/count")
async def user_count(db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    total = await svc.count()
    return {"count": total}


@router.get("/{user_id}/detail")
async def get_user_detail(user_id: int, db: AsyncSession = Depends(get_db)):
    """Full user detail: profile + credit balance + memberships."""
    svc = UserService(db)
    user = await svc.get_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")

    # Credit
    cr = await db.execute(select(Credit).where(Credit.user_id == user.id))
    credit = cr.scalar_one_or_none()

    # Memberships
    mr = await db.execute(
        select(Membership).where(Membership.user_id == user.id)
        .order_by(Membership.start_at.desc())
    )
    memberships = mr.scalars().all()

    return {
        "id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "level": user.level,
        "created_at": user.created_at.isoformat() if user.created_at else None,
        "last_active_at": user.last_active_at.isoformat() if user.last_active_at else None,
        "blocked_until": user.blocked_until.isoformat() if user.blocked_until else None,
        "credit_balance": credit.balance if credit else 0,
        "memberships": [
            {
                "id": m.id,
                "membership_type": m.membership_type,
                "start_at": m.start_at.isoformat() if m.start_at else None,
                "expiry_at": m.expiry_at.isoformat() if m.expiry_at else None,
                "is_active": m.is_active,
            }
            for m in memberships
        ],
    }


@router.post("/{user_id}/grant-credits")
async def grant_credits(user_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    """Grant or deduct credits for a user. Body: {amount: int, reason: str}."""
    amount = body.get("amount", 0)
    reason = body.get("reason", "admin action")
    if not amount:
        raise HTTPException(400, "Amount is required")

    engine = CreditEngine(db)
    try:
        if amount > 0:
            new_balance = await engine.add(user_id, amount, reason)
        else:
            new_balance = await engine.deduct(user_id, abs(amount), reason)
        await db.commit()
        return {"balance": new_balance}
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.post("/{user_id}/grant-membership")
async def grant_membership_for_user(user_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    """Grant membership. Body: {membership_type: str, days: int, hours: int}."""
    mtype = body.get("membership_type", "vip")
    days = body.get("days", 30)
    hours = body.get("hours", 0)
    expiry = datetime.now(timezone.utc) + timedelta(days=days, hours=hours) if (days > 0 or hours > 0) else None
    engine = MembershipEngine(db)
    membership = await engine.grant(user_id=user_id, membership_type=mtype, expiry_at=expiry)
    await db.commit()
    return {
        "id": membership.id,
        "membership_type": membership.membership_type,
        "expiry_at": membership.expiry_at.isoformat() if membership.expiry_at else None,
    }


@router.post("/{user_id}/set-level")
async def set_user_level(user_id: int, body: dict, db: AsyncSession = Depends(get_db)):
    """Set user level. Body: {level: int}."""
    level = body.get("level", 0)
    svc = UserService(db)
    user = await svc.get_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    user.level = level
    await db.commit()
    return {"level": user.level}


@router.get("/{user_id}", response_model=UserRead)
async def get_user(user_id: int, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    user = await svc.get_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.post("", response_model=UserRead, status_code=201)
async def create_user(body: UserCreate, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    user, _created = await svc.get_or_create(telegram_id=body.telegram_id, username=body.username)
    return user


@router.patch("/{user_id}", response_model=UserRead)
async def update_user(user_id: int, body: UserUpdate, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    user = await svc.update(user_id, body)
    if not user:
        raise HTTPException(404, "User not found")
    return user


@router.post("/{user_id}/block", response_model=UserRead)
async def block_user(user_id: int, db: AsyncSession = Depends(get_db)):
    from datetime import datetime, timezone, timedelta
    svc = UserService(db)
    ok = await svc.block(user_id, until=datetime.now(timezone.utc) + timedelta(days=36500))
    if not ok:
        raise HTTPException(404, "User not found")
    user = await svc.get_by_id(user_id)
    return user


@router.post("/{user_id}/unblock", response_model=UserRead)
async def unblock_user(user_id: int, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    ok = await svc.unblock(user_id)
    if not ok:
        raise HTTPException(404, "User not found")
    user = await svc.get_by_id(user_id)
    return user


@router.delete("/{user_id}")
async def delete_user(user_id: int, db: AsyncSession = Depends(get_db)):
    svc = UserService(db)
    user = await svc.get_by_id(user_id)
    if not user:
        raise HTTPException(404, "User not found")
    await db.delete(user)
    await db.flush()
    return {"detail": "User deleted"}