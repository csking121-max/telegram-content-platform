"""Admin CRUD for users."""

from datetime import datetime, timezone, timedelta
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.models.credit import Credit
from backend.models.membership import Membership
from backend.models.user import User
from backend.schemas.user import UserCreate, UserRead, UserUpdate
from backend.services.user_service import UserService
from backend.engines.credit_engine import CreditEngine
from backend.engines.membership_engine import MembershipEngine


# ── Request schemas ──────────────────────────────────────
class GrantCreditsBody(BaseModel):
    amount: int = Field(..., description="Positive to add, negative to deduct")
    reason: str = Field("admin action", max_length=200)


class GrantMembershipBody(BaseModel):
    membership_type: str = Field("vip", max_length=50)
    days: int = Field(30, ge=0, le=3650)
    hours: int = Field(0, ge=0, le=8760)


class SetLevelBody(BaseModel):
    level: int = Field(..., ge=0, le=100)


class UserListRead(UserRead):
    credit_balance: int = 0
    active_membership: str | None = None
    active_membership_count: int = 0

router = APIRouter()


@router.get("", response_model=list[UserListRead])
async def list_users(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    search: str | None = Query(None, max_length=255),
    status: Literal["all", "active", "blocked"] = Query("all"),
    membership: str = Query("all", max_length=64),
    sort_by: Literal[
        "id",
        "telegram_id",
        "username",
        "level",
        "status",
        "created_at",
        "last_active_at",
        "credit_balance",
        "membership",
    ] = Query("created_at"),
    sort_dir: Literal["asc", "desc"] = Query("desc"),
    db: AsyncSession = Depends(get_db),
):
    now = datetime.now(timezone.utc)
    active_membership_filter = or_(Membership.expiry_at.is_(None), Membership.expiry_at > now)
    active_memberships = (
        select(
            Membership.user_id.label("user_id"),
            func.count(Membership.id).label("active_membership_count"),
            func.min(Membership.membership_type).label("active_membership"),
        )
        .where(active_membership_filter)
        .group_by(Membership.user_id)
        .subquery()
    )

    stmt = (
        select(
            User,
            func.coalesce(Credit.balance, 0).label("credit_balance"),
            func.coalesce(active_memberships.c.active_membership_count, 0).label("active_membership_count"),
            active_memberships.c.active_membership.label("active_membership"),
        )
        .outerjoin(Credit, Credit.user_id == User.id)
        .outerjoin(active_memberships, active_memberships.c.user_id == User.id)
    )

    if search:
        stripped = search.strip()
        term = f"%{stripped.lower()}%"
        conditions = [func.lower(func.coalesce(User.username, "")).like(term)]
        if stripped.isdigit():
            numeric = int(stripped)
            conditions.extend([User.id == numeric, User.telegram_id == numeric])
        stmt = stmt.where(or_(*conditions))

    if status == "blocked":
        stmt = stmt.where(User.blocked_until.is_not(None), User.blocked_until > now)
    elif status == "active":
        stmt = stmt.where(or_(User.blocked_until.is_(None), User.blocked_until <= now))

    membership_key = membership.strip().lower()
    if membership_key == "active":
        stmt = stmt.where(func.coalesce(active_memberships.c.active_membership_count, 0) > 0)
    elif membership_key == "none":
        stmt = stmt.where(func.coalesce(active_memberships.c.active_membership_count, 0) == 0)
    elif membership_key not in {"", "all"}:
        stmt = stmt.where(
            User.id.in_(
                select(Membership.user_id).where(
                    func.lower(Membership.membership_type) == membership_key,
                    active_membership_filter,
                )
            )
        )

    sort_columns = {
        "id": User.id,
        "telegram_id": User.telegram_id,
        "username": func.lower(func.coalesce(User.username, "")),
        "level": User.level,
        "status": User.blocked_until,
        "created_at": User.created_at,
        "last_active_at": User.last_active_at,
        "credit_balance": func.coalesce(Credit.balance, 0),
        "membership": func.coalesce(active_memberships.c.active_membership, ""),
    }
    order_col = sort_columns[sort_by]
    stmt = stmt.order_by(order_col.asc() if sort_dir == "asc" else order_col.desc(), User.id.desc())
    stmt = stmt.limit(limit).offset(skip)

    result = await db.execute(stmt)
    return [
        UserListRead(
            id=user.id,
            telegram_id=user.telegram_id,
            username=user.username,
            level=user.level,
            created_at=user.created_at,
            last_active_at=user.last_active_at,
            blocked_until=user.blocked_until,
            credit_balance=int(balance or 0),
            active_membership=active_membership,
            active_membership_count=int(active_count or 0),
        )
        for user, balance, active_count, active_membership in result.all()
    ]


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
async def grant_credits(user_id: int, body: GrantCreditsBody, db: AsyncSession = Depends(get_db)):
    """Grant or deduct credits for a user."""
    amount = body.amount
    reason = body.reason
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
async def grant_membership_for_user(user_id: int, body: GrantMembershipBody, db: AsyncSession = Depends(get_db)):
    """Grant membership."""
    mtype = body.membership_type
    days = body.days
    hours = body.hours
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
async def set_user_level(user_id: int, body: SetLevelBody, db: AsyncSession = Depends(get_db)):
    """Set user level."""
    level = body.level
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
