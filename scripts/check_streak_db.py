"""Quick script to check streak state in database."""
import asyncio
import sys
sys.path.insert(0, ".")
from backend.database import AsyncSessionLocal
from backend.services.platform_settings_service import PlatformSettingsService
from backend.models.user_streak import UserStreak
from sqlalchemy import select

async def check():
    async with AsyncSessionLocal() as db:
        svc = PlatformSettingsService(db)
        enabled = await svc.get("streak_enabled", "NOT_SET")
        min_spend = await svc.get("streak_min_daily_spend", "NOT_SET")
        print(f"streak_enabled={enabled}")
        print(f"streak_min_daily_spend={min_spend}")

        result = await db.execute(select(UserStreak))
        streaks = result.scalars().all()
        if not streaks:
            print("NO STREAK RECORDS FOUND")
        for s in streaks:
            print(f"user={s.user_id} streak={s.current_streak} today_spent={s.today_spent} last_date={s.last_streak_date} longest={s.longest_streak}")

asyncio.run(check())
