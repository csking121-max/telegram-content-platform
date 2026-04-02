"""Admin endpoints for platform settings — configurable key/value store."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.schemas.platform_setting import (
    PlatformSettingBulkUpdate,
    PlatformSettingCreate,
    PlatformSettingRead,
    PlatformSettingUpdate,
)
from backend.services.platform_settings_service import PlatformSettingsService

router = APIRouter()


@router.get("", response_model=list[PlatformSettingRead])
async def list_settings(category: str = None, db: AsyncSession = Depends(get_db)):
    """List all platform settings, optionally filtered by category."""
    svc = PlatformSettingsService(db)
    # Auto-seed defaults on first access
    await svc.seed_defaults()
    await db.commit()
    return await svc.get_all(category=category)


@router.post("", response_model=PlatformSettingRead)
async def create_setting(body: PlatformSettingCreate, db: AsyncSession = Depends(get_db)):
    """Create a new custom setting."""
    svc = PlatformSettingsService(db)
    # Check if key already exists
    existing = await svc.get(body.key)
    if existing:
        raise HTTPException(400, f"Setting '{body.key}' already exists. Use PUT to update.")
    from backend.models.platform_setting import PlatformSetting
    setting = PlatformSetting(
        key=body.key,
        value=body.value,
        description=body.description,
        category=body.category,
    )
    db.add(setting)
    await db.commit()
    await db.refresh(setting)
    return setting


@router.put("/{key}", response_model=PlatformSettingRead)
async def update_setting(key: str, body: PlatformSettingUpdate, db: AsyncSession = Depends(get_db)):
    """Update a single setting by key."""
    svc = PlatformSettingsService(db)
    setting = await svc.set(key, body.value)
    await db.commit()
    await db.refresh(setting)
    return setting


@router.post("/bulk", response_model=dict)
async def bulk_update_settings(body: PlatformSettingBulkUpdate, db: AsyncSession = Depends(get_db)):
    """Update multiple settings at once."""
    svc = PlatformSettingsService(db)
    count = await svc.bulk_update(body.settings)
    await db.commit()
    return {"updated": count}


@router.delete("/{key}")
async def delete_setting(key: str, db: AsyncSession = Depends(get_db)):
    """Delete a custom setting."""
    svc = PlatformSettingsService(db)
    deleted = await svc.delete(key)
    if not deleted:
        raise HTTPException(404, "Setting not found")
    await db.commit()
    return {"detail": "Deleted"}
