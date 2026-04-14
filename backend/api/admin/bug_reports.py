"""
Admin bug reports — view and manage user-submitted bug reports.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.models.bug_report import BugReport

router = APIRouter()


@router.get("")
async def list_bug_reports(
    status: str = Query("", description="Filter by status: open, closed"),
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    """List bug reports, newest first."""
    q = select(BugReport).order_by(BugReport.created_at.desc())
    if status:
        q = q.where(BugReport.status == status)
    q = q.limit(limit).offset(offset)
    result = await db.execute(q)
    bugs = result.scalars().all()

    count_q = select(func.count(BugReport.id))
    if status:
        count_q = count_q.where(BugReport.status == status)
    total = (await db.execute(count_q)).scalar() or 0

    return {
        "total": total,
        "items": [
            {
                "id": b.id,
                "telegram_id": b.telegram_id,
                "username": b.username,
                "first_name": b.first_name,
                "report": b.report,
                "status": b.status,
                "created_at": b.created_at.isoformat() if b.created_at else None,
            }
            for b in bugs
        ],
    }


class UpdateBugStatus(BaseModel):
    status: str  # open / closed


@router.put("/{bug_id}")
async def update_bug_report(
    bug_id: int,
    body: UpdateBugStatus,
    db: AsyncSession = Depends(get_db),
):
    """Update bug report status."""
    result = await db.execute(
        update(BugReport).where(BugReport.id == bug_id).values(status=body.status)
    )
    if result.rowcount == 0:
        raise HTTPException(404, "Bug report not found")
    await db.commit()
    return {"detail": "Updated"}
