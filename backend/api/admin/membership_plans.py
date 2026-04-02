"""Admin CRUD for membership plans (pricing, duration, access type)."""

from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import func, select

from backend.dependencies import get_db
from backend.schemas.membership_plan import MembershipPlanCreate, MembershipPlanRead, MembershipPlanUpdate
from backend.models.membership import Membership
from backend.models.membership_plan import MembershipPlan
from backend.models.user import User

router = APIRouter()


class PlanMember(BaseModel):
    membership_id: int
    user_id: int
    telegram_id: int
    username: Optional[str] = None
    membership_type: str
    start_at: str
    expiry_at: Optional[str] = None


class PlanReadWithMembers(MembershipPlanRead):
    active_member_count: int = 0


@router.get("", response_model=list[PlanReadWithMembers])
async def list_plans(
    include_inactive: bool = Query(False),
    db: AsyncSession = Depends(get_db),
):
    """List all membership plans with active member counts."""
    query = select(MembershipPlan).order_by(MembershipPlan.sort_order, MembershipPlan.price_inr)
    if not include_inactive:
        query = query.where(MembershipPlan.is_active == True)  # noqa: E712
    result = await db.execute(query)
    plans = result.scalars().all()

    # Build active member counts per access_type
    count_q = (
        select(Membership.membership_type, func.count(Membership.id))
        .where(
            (Membership.expiry_at.is_(None)) | (Membership.expiry_at > func.now())
        )
        .group_by(Membership.membership_type)
    )
    count_result = await db.execute(count_q)
    counts = dict(count_result.all())

    out = []
    for p in plans:
        data = PlanReadWithMembers.model_validate(p)
        data.active_member_count = counts.get(p.access_type, 0)
        out.append(data)
    return out


@router.get("/{plan_id}", response_model=MembershipPlanRead)
async def get_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    return plan


@router.post("", response_model=MembershipPlanRead, status_code=201)
async def create_plan(body: MembershipPlanCreate, db: AsyncSession = Depends(get_db)):
    plan = MembershipPlan(**body.model_dump())
    db.add(plan)
    await db.flush()
    return plan


@router.patch("/{plan_id}", response_model=MembershipPlanRead)
async def update_plan(plan_id: int, body: MembershipPlanUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(plan, field, value)
    await db.flush()
    return plan


@router.delete("/{plan_id}")
async def delete_plan(plan_id: int, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")
    await db.delete(plan)
    await db.flush()
    return {"detail": "Plan deleted"}


# ── Active members per plan ────────────────────────────


@router.get("/{plan_id}/members", response_model=list[PlanMember])
async def list_plan_members(plan_id: int, db: AsyncSession = Depends(get_db)):
    """List active members for a specific plan."""
    result = await db.execute(select(MembershipPlan).where(MembershipPlan.id == plan_id))
    plan = result.scalar_one_or_none()
    if not plan:
        raise HTTPException(404, "Plan not found")

    q = (
        select(Membership, User)
        .join(User, Membership.user_id == User.id)
        .where(
            Membership.membership_type == plan.access_type,
            (Membership.expiry_at.is_(None)) | (Membership.expiry_at > func.now()),
        )
        .order_by(Membership.start_at.desc())
    )
    rows = await db.execute(q)
    return [
        PlanMember(
            membership_id=m.id,
            user_id=u.id,
            telegram_id=u.telegram_id,
            username=u.username,
            membership_type=m.membership_type,
            start_at=m.start_at.isoformat() if m.start_at else "",
            expiry_at=m.expiry_at.isoformat() if m.expiry_at else None,
        )
        for m, u in rows.all()
    ]


class ExtendBody(BaseModel):
    days: int = 0
    hours: int = 0


@router.post("/members/{membership_id}/extend")
async def extend_membership(membership_id: int, body: ExtendBody, db: AsyncSession = Depends(get_db)):
    """Extend a membership's expiry by given days/hours."""
    from datetime import timedelta
    result = await db.execute(select(Membership).where(Membership.id == membership_id))
    mem = result.scalar_one_or_none()
    if not mem:
        raise HTTPException(404, "Membership not found")
    if mem.expiry_at is None:
        raise HTTPException(400, "Membership has no expiry (lifetime)")
    mem.expiry_at = mem.expiry_at + timedelta(days=body.days, hours=body.hours)
    await db.flush()
    return {"detail": "Membership extended", "new_expiry": mem.expiry_at.isoformat()}


@router.post("/members/{membership_id}/deactivate")
async def deactivate_membership(membership_id: int, db: AsyncSession = Depends(get_db)):
    """Deactivate a membership by setting expiry to now."""
    result = await db.execute(select(Membership).where(Membership.id == membership_id))
    mem = result.scalar_one_or_none()
    if not mem:
        raise HTTPException(404, "Membership not found")
    mem.expiry_at = datetime.now(timezone.utc)
    await db.flush()
    return {"detail": "Membership deactivated"}


@router.delete("/members/{membership_id}")
async def remove_membership(membership_id: int, db: AsyncSession = Depends(get_db)):
    """Permanently delete a membership record."""
    result = await db.execute(select(Membership).where(Membership.id == membership_id))
    mem = result.scalar_one_or_none()
    if not mem:
        raise HTTPException(404, "Membership not found")
    await db.delete(mem)
    await db.flush()
    return {"detail": "Membership removed"}
