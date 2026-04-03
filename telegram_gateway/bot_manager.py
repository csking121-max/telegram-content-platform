"""
Multi-bot manager using **aiogram 3.x**.

Fetches active bots from the backend database via the internal API,
then starts aiogram long-polling for each. Falls back to TELEGRAM_BOTS
env var if the backend is unreachable.

Scaling design (handles 10–15+ bots with no code changes):
  - Single shared Dispatcher for all bots — aiogram's documented multi-bot
    pattern; no per-bot overhead, no router duplication.
  - BotConfigMiddleware resolves per-bot config at request-time via bot.id.
  - All bot tokens are validated in parallel on startup, so adding more bots
    does not increase startup time linearly.
  - A background watcher checks the backend every BOT_CONFIG_CHECK_INTERVAL
    seconds (default 60). When the bot list changes the process replaces
    itself via os.execv so the new configuration is picked up without any
    manual restart, and all module-level singleton state (aiogram Router
    parent links etc.) is cleanly reset.

Environment variables:
  BOT_CONFIG_CHECK_INTERVAL  seconds between config-change checks (default 60)
  BOT_RESTART_DELAY          seconds to wait before exec-restart (default 3)
  LOG_LEVEL                  logging level (default INFO)
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys

import httpx
from aiogram import Bot, Dispatcher
from dotenv import load_dotenv

from .handlers.start import start_router
from .handlers.payment import payment_router
from .handlers.utr_group import utr_group_router
from .handlers.upload import upload_router
from .handlers.fallback import fallback_router
from .middleware.forwarding import BotConfigMiddleware, RequestLoggingMiddleware
from .message_tracker import MessageTrackingMiddleware, start_flush_task
from .http_client import BACKEND_URL

# Maps bot_id (int) → {username, hmac_secret}.  Populated by run_bots().
_BOT_CONFIGS: dict[int, dict[str, str]] = {}


class TrackingBot(Bot):
    """Bot subclass that auto-tracks every outgoing private-chat message for cleanup."""

    async def _auto_track(self, chat_id: int | str, message_id: int) -> None:
        if not isinstance(chat_id, int) or chat_id <= 0:
            return
        cfg = _BOT_CONFIGS.get(self.id, {})
        db_id = cfg.get("db_id", 0)
        if db_id:
            from .message_tracker import track
            await track(db_id, chat_id, message_id, "out")

    async def send_message(self, chat_id, *args, **kwargs):
        msg = await super().send_message(chat_id, *args, **kwargs)
        await self._auto_track(chat_id, msg.message_id)
        return msg

    async def send_photo(self, chat_id, *args, **kwargs):
        msg = await super().send_photo(chat_id, *args, **kwargs)
        await self._auto_track(chat_id, msg.message_id)
        return msg

    async def send_video(self, chat_id, *args, **kwargs):
        msg = await super().send_video(chat_id, *args, **kwargs)
        await self._auto_track(chat_id, msg.message_id)
        return msg

    async def send_document(self, chat_id, *args, **kwargs):
        msg = await super().send_document(chat_id, *args, **kwargs)
        await self._auto_track(chat_id, msg.message_id)
        return msg

    async def send_audio(self, chat_id, *args, **kwargs):
        msg = await super().send_audio(chat_id, *args, **kwargs)
        await self._auto_track(chat_id, msg.message_id)
        return msg

    async def send_sticker(self, chat_id, *args, **kwargs):
        msg = await super().send_sticker(chat_id, *args, **kwargs)
        await self._auto_track(chat_id, msg.message_id)
        return msg

    async def send_animation(self, chat_id, *args, **kwargs):
        msg = await super().send_animation(chat_id, *args, **kwargs)
        await self._auto_track(chat_id, msg.message_id)
        return msg

    async def send_voice(self, chat_id, *args, **kwargs):
        msg = await super().send_voice(chat_id, *args, **kwargs)
        await self._auto_track(chat_id, msg.message_id)
        return msg

    async def copy_message(self, chat_id, *args, **kwargs):
        msg_id_obj = await super().copy_message(chat_id, *args, **kwargs)
        await self._auto_track(chat_id, msg_id_obj.message_id)
        return msg_id_obj

load_dotenv()
logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Backend / env helpers
# ---------------------------------------------------------------------------

async def _fetch_bots_from_backend() -> list[dict[str, str]]:
    """Fetch active bots from the backend internal API."""
    url = f"{BACKEND_URL}/internal/bots/active"
    headers: dict[str, str] = {}
    api_key = os.getenv("INTERNAL_API_KEY", "")
    if api_key:
        headers["X-Internal-Key"] = api_key
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            resp = await client.get(url, headers=headers)
            resp.raise_for_status()
            bots = resp.json()
            logger.info("Fetched %d active bot(s) from backend", len(bots))
            return bots
    except Exception as e:
        logger.warning("Could not fetch bots from backend (%s): %s", url, e)
        return []


def _parse_bots_from_env() -> list[dict[str, str]]:
    """Parse TELEGRAM_BOTS env var → list of {username, token, hmac_secret}."""
    raw = os.getenv("TELEGRAM_BOTS", "")
    bots: list[dict[str, str]] = []
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 3:
            logger.warning("Skipping malformed bot entry: %s", entry)
            continue
        # token may contain colons — rejoin middle parts
        bots.append({"username": parts[0], "token": ":".join(parts[1:-1]), "hmac_secret": parts[-1]})
    return bots


# ---------------------------------------------------------------------------
# Parallel bot validation
# ---------------------------------------------------------------------------

async def _validate_bot(cfg: dict) -> tuple[int, Bot, str, str, int] | None:
    """
    Validate one bot token via getMe.  Runs concurrently for all bots so
    startup time is O(1) regardless of bot count (not O(n)).

    Returns (bot_id, Bot instance, username, hmac_secret, db_id) or None on failure.
    """
    token = cfg.get("token", "")
    username = cfg.get("username", "")
    secret = cfg.get("hmac_secret", "")
    db_id = cfg.get("id", 0)  # backend DB primary key

    if not token or not username:
        logger.warning("Skipping bot entry with missing token/username")
        return None

    bot = TrackingBot(token=token)
    try:
        me = await bot.get_me()
        resolved = me.username or username
        if resolved != username:
            logger.info("   Bot username resolved: %s -> @%s", username, resolved)
        logger.info("Bot @%s (%s) id=%d connected", resolved, me.first_name, me.id)
        return me.id, bot, resolved, secret, db_id
    except Exception as exc:
        logger.error("Bot @%s token invalid or API unreachable: %s", username, exc)
        await bot.session.close()
        return None


# ---------------------------------------------------------------------------
# Config-change watcher
# ---------------------------------------------------------------------------

async def _config_watcher(
    current_tokens: frozenset[str],
    stop_event: asyncio.Event,
    interval: int,
) -> None:
    """
    Background task: poll the backend every *interval* seconds.
    Sets stop_event when the active bot set differs from current_tokens,
    which causes run_bots() to return True and triggers a process restart.
    Sleeps in 1-second ticks so it exits promptly when stop_event is set.
    """
    elapsed = 0
    while not stop_event.is_set():
        await asyncio.sleep(1)
        elapsed += 1
        if elapsed < interval:
            continue
        elapsed = 0

        try:
            new_configs = await _fetch_bots_from_backend()
            new_tokens = frozenset(
                c.get("token", "") for c in new_configs if c.get("token")
            )
            if new_tokens != current_tokens:
                added = len(new_tokens - current_tokens)
                removed = len(current_tokens - new_tokens)
                logger.info(
                    "Bot config changed (+%d/-%d) — restarting gateway", added, removed
                )
                stop_event.set()
        except Exception as exc:
            logger.warning("Config watcher check failed: %s", exc)


# ---------------------------------------------------------------------------
# Main bot runner
# ---------------------------------------------------------------------------

async def run_bots() -> bool:
    """
    Start all configured bots under a single shared Dispatcher.

    Returns True  → caller should restart the process (config changed).
    Returns False → clean shutdown (SIGINT / no bots found).
    """
    _BOT_CONFIGS.clear()

    bots_config = await _fetch_bots_from_backend()
    if not bots_config:
        logger.info("No bots from backend API. Trying TELEGRAM_BOTS env var...")
        bots_config = _parse_bots_from_env()

    if not bots_config:
        logger.error(
            "No bots configured!\n"
            "  -> Add a bot via the Admin Panel (Bots page), OR\n"
            "  -> Set TELEGRAM_BOTS env var (format: username:token:secret)"
        )
        return False

    # Validate ALL tokens concurrently — fast even with 15+ bots
    logger.info("Validating %d bot token(s) in parallel...", len(bots_config))
    results = await asyncio.gather(
        *[_validate_bot(cfg) for cfg in bots_config],
        return_exceptions=True,
    )

    bots: list[Bot] = []
    for r in results:
        if isinstance(r, Exception):
            logger.error("Unexpected bot validation error: %s", r)
            continue
        if r is None:
            continue
        bot_id, bot, username, secret, db_id = r
        _BOT_CONFIGS[bot_id] = {"username": username, "hmac_secret": secret, "db_id": db_id}
        bots.append(bot)

    if not bots:
        logger.error("No valid bots could be started. Check bot tokens in Admin Panel.")
        return False

    # Single shared Dispatcher — routers registered once, middleware resolves
    # per-bot config at request-time via BotConfigMiddleware.
    dp = Dispatcher()
    dp.update.outer_middleware(BotConfigMiddleware(_BOT_CONFIGS))
    dp.message.middleware(RequestLoggingMiddleware())
    dp.message.middleware(MessageTrackingMiddleware())
    dp.include_router(start_router)
    dp.include_router(payment_router)
    dp.include_router(upload_router)
    dp.include_router(utr_group_router)
    dp.include_router(fallback_router)

    # Start background message-tracking flush loop
    start_flush_task()

    check_interval = int(os.getenv("BOT_CONFIG_CHECK_INTERVAL", "60"))
    current_tokens = frozenset(cfg.get("token", "") for cfg in bots_config if cfg.get("token"))
    stop_event = asyncio.Event()

    logger.info(
        "Starting %d bot(s) in polling mode (config check every %ds)...",
        len(bots), check_interval,
    )

    watcher_task = asyncio.create_task(
        _config_watcher(current_tokens, stop_event, check_interval)
    )

    should_restart = False
    polling_task: asyncio.Task | None = None

    try:
        # handle_signals=False: let asyncio.run() handle SIGINT/KeyboardInterrupt
        # close_bot_session=False: we close sessions explicitly in finally so
        # they're always closed exactly once even if start_polling raises.
        polling_task = asyncio.create_task(
            dp.start_polling(*bots, handle_signals=False, close_bot_session=False)
        )

        # Block until polling ends OR the watcher signals a config change
        done, _ = await asyncio.wait(
            {polling_task, asyncio.create_task(stop_event.wait())},
            return_when=asyncio.FIRST_COMPLETED,
        )

        should_restart = stop_event.is_set()

        if should_restart and not polling_task.done():
            logger.info("Stopping polling for gateway restart...")
            polling_task.cancel()
            try:
                await polling_task
            except (asyncio.CancelledError, Exception):
                pass
        elif not polling_task.done():
            await polling_task  # propagate any polling exception

    except (KeyboardInterrupt, asyncio.CancelledError):
        # Clean shutdown via Ctrl-C or external cancellation — do not restart
        should_restart = False

    finally:
        # Cancel in-flight tasks
        if polling_task and not polling_task.done():
            polling_task.cancel()
            try:
                await polling_task
            except (asyncio.CancelledError, Exception):
                pass

        stop_event.set()
        watcher_task.cancel()
        try:
            await watcher_task
        except asyncio.CancelledError:
            pass

        # Close all aiohttp sessions
        for bot in bots:
            try:
                await bot.session.close()
            except Exception:
                pass
        logger.info("All bot sessions closed.")

    return should_restart


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    """
    Entry point for the Telegram gateway.

    If run_bots() returns True (bot config changed), the process replaces
    itself via os.execv — this gives a completely fresh Python process with
    clean module-level state, avoiding aiogram Router re-attachment errors.
    """
    log_level = os.getenv("LOG_LEVEL", "INFO")
    os.makedirs("data", exist_ok=True)

    logging.basicConfig(
        level=getattr(logging, log_level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("data/gateway.log", encoding="utf-8"),
        ],
    )

    try:
        should_restart = asyncio.run(run_bots())
    except Exception as exc:
        logger.exception("run_bots() crashed: %s", exc)
        should_restart = True

    if should_restart:
        delay = int(os.getenv("BOT_RESTART_DELAY", "3"))
        logger.info("Restarting gateway process in %d second(s)...", delay)
        import time
        time.sleep(delay)
        # Replace current process image — clean slate, no singleton leakage
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    main()