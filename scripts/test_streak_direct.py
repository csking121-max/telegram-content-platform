"""Test streak recording via credit deduction."""
import asyncio
import sys
sys.path.insert(0, ".")

async def main():
    from backend.database import AsyncSessionLocal
    from backend.engines.credit_engine import CreditEngine
    from backend.engines.streak_engine import StreakEngine
    
    async with AsyncSessionLocal() as db:
        # Check streak directly for user_id=2
        se = StreakEngine(db)
        info = await se.get_user_streak(2)
        print("User 2 streak BEFORE:", info)
        
        # Try record_spend directly
        try:
            result = await se.record_spend(2, 10)
            print("record_spend result:", result)
        except Exception as e:
            print("record_spend ERROR:", type(e).__name__, e)
        
        await db.commit()
        
        # Check again
        info2 = await se.get_user_streak(2)
        print("User 2 streak AFTER:", info2)

asyncio.run(main())
