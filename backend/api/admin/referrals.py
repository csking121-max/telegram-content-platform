"""Admin CRUD for referrals."""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.dependencies import get_db
from backend.schemas.referral import ReferralCreate, ReferralRead
from backend.models.referral import Referral
from backend.services.referral_service import ReferralService

router = APIRouter()


@router.get("/user/{user_id}", response_model=list[ReferralRead])
async def get_user_referrals(
    user_id: int,
    db: AsyncSession = Depends(get_db),
):
    """All referrals where ``user_id`` is the inviter."""
    result = await db.execute(
        select(Referral)
        .where(Referral.inviter_id == user_id)
        .order_by(Referral.created_at.desc())
    )
    return result.scalars().all()


@router.get("/count/{user_id}")
async def referral_count(user_id: int, db: AsyncSession = Depends(get_db)):
    svc = ReferralService(db)
    total = await svc.count_successful(user_id)
    return {"user_id": user_id, "successful_referrals": total}


@router.post("", response_model=ReferralRead, status_code=201)
async def create_invite(body: ReferralCreate, db: AsyncSession = Depends(get_db)):
    svc = ReferralService(db)
    referral = await svc.create_invite(referrer_user_id=body.inviter_id)
    return referral


@router.get("/{invite_code}", response_model=ReferralRead)
async def get_by_code(invite_code: str, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Referral).where(Referral.invite_code == invite_code)
    )
    referral = result.scalar_one_or_none()
    if not referral:
        raise HTTPException(404, "Referral not found")
    return referral