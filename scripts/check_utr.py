"""Check DB state for UTR 418100516078"""
import asyncio, sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from backend.database import AsyncSessionLocal as async_session

async def main():
    async with async_session() as db:
        r = await db.execute(text(
            "SELECT id, order_ref, user_id, amount, status, utr_submitted, created_at "
            "FROM payment_orders ORDER BY id DESC"
        ))
        rows = r.fetchall()
        print("Matching orders:")
        for row in rows:
            print(f"  #{row[0]} ref={row[1]} user={row[2]} amt={row[3]} status={row[4]} utr={row[5]} at={row[6]}")

        r2 = await db.execute(text(
            "SELECT id, sender, body, utr_extracted, matched, source_chat_id FROM sms_logs ORDER BY id DESC LIMIT 10"
        ))
        rows2 = r2.fetchall()
        print("\nRecent SMS logs:")
        for row in rows2:
            print(f"  #{row[0]} sender={row[1]} utr={row[3]} matched={row[4]} src_chat={row[5]} body={row[2][:60]}")

asyncio.run(main())
