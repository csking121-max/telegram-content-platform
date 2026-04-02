#!/usr/bin/env python3
"""
Seed the database with sample data for development.

Usage:
    python -m scripts.seed_db
    # or from project root:
    python scripts/seed_db.py
"""
from __future__ import annotations

import asyncio
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

# Ensure project root on sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.database import AsyncSessionLocal, Base, async_engine  # noqa: E402
from backend.models import (  # noqa: E402
    Bot,
    ContentPack,
    Credit,
    Membership,
    PackItem,
    Payment,
    Referral,
    Token,
    User,
)
from backend.utils.token_generator import generate_token, generate_invite_code  # noqa: E402


async def seed():
    # Create tables if they don't exist
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSessionLocal() as db:
        print("🌱 Seeding database...")

        # ── Users ───────────────────────────────────────────
        users = [
            User(telegram_id=100000001, username="alice", level=1),
            User(telegram_id=100000002, username="bob", level=2),
            User(telegram_id=100000003, username="charlie", level=1),
            User(telegram_id=100000004, username="diana", level=0),
            User(telegram_id=100000005, username="eve", level=3),
        ]
        db.add_all(users)
        await db.flush()
        print(f"  ✓ Created {len(users)} users")

        # ── Bots ────────────────────────────────────────────
        bots = [
            Bot(bot_username="content_bot_1", bot_token="111:AAA-BBB", webhook_secret="secret_1", status="active"),
            Bot(bot_username="content_bot_2", bot_token="222:CCC-DDD", webhook_secret="secret_2", status="active"),
            Bot(bot_username="content_bot_3", bot_token="333:EEE-FFF", webhook_secret="secret_3", status="inactive"),
        ]
        db.add_all(bots)
        await db.flush()
        print(f"  ✓ Created {len(bots)} bots")

        # ── Content Packs ───────────────────────────────────
        packs = [
            ContentPack(title="Free Starter Pack", description="Welcome pack for new users", access_type="free", credit_cost=0, deletion_seconds=3600),
            ContentPack(title="Premium Video Course", description="10-part video tutorial", access_type="credits", credit_cost=50, deletion_seconds=7200),
            ContentPack(title="VIP Photo Collection", description="Exclusive photo set", access_type="vip", credit_cost=0, deletion_seconds=None),
            ContentPack(title="Daily Special", description="Limited daily access content", access_type="daily_pass", credit_cost=0, deletion_seconds=1800),
            ContentPack(title="Premium Music Pack", description="High quality audio files", access_type="premium", credit_cost=0, deletion_seconds=3600),
        ]
        db.add_all(packs)
        await db.flush()
        print(f"  ✓ Created {len(packs)} content packs")

        # ── Pack Items ──────────────────────────────────────
        media_types = ["photo", "video", "document", "audio"]
        item_count = 0
        for pack in packs:
            for i in range(5):
                item = PackItem(
                    pack_id=pack.id,
                    storage_chat_id=-1001234567890,
                    storage_message_id=1000 + pack.id * 10 + i,
                    media_type=media_types[i % len(media_types)],
                    order_index=i,
                )
                db.add(item)
                item_count += 1
        await db.flush()
        print(f"  ✓ Created {item_count} pack items")

        # ── Tokens ──────────────────────────────────────────
        now = datetime.now(timezone.utc)
        tokens = []
        for pack in packs:
            t = Token(
                token=generate_token(24),
                pack_id=pack.id,
                expires_at=now + timedelta(days=30),
                single_use=False,
                used_count=0,
            )
            db.add(t)
            tokens.append(t)
        # A single-use token
        single_t = Token(
            token=generate_token(24),
            pack_id=packs[1].id,
            expires_at=now + timedelta(hours=48),
            single_use=True,
            bound_user_id=users[0].id,
            used_count=0,
        )
        db.add(single_t)
        tokens.append(single_t)
        await db.flush()
        print(f"  ✓ Created {len(tokens)} tokens")

        # ── Credits ─────────────────────────────────────────
        credits = [
            Credit(user_id=users[0].id, balance=500),
            Credit(user_id=users[1].id, balance=200),
            Credit(user_id=users[2].id, balance=50),
            Credit(user_id=users[3].id, balance=0),
            Credit(user_id=users[4].id, balance=1000),
        ]
        db.add_all(credits)
        await db.flush()
        print(f"  ✓ Created {len(credits)} credit accounts")

        # ── Memberships ─────────────────────────────────────
        memberships = [
            Membership(user_id=users[0].id, membership_type="vip", expiry_at=now + timedelta(days=90)),
            Membership(user_id=users[1].id, membership_type="premium", expiry_at=now + timedelta(days=30)),
            Membership(user_id=users[4].id, membership_type="vip", expiry_at=None),  # Lifetime
            Membership(user_id=users[4].id, membership_type="premium", expiry_at=now + timedelta(days=365)),
        ]
        db.add_all(memberships)
        await db.flush()
        print(f"  ✓ Created {len(memberships)} memberships")

        # ── Payments ────────────────────────────────────────
        payments = [
            Payment(user_id=users[0].id, amount=49.99, method="stripe", reference="PAY-SEED-001", status="completed", completed_at=now - timedelta(days=5)),
            Payment(user_id=users[1].id, amount=19.99, method="crypto", reference="PAY-SEED-002", status="completed", completed_at=now - timedelta(days=2)),
            Payment(user_id=users[2].id, amount=9.99, method="stripe", reference="PAY-SEED-003", status="pending"),
        ]
        db.add_all(payments)
        await db.flush()
        print(f"  ✓ Created {len(payments)} payments")

        # ── Referrals ───────────────────────────────────────
        referrals = [
            Referral(invite_code=generate_invite_code(), referrer_user_id=users[0].id, used_by_user_id=users[2].id, reward_granted=True),
            Referral(invite_code=generate_invite_code(), referrer_user_id=users[0].id),  # Unused
            Referral(invite_code=generate_invite_code(), referrer_user_id=users[1].id, used_by_user_id=users[3].id, reward_granted=False),
        ]
        db.add_all(referrals)
        await db.flush()
        print(f"  ✓ Created {len(referrals)} referrals")

        await db.commit()
        print("\n✅ Database seeded successfully!")

        # Print useful info
        print("\n📋 Sample tokens for testing:")
        for t in tokens[:5]:
            pack_name = [p for p in packs if p.id == t.pack_id][0].title
            print(f"   {t.token}  →  {pack_name}")


if __name__ == "__main__":
    asyncio.run(seed())