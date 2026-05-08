"""
Webhook endpoint – receives forwarded events from Telegram bots.

Flow:
  1. Look up bot in database and validate HMAC signature.
  2. Parse payload → identify user + bot + action.
  3. Dispatch to the appropriate engine / service.
"""

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.config import settings
from backend.dependencies import get_db
from backend.schemas.webhook import BotWebhookPayload
from backend.security.hmac_validation import validate_hmac
from backend.services.user_service import UserService
from backend.services.bot_service import BotService
from backend.services.activity_logger import ActivityLogger
from backend.services.cooldown_service import CooldownService
from backend.services.platform_settings_service import PlatformSettingsService
from backend.engines.access_control import AccessControlEngine
from backend.engines.delivery_engine import DeliveryEngine

logger = logging.getLogger(__name__)
router = APIRouter()


async def _get_bot_secret(bot_username: str, db: AsyncSession) -> str | None:
    """Look up HMAC secret from the database first, then fall back to env var."""
    # 1. Try DB
    svc = BotService(db)
    bot = await svc.get_by_username(bot_username)
    if bot and bot.webhook_secret:
        return bot.webhook_secret

    # 2. Fallback to env var config
    for entry in settings.telegram_bots:
        if entry["username"] == bot_username:
            return entry["hmac_secret"]
    return None


@router.post("/{bot_username}")
async def receive_webhook(
    bot_username: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    # ── 1. HMAC validation ──────────────────────────────────────
    secret = await _get_bot_secret(bot_username, db)
    if not secret:
        logger.warning("Webhook received for unknown bot: %s", bot_username)
        raise HTTPException(status_code=404, detail="Bot not registered")

    body = await request.body()
    signature = request.headers.get("X-Signature", "")
    if not signature or not validate_hmac(secret, body, signature):
        raise HTTPException(status_code=401, detail="Invalid signature")

    # ── 2. Parse payload ────────────────────────────────────────
    try:
        payload = BotWebhookPayload.model_validate_json(body)
    except Exception:
        raise HTTPException(status_code=422, detail="Malformed payload")

    # ── 3. Ensure user + bot exist ──────────────────────────────
    user_svc = UserService(db)
    user, _created = await user_svc.get_or_create(
        telegram_id=payload.telegram_id,
        username=payload.username,
    )

    bot_svc = BotService(db)
    bot = await bot_svc.get_by_username(bot_username)
    if not bot:
        raise HTTPException(status_code=404, detail="Bot not found in database")

    activity = ActivityLogger(db)

    # ── 4. Dispatch by action ───────────────────────────────────
    action = payload.action

    if action == "register_user":
        # Just ensure user exists — already done in step 3
        await db.commit()
        return {"ok": True, "user_id": user.id}

    if action == "access_check":
        cooldown_svc = CooldownService(db)
        active_cooldown = await cooldown_svc.get_cooldown_for_user(user.id)
        if active_cooldown:
            remaining = int(
                (active_cooldown.cooldown_until - datetime.now(timezone.utc)).total_seconds()
            )
            remaining_seconds = max(remaining, 0)
            reason = f"User is in cooldown. Remaining time: {remaining_seconds} seconds"
            await activity.log(
                user_id=user.id,
                action="access_check",
                payload={
                    "token": payload.token,
                    "allowed": False,
                    "reason": "cooldown_active",
                    "remaining_seconds": remaining_seconds,
                },
            )
            await db.commit()
            return {
                "allowed": False,
                "reason": reason,
                "reason_code": "cooldown_active",
                "remaining_seconds": remaining_seconds,
            }

        engine = AccessControlEngine(db)
        result = await engine.check(
            telegram_id=payload.telegram_id,
            token_str=payload.token or "",
        )

        if result.allowed:
            settings_svc = PlatformSettingsService(db)
            cooldown_links_limit = await settings_svc.get_int("cooldown_links_limit", 5)
            cooldown_seconds = await settings_svc.get_int("cooldown_seconds", 3600)
            access_count, should_cooldown = await cooldown_svc.increment_access_count(
                user.id,
                cooldown_links_limit,
                cooldown_seconds,
            )
            if should_cooldown:
                await cooldown_svc.apply_cooldown(
                    user_id=user.id,
                    cooldown_seconds=cooldown_seconds,
                    access_count=access_count,
                    cooldown_links_limit=cooldown_links_limit,
                )
                reason = (
                    f"Link access limit ({cooldown_links_limit}) exceeded. "
                    f"Cooldown applied for {cooldown_seconds} seconds."
                )
                await activity.log(
                    user_id=user.id,
                    action="access_check",
                    payload={
                        "token": payload.token,
                        "allowed": False,
                        "reason": "cooldown_applied",
                        "access_count": access_count,
                    },
                )
                await db.commit()
                return {
                    "allowed": False,
                    "reason": reason,
                    "reason_code": "cooldown_applied",
                    "cooldown_seconds": cooldown_seconds,
                    "remaining_seconds": cooldown_seconds,
                }

        await activity.log(
            user_id=user.id,
            action="access_check",
            payload={"token": payload.token, "allowed": result.allowed},
        )
        await db.commit()
        return result.model_dump()

    if action == "request_delivery":
        delivery = DeliveryEngine(db)
        result = await delivery.enqueue_delivery(
            user_id=user.id,
            telegram_id=payload.telegram_id,
            pack_id=payload.pack_id or 0,
            bot_username=bot_username,
        )
        await activity.log(
            user_id=user.id,
            action="request_delivery",
            payload={"pack_id": payload.pack_id},
        )
        await db.commit()
        return result

    # Unknown action – log and return 400
    await activity.log(
        user_id=user.id,
        action="unknown",
        payload={"raw_action": action},
    )
    await db.commit()
    raise HTTPException(status_code=400, detail=f"Unknown action: {action}")
