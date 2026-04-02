"""
Admin Streak Manager — milestones CRUD, level CRUD, user streak overview.
"""
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.engines.streak_engine import StreakEngine
from backend.models.membership_plan import MembershipPlan

router = APIRouter()


# ── Schemas ──────────────────────────────────────────────

class MilestoneCreate(BaseModel):
    days_required: int
    bonus_credits: int
    label: str = ""
    is_active: bool = True


class MilestoneUpdate(BaseModel):
    days_required: int | None = None
    bonus_credits: int | None = None
    label: str | None = None
    is_active: bool | None = None


class LevelCreate(BaseModel):
    level: int
    streak_days_required: int
    bonus_credits: int = 0
    membership_plan_id: Optional[int] = None
    membership_duration_days: int = 0
    label: str = ""
    is_active: bool = True


class LevelUpdate(BaseModel):
    level: int | None = None
    streak_days_required: int | None = None
    bonus_credits: int | None = None
    membership_plan_id: Optional[int] = None
    membership_duration_days: int | None = None
    label: str | None = None
    is_active: bool | None = None


# ── Milestone endpoints ─────────────────────────────────

@router.get("/milestones")
async def list_milestones(db: AsyncSession = Depends(get_db)):
    """List all streak milestones ordered by days_required."""
    engine = StreakEngine(db)
    milestones = await engine.list_milestones()
    return [
        {
            "id": m.id,
            "days_required": m.days_required,
            "bonus_credits": m.bonus_credits,
            "label": m.label,
            "is_active": m.is_active,
        }
        for m in milestones
    ]


@router.post("/milestones")
async def create_milestone(body: MilestoneCreate, db: AsyncSession = Depends(get_db)):
    """Create a new streak milestone."""
    if body.days_required < 1:
        raise HTTPException(400, "days_required must be >= 1")
    if body.bonus_credits < 1:
        raise HTTPException(400, "bonus_credits must be >= 1")

    engine = StreakEngine(db)
    try:
        m = await engine.create_milestone(
            days_required=body.days_required,
            bonus_credits=body.bonus_credits,
            label=body.label,
            is_active=body.is_active,
        )
        await db.commit()
        return {
            "id": m.id,
            "days_required": m.days_required,
            "bonus_credits": m.bonus_credits,
            "label": m.label,
            "is_active": m.is_active,
        }
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            409, f"A milestone for {body.days_required} days already exists"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(400, str(e))


@router.patch("/milestones/{milestone_id}")
async def update_milestone(
    milestone_id: int, body: MilestoneUpdate, db: AsyncSession = Depends(get_db),
):
    """Update a streak milestone."""
    engine = StreakEngine(db)
    m = await engine.update_milestone(
        milestone_id,
        **body.model_dump(exclude_none=True),
    )
    if not m:
        raise HTTPException(404, "Milestone not found")
    await db.commit()
    return {
        "id": m.id,
        "days_required": m.days_required,
        "bonus_credits": m.bonus_credits,
        "label": m.label,
        "is_active": m.is_active,
    }


