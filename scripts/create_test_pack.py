#!/usr/bin/env python3
"""
Create a test content pack with sample items and print the token.

Usage:
    python scripts/create_test_pack.py [--title "My Pack"] [--items 5] [--type free]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import AsyncSessionLocal, Base, async_engine  # noqa: E402
from backend.engines.token_service import TokenService  # noqa: E402
from backend.models.content_pack import ContentPack  # noqa: E402
from backend.models.pack_item import PackItem  # noqa: E402


async def create_pack(title: str, num_items: int, access_type: str, credit_cost: int):
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        pack = ContentPack(
            title=title,
            description=f"Test pack: {title}",
            access_type=access_type,
            credit_cost=credit_cost,
            deletion_seconds=3600,
        )
        db.add(pack)
        await db.flush()

        media_types = ["photo", "video", "document", "audio"]
        for i in range(num_items):
            item = PackItem(
                pack_id=pack.id,
                storage_chat_id=-1001234567890,
                storage_message_id=5000 + i,
                media_type=media_types[i % len(media_types)],
                order_index=i,
            )
            db.add(item)
        await db.flush()

        ts = TokenService(db)
        token = await ts.create(pack.id, expires_in_hours=720)  # 30 days

        await db.commit()

        print(f"✅ Created content pack: '{title}'")
        print(f"   Pack ID:     {pack.id}")
        print(f"   Access type: {access_type}")
        print(f"   Credit cost: {credit_cost}")
        print(f"   Items:       {num_items}")
        print(f"   Token:       {token.token}")
        print(f"   Expires:     {token.expires_at}")
        print(f"\n   Deep link:   https://t.me/YOUR_BOT?start={token.token}")


def main():
    parser = argparse.ArgumentParser(description="Create a test content pack")
    parser.add_argument("--title", default="Test Pack", help="Pack title")
    parser.add_argument("--items", type=int, default=5, help="Number of items")
    parser.add_argument("--type", dest="access_type", default="free", choices=["free", "credits", "vip", "premium", "daily_pass"])
    parser.add_argument("--cost", type=int, default=0, help="Credit cost (for credits type)")
    args = parser.parse_args()

    asyncio.run(create_pack(args.title, args.items, args.access_type, args.cost))


if __name__ == "__main__":
    main()