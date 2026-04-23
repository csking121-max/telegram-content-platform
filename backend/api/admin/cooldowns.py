"""Admin endpoints for cooldown management."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.services.cooldown_service import CooldownService

router = APIRouter()


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
    additional_seconds: int,
    db: AsyncSession = Depends(get_db),
):
    """Extend an active cooldown by additional seconds."""
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