@router.delete("/milestones/{milestone_id}")
async def delete_milestone(milestone_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a streak milestone."""
    engine = StreakEngine(db)
    deleted = await engine.delete_milestone(milestone_id)
    if not deleted:
        raise HTTPException(404, "Milestone not found")
    await db.commit()
    return {"detail": "Milestone deleted"}


# ── User streak endpoints ────────────────────────────────

@router.get("/users")
async def list_user_streaks(
    skip: int = 0, limit: int = 50, db: AsyncSession = Depends(get_db),
):
    """List all user streaks (admin overview)."""
    engine = StreakEngine(db)
    return await engine.get_all_streaks(skip=skip, limit=limit)


@router.get("/users/{user_id}")
async def get_user_streak(user_id: int, db: AsyncSession = Depends(get_db)):
    """Get streak details for a specific user."""
    engine = StreakEngine(db)
    return await engine.get_user_streak(user_id)


@router.post("/users/{user_id}/reset")
async def reset_user_streak(user_id: int, db: AsyncSession = Depends(get_db)):
    """Reset a user's streak to 0."""
    engine = StreakEngine(db)
    await engine.reset_user_streak(user_id)
    await db.commit()
    return {"detail": f"Streak reset for user {user_id}"}


# ── Level endpoints ──────────────────────────────────────

@router.get("/levels")
async def list_levels(db: AsyncSession = Depends(get_db)):
    """List all streak levels ordered by level number."""
    engine = StreakEngine(db)
    levels = await engine.list_levels()
    return [
        {
            "id": lv.id,
            "level": lv.level,
            "streak_days_required": lv.streak_days_required,
            "bonus_credits": lv.bonus_credits,
            "membership_plan_id": lv.membership_plan_id,
            "membership_duration_days": lv.membership_duration_days,
            "label": lv.label,
            "is_active": lv.is_active,
        }
        for lv in levels
    ]


@router.post("/levels")
async def create_level(body: LevelCreate, db: AsyncSession = Depends(get_db)):
    """Create a new streak level."""
    if body.level < 1:
        raise HTTPException(400, "level must be >= 1")
    if body.streak_days_required < 1:
        raise HTTPException(400, "streak_days_required must be >= 1")

    engine = StreakEngine(db)
    try:
        lv = await engine.create_level(
            level=body.level,
            streak_days_required=body.streak_days_required,
            bonus_credits=body.bonus_credits,
            membership_plan_id=body.membership_plan_id,
            membership_duration_days=body.membership_duration_days,
            label=body.label,
            is_active=body.is_active,
        )
        await db.commit()
        return {
            "id": lv.id,
            "level": lv.level,
            "streak_days_required": lv.streak_days_required,
            "bonus_credits": lv.bonus_credits,
            "membership_plan_id": lv.membership_plan_id,
            "membership_duration_days": lv.membership_duration_days,
            "label": lv.label,
            "is_active": lv.is_active,
        }
    except IntegrityError:
        await db.rollback()
        raise HTTPException(
            409, f"Level {body.level} or streak_days {body.streak_days_required} already exists"
        )
    except Exception as e:
        await db.rollback()
        raise HTTPException(400, str(e))


@router.patch("/levels/{level_id}")
async def update_level(
    level_id: int, body: LevelUpdate, db: AsyncSession = Depends(get_db),
):
    """Update a streak level."""
    engine = StreakEngine(db)
    lv = await engine.update_level(
        level_id,
        **body.model_dump(exclude_none=True),
    )
    if not lv:
        raise HTTPException(404, "Level not found")
    await db.commit()
    return {
        "id": lv.id,
        "level": lv.level,
        "streak_days_required": lv.streak_days_required,
        "bonus_credits": lv.bonus_credits,
        "membership_plan_id": lv.membership_plan_id,
        "membership_duration_days": lv.membership_duration_days,
        "label": lv.label,
        "is_active": lv.is_active,
    }


@router.delete("/levels/{level_id}")
async def delete_level(level_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a streak level."""
    engine = StreakEngine(db)
    deleted = await engine.delete_level(level_id)
    if not deleted:
        raise HTTPException(404, "Level not found")
    await db.commit()
    return {"detail": "Level deleted"}


# ── Membership plans helper (for level reward dropdown) ──

@router.get("/membership-plans")
async def list_membership_plans(db: AsyncSession = Depends(get_db)):
    """List active membership plans for use in level reward configuration."""
    result = await db.execute(
        select(MembershipPlan)
        .where(MembershipPlan.is_active == True)
        .order_by(MembershipPlan.sort_order)
    )
    plans = result.scalars().all()
    return [
        {
            "id": p.id,
            "name": p.name,
            "display_name": p.display_name,
            "access_type": p.access_type,
            "duration_days": p.duration_days,
        }
        for p in plans
    ]
