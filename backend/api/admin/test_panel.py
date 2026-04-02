"""
Admin Test Panel — endpoints to verify platform components are working.
"""
from __future__ import annotations

import logging
import re
import time
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.dependencies import get_db
from backend.services.platform_settings_service import PlatformSettingsService

logger = logging.getLogger(__name__)
router = APIRouter()


class TestResult(BaseModel):
    name: str
    success: bool
    message: str
    details: dict[str, Any] | None = None
    duration_ms: float | None = None


class UtrTestInput(BaseModel):
    sample_text: str


# ── Helper: UTR extraction regex (same as sms_verification_service) ──

UTR_PATTERNS = [
    re.compile(r"\b(\d{12})\b"),                # 12-digit UPI UTR
    re.compile(r"\b(\d{16})\b"),                 # 16-digit NEFT/RTGS
    re.compile(r"\b([A-Z]{4}\d{13})\b"),         # Bank ref e.g. HDFC0001234567890
    re.compile(r"UTR[:\s#]*([A-Za-z0-9]+)", re.I),
    re.compile(r"Ref[:\s#]*([A-Za-z0-9]{10,})", re.I),
    re.compile(r"UPI[:\s/]*([A-Za-z0-9]{12,})", re.I),
]


# ── 1. API Ping ─────────────────────────────────────────────

@router.post("/ping", response_model=TestResult)
async def test_ping():
    """Simple API health check."""
    return TestResult(
        name="API Ping",
        success=True,
        message="Backend API is running and reachable.",
        details={"timestamp": time.time()},
    )


# ── 2. Database connectivity ────────────────────────────────

