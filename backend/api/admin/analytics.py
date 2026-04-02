"""Admin analytics endpoints."""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from backend.dependencies import get_db
from backend.models.user import User
from backend.models.bot import Bot
from backend.models.content_pack import ContentPack
from backend.models.credit import Credit
from backend.models.membership import Membership
from backend.models.delivered_message import DeliveredMessage
from backend.models.payment import Payment
from backend.models.activity_log import ActivityLog
from backend.services.activity_logger import ActivityLogger

router = APIRouter()


@router.get("/summary")
async def dashboard_summary(db: AsyncSession = Depends(get_db)):
    """Aggregate counts for the admin dashboard."""
    async def _count(model):
        r = await db.execute(select(func.count()).select_from(model))
        return r.scalar() or 0

    return {
        "total_users": await _count(User),
        "total_bots": await _count(Bot),
        "total_packs": await _count(ContentPack),
        "total_deliveries": await _count(DeliveredMessage),
        "total_payments": await _count(Payment),
    }


@router.get("/activity")
async def recent_activity(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    logger = ActivityLogger(db)
    logs = await logger.get_recent(limit=limit)
    return logs


@router.get("/activity/user/{user_id}")
async def user_activity(
    user_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
):
    al = ActivityLogger(db)
    logs = await al.get_user_activity(user_id, limit=limit, offset=skip)
    return logs


@router.get("/revenue")
async def revenue_summary(db: AsyncSession = Depends(get_db)):
    """Simple revenue aggregation."""
    result = await db.execute(
        select(
            func.count(Payment.id).label("count"),
            func.coalesce(func.sum(Payment.amount), 0).label("total"),
        ).where(Payment.status == "completed")
    )
    row = result.one()
    return {
        "completed_payments": row.count,
        "total_revenue": float(row.total),
    }