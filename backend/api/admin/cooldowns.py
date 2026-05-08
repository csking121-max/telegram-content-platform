"""Admin endpoints for cooldown management."""

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.services.cooldown_service import CooldownService

router = APIRouter()


class ExtendCooldownBody(BaseModel):
    additional_seconds: int


@router.get("")
async def list_active_cooldowns(db: AsyncSession = Depends(get_db)):
    """Get all currently active cooldowns with user info and remaining time."""
    svc = CooldownService(db)
    cooldowns = await svc.get_all_active_cooldowns()
    return {"cooldowns": cooldowns, "total": len(cooldowns)}


@router.delete("/{cooldown_id}")
async def remove_cooldown(cooldown_id: int, db: AsyncSession = Depends(get_db)):
    """Remove/clear a cooldown by ID."""
    svc = CooldownService(db)
    deleted = await svc.remove_cooldown(cooldown_id)
    if not deleted:
        raise HTTPException(404, "Cooldown not found")
    await db.commit()
    return {"detail": f"Cooldown {cooldown_id} removed"}


@router.post("/{cooldown_id}/extend")
async def extend_cooldown(
    cooldown_id: int,
    body: ExtendCooldownBody | None = None,
    additional_seconds: int | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
):
    """Extend an active cooldown by additional seconds."""
    additional_seconds = body.additional_seconds if body is not None else additional_seconds
    if additional_seconds is None:
        raise HTTPException(400, "additional_seconds is required")
    if additional_seconds <= 0:
        raise HTTPException(400, "additional_seconds must be positive")
    
    svc = CooldownService(db)
    cooldown = await svc.extend_cooldown(cooldown_id, additional_seconds)
    if not cooldown:
        raise HTTPException(404, "Cooldown not found")
    
    await db.commit()
    return {
        "detail": f"Cooldown extended by {additional_seconds} seconds",
        "cooldown_until": cooldown.cooldown_until.isoformat(),
    }


@router.post("/clear-expired")
async def clear_expired_cooldowns(db: AsyncSession = Depends(get_db)):
    """Delete all expired cooldowns. Returns count deleted."""
    svc = CooldownService(db)
    count = await svc.clear_expired_cooldowns()
    await db.commit()
    return {"detail": f"Cleared {count} expired cooldowns"}