@router.post("/database", response_model=TestResult)
async def test_database(db: AsyncSession = Depends(get_db)):
    """Check database connectivity and table existence."""
    start = time.time()
    try:
        # Test basic query
        result = await db.execute(text("SELECT 1"))
        result.scalar()

        # Check key tables exist
        tables_to_check = [
            "users", "bots", "content_packs", "tokens",
            "membership_plans", "upi_configs", "payment_orders",
            "platform_settings", "sms_logs",
        ]
        existing = []
        missing = []

        _ALLOWED_TABLES = set(tables_to_check)
        for table in tables_to_check:
            if table not in _ALLOWED_TABLES:
                continue
            try:
                await db.execute(text(f"SELECT COUNT(*) FROM {table}"))
                existing.append(table)
            except Exception:
                missing.append(table)
                await db.rollback()

        elapsed = (time.time() - start) * 1000
        success = len(missing) == 0
        return TestResult(
            name="Database",
            success=success,
            message=f"{'All' if success else 'Some'} tables accessible. {len(existing)}/{len(tables_to_check)} found.",
            details={"existing_tables": existing, "missing_tables": missing},
            duration_ms=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return TestResult(
            name="Database",
            success=False,
            message=f"Database connection failed: {str(e)}",
            duration_ms=round(elapsed, 2),
        )


# ── 3. Platform Settings ───────────────────────────────────

@router.post("/settings", response_model=TestResult)
async def test_settings(db: AsyncSession = Depends(get_db)):
    """Check if platform settings are accessible and seed defaults."""
    start = time.time()
    try:
        svc = PlatformSettingsService(db)
        seeded = await svc.seed_defaults()
        await db.commit()

        all_settings = await svc.get_all()
        count = len(all_settings)

        # Check important settings have values
        critical_keys = ["utr_group_chat_id", "platform_name", "payment_expiry_minutes"]
        warnings = []
        for key in critical_keys:
            val = await svc.get(key)
            if not val:
                warnings.append(f"'{key}' is empty - please configure it")

        elapsed = (time.time() - start) * 1000
        return TestResult(
            name="Platform Settings",
            success=True,
            message=f"{count} settings loaded. {seeded} new defaults seeded." + (
                f" ⚠️ {len(warnings)} warnings." if warnings else ""
            ),
            details={"total_settings": count, "newly_seeded": seeded, "warnings": warnings},
            duration_ms=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return TestResult(
            name="Platform Settings",
            success=False,
            message=f"Settings check failed: {str(e)}",
            duration_ms=round(elapsed, 2),
        )


# ── 4. UTR Extraction Test ─────────────────────────────────

@router.post("/utr-extract", response_model=TestResult)
async def test_utr_extraction(body: UtrTestInput):
    """Test UTR extraction from sample text."""
    start = time.time()
    text_to_check = body.sample_text
    found_utrs: list[str] = []

    for pattern in UTR_PATTERNS:
        matches = pattern.findall(text_to_check)
        found_utrs.extend(matches)

    # Deduplicate
    found_utrs = list(dict.fromkeys(found_utrs))

    # Also try to extract amount
    amount = None
    amt_match = re.search(r"Rs\.?\s*([\d,]+\.?\d*)", text_to_check, re.I)
    if not amt_match:
        amt_match = re.search(r"INR\s*([\d,]+\.?\d*)", text_to_check, re.I)
    if amt_match:
        amount = amt_match.group(1).replace(",", "")

    elapsed = (time.time() - start) * 1000
    return TestResult(
        name="UTR Extraction",
        success=len(found_utrs) > 0,
        message=f"Found {len(found_utrs)} UTR(s)" + (f" and amount ₹{amount}" if amount else "") + (
            "." if found_utrs else ". No UTR found — check format."
        ),
        details={"utrs_found": found_utrs, "amount_extracted": amount, "input_text": text_to_check[:200]},
        duration_ms=round(elapsed, 2),
    )


# ── 5. Telegram Bot Status ─────────────────────────────────

@router.post("/bot-status", response_model=TestResult)
async def test_bot_status(db: AsyncSession = Depends(get_db)):
    """Check if any configured bots are reachable via Telegram API."""
    import httpx
    from sqlalchemy import select
    from backend.models.bot import Bot

    start = time.time()
    try:
        result = await db.execute(select(Bot).limit(5))
        bots = list(result.scalars().all())

        if not bots:
            elapsed = (time.time() - start) * 1000
            return TestResult(
                name="Telegram Bot",
                success=False,
                message="No bots configured. Add a bot in the Bots section first.",
                duration_ms=round(elapsed, 2),
            )

        bot_results = []
        any_success = False

        async with httpx.AsyncClient(timeout=10) as client:
            for bot in bots:
                try:
                    resp = await client.get(f"https://api.telegram.org/bot{bot.bot_token}/getMe")
                    data = resp.json()
                    if data.get("ok"):
                        bot_info = data["result"]
                        bot_results.append({
                            "username": bot.bot_username,
                            "status": "✅ Online",
                            "bot_name": bot_info.get("first_name", ""),
                            "can_join_groups": bot_info.get("can_join_groups", False),
                        })
                        any_success = True
                    else:
                        bot_results.append({
                            "username": bot.bot_username,
                            "status": "❌ Invalid token",
                            "error": data.get("description", "Unknown error"),
                        })
                except Exception as e:
                    bot_results.append({
                        "username": bot.bot_username,
                        "status": "❌ Connection failed",
                        "error": str(e),
                    })

        elapsed = (time.time() - start) * 1000
        return TestResult(
            name="Telegram Bot",
            success=any_success,
            message=f"Checked {len(bots)} bot(s). {'At least one is online.' if any_success else 'None reachable.'}",
            details={"bots": bot_results},
            duration_ms=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return TestResult(
            name="Telegram Bot",
            success=False,
            message=f"Bot check failed: {str(e)}",
            duration_ms=round(elapsed, 2),
        )


# ── 6. UTR Group Check ─────────────────────────────────────

@router.post("/utr-group", response_model=TestResult)
async def test_utr_group(db: AsyncSession = Depends(get_db)):
    """Check if the UTR verification group is configured and accessible."""
    import httpx
    from sqlalchemy import select
    from backend.models.bot import Bot

    start = time.time()
    try:
        svc = PlatformSettingsService(db)
        group_id = await svc.get("utr_group_chat_id")

        if not group_id:
            elapsed = (time.time() - start) * 1000
            return TestResult(
                name="UTR Group",
                success=False,
                message="UTR group chat ID is not configured. Set it in Settings → Telegram.",
                duration_ms=round(elapsed, 2),
            )

        # Try to get chat info using the first available bot
        result = await db.execute(select(Bot).limit(1))
        bot = result.scalar_one_or_none()
        if not bot:
            elapsed = (time.time() - start) * 1000
            return TestResult(
                name="UTR Group",
                success=False,
                message=f"Group ID configured ({group_id}) but no bot available to verify access.",
                duration_ms=round(elapsed, 2),
            )

        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(
                f"https://api.telegram.org/bot{bot.bot_token}/getChat",
                params={"chat_id": group_id},
            )
            data = resp.json()

        if data.get("ok"):
            chat = data["result"]
            elapsed = (time.time() - start) * 1000
            return TestResult(
                name="UTR Group",
                success=True,
                message=f"UTR group accessible: \"{chat.get('title', 'Unknown')}\"",
                details={
                    "chat_id": group_id,
                    "title": chat.get("title"),
                    "type": chat.get("type"),
                    "members_count": chat.get("members_count"),
                },
                duration_ms=round(elapsed, 2),
            )
        else:
            elapsed = (time.time() - start) * 1000
            return TestResult(
                name="UTR Group",
                success=False,
                message=f"Cannot access group ({group_id}): {data.get('description', 'Unknown error')}. Make sure the bot is added to the group.",
                details={"chat_id": group_id, "telegram_error": data.get("description")},
                duration_ms=round(elapsed, 2),
            )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return TestResult(
            name="UTR Group",
            success=False,
            message=f"UTR group check failed: {str(e)}",
            duration_ms=round(elapsed, 2),
        )


# ── 7. UPI Config Check ────────────────────────────────────

@router.post("/upi-config", response_model=TestResult)
async def test_upi_config(db: AsyncSession = Depends(get_db)):
    """Check if UPI is configured with at least one active UPI ID."""
    from sqlalchemy import select
    from backend.models.upi_config import UpiConfig

    start = time.time()
    try:
        result = await db.execute(select(UpiConfig))
        configs = list(result.scalars().all())

        active = [c for c in configs if c.is_active]

        elapsed = (time.time() - start) * 1000
        if not configs:
            return TestResult(
                name="UPI Config",
                success=False,
                message="No UPI IDs configured. Add one in UPI Settings.",
                duration_ms=round(elapsed, 2),
            )

        if not active:
            return TestResult(
                name="UPI Config",
                success=False,
                message=f"{len(configs)} UPI ID(s) found but none is marked active.",
                details={"total": len(configs), "active": 0},
                duration_ms=round(elapsed, 2),
            )

        return TestResult(
            name="UPI Config",
            success=True,
            message=f"Active UPI: {active[0].upi_id} ({active[0].payee_name})",
            details={
                "total": len(configs),
                "active_id": active[0].upi_id,
                "active_name": active[0].payee_name,
            },
            duration_ms=round(elapsed, 2),
        )
    except Exception as e:
        elapsed = (time.time() - start) * 1000
        return TestResult(
            name="UPI Config",
            success=False,
            message=f"UPI config check failed: {str(e)}",
            duration_ms=round(elapsed, 2),
        )


# ── Run All Tests ───────────────────────────────────────────

@router.post("/run-all", response_model=list[TestResult])
async def run_all_tests(db: AsyncSession = Depends(get_db)):
    """Run all diagnostic tests and return combined results."""
    results: list[TestResult] = []

    # 1. Ping
    results.append(await test_ping())

    # 2. Database
    results.append(await test_database(db))

    # 3. Settings
    results.append(await test_settings(db))

    # 4. UPI Config
    results.append(await test_upi_config(db))

    # 5. Bot Status
    results.append(await test_bot_status(db))

    # 6. UTR Group
    results.append(await test_utr_group(db))

    return results
