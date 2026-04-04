import asyncio
from backend.database import AsyncSessionLocal
from backend.services.platform_settings_service import PlatformSettingsService

async def seed():
    async with AsyncSessionLocal() as db:
        svc = PlatformSettingsService(db)
        count = await svc.seed_defaults()
        await db.commit()
        print(f"Seeded {count} new settings")

asyncio.run(seed())
