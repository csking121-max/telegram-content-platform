"""Admin CRUD for memberships."""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from backend.dependencies import get_db
from backend.schemas.membership import MembershipCreate, MembershipRead
from backend.models.membership import Membership
from backend.engines.membership_engine import MembershipEngine

router = APIRouter()


@router.get("/{user_id}", response_model=list[MembershipRead])
async def get_memberships(user_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Membership)
        .where(Membership.user_id == user_id)
        .order_by(Membership.start_at.desc())
    )
    return result.scalars().all()


@router.get("/{user_id}/active", response_model=list[MembershipRead])
async def get_active_memberships(user_id: int, db: AsyncSession = Depends(get_db)):
    engine = MembershipEngine(db)
    return await engine.get_active(user_id)


@router.post("", response_model=MembershipRead, status_code=201)
async def grant_membership(body: MembershipCreate, db: AsyncSession = Depends(get_db)):
    engine = MembershipEngine(db)
    membership = await engine.grant(
        user_id=body.user_id,
        membership_type=body.membership_type,
        expiry_at=body.expiry_at,
    )
    return membership


@router.post("/{membership_id}/revoke", response_model=MembershipRead)
async def revoke_membership(membership_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Membership).where(Membership.id == membership_id)
    )
    membership = result.scalar_one_or_none()
    if not membership:
        raise HTTPException(404, "Membership not found")

    membership.expiry_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(membership)
    return membership