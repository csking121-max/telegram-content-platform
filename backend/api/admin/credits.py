"""Admin CRUD for credits."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.dependencies import get_db
from backend.schemas.credit import CreditRead, CreditAdjust, CreditHistoryRead
from backend.models.credit import Credit
from backend.models.credit_history import CreditHistory
from backend.models.user import User
from backend.engines.credit_engine import CreditEngine

router = APIRouter()


@router.get("/lookup")
async def lookup_credit_by_telegram(
    telegram_id: int = Query(...),
    db: AsyncSession = Depends(get_db),
):
    """Lookup a user's credit by telegram_id (more intuitive for admins)."""
    result = await db.execute(select(User).where(User.telegram_id == telegram_id))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, "User not found with that Telegram ID")
    # Ensure credit account exists
    engine = CreditEngine(db)
    await engine.ensure_account(user.id)
    await db.commit()
    cr = await db.execute(select(Credit).where(Credit.user_id == user.id))
    credit = cr.scalar_one_or_none()
    return {
        "user_id": user.id,
        "telegram_id": user.telegram_id,
        "username": user.username,
        "balance": credit.balance if credit else 0,
    }


@router.get("/{user_id}", response_model=CreditRead)
async def get_credit(user_id: int, db: AsyncSession = Depends(get_db)):
    # Try user_id first, then treat as telegram_id
    result = await db.execute(select(Credit).where(Credit.user_id == user_id))
    credit = result.scalar_one_or_none()
    if not credit:
        # Maybe user entered a telegram_id?
        usr = await db.execute(select(User).where(User.telegram_id == user_id))
        user = usr.scalar_one_or_none()
        if user:
            engine = CreditEngine(db)
            await engine.ensure_account(user.id)
            await db.commit()
            result2 = await db.execute(select(Credit).where(Credit.user_id == user.id))
            credit = result2.scalar_one_or_none()
    if not credit:
        raise HTTPException(404, "Credit account not found")
    return credit


@router.post("/adjust", response_model=CreditRead)
async def adjust_credit(body: CreditAdjust, db: AsyncSession = Depends(get_db)):
    """Add or deduct credits. Positive change_amount → add, negative → deduct."""
    engine = CreditEngine(db)
    try:
        if body.change_amount > 0:
            await engine.add(
                user_id=body.user_id, amount=body.change_amount, reason=body.reason,
            )
        elif body.change_amount < 0:
            await engine.deduct(
                user_id=body.user_id, amount=abs(body.change_amount), reason=body.reason,
            )
        else:
            raise HTTPException(400, "Amount must be non-zero")
    except ValueError as e:
        raise HTTPException(400, str(e))

    result = await db.execute(select(Credit).where(Credit.user_id == body.user_id))
    credit = result.scalar_one_or_none()
    if not credit:
        raise HTTPException(400, "Credit operation failed")
    return credit


@router.post("/set", response_model=CreditRead)
async def set_credit(body: CreditAdjust, db: AsyncSession = Depends(get_db)):
    """Override a user's balance to an exact value."""
    engine = CreditEngine(db)
    await engine.admin_set(
        user_id=body.user_id, new_balance=body.change_amount, reason=body.reason,
    )
    result = await db.execute(select(Credit).where(Credit.user_id == body.user_id))
    credit = result.scalar_one_or_none()
    if not credit:
        raise HTTPException(404, "Credit account not found")
    return credit


@router.get("/{user_id}/history", response_model=list[CreditHistoryRead])
async def credit_history(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(CreditHistory)
        .where(CreditHistory.user_id == user_id)
        .order_by(CreditHistory.created_at.desc())
        .offset(skip)
        .limit(limit)
    )
    return result.scalars().all()