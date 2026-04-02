#!/usr/bin/env python3
"""
Create a test token for an existing content pack.

Usage:
    python scripts/create_test_token.py <pack_id> [--single-use] [--hours 24] [--user-id 1]
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import AsyncSessionLocal, Base, async_engine  # noqa: E402
from backend.engines.token_service import TokenService  # noqa: E402


async def create_token(pack_id: int, single_use: bool, hours: int, user_id: int | None):
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        ts = TokenService(db)

        token = await ts.create(
            pack_id=pack_id,
            expires_in_hours=hours,
            single_use=single_use,
            bound_user_id=user_id,
        )
        await db.commit()

        print(f"✅ Token created successfully!")
        print(f"   Token:       {token.token}")
        print(f"   Pack ID:     {token.pack_id}")
        print(f"   Single use:  {token.single_use}")
        print(f"   Bound user:  {token.bound_user_id or 'None (open)'}")
        print(f"   Expires at:  {token.expires_at}")
        print(f"\n   Deep link:   https://t.me/YOUR_BOT?start={token.token}")


def main():
    parser = argparse.ArgumentParser(description="Create a test access token")
    parser.add_argument("pack_id", type=int, help="Content pack ID")
    parser.add_argument("--single-use", action="store_true", help="Make token single-use")
    parser.add_argument("--hours", type=int, default=24, help="Token validity in hours")
    parser.add_argument("--user-id", type=int, default=None, help="Bind to specific user ID")
    args = parser.parse_args()

    asyncio.run(create_token(args.pack_id, args.single_use, args.hours, args.user_id))


if __name__ == "__main__":
    main()