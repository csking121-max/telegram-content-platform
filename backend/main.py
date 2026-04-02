"""
Telegram Content Access Platform — FastAPI entry-point.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from backend.config import settings
from backend.database import async_engine, Base
from backend.api.router import api_router
from backend.api.endpoints.sms_webhook import TgProxyPayload, telegram_proxy
from backend.dependencies import get_db

logger = logging.getLogger(__name__)


def _setup_logging() -> None:
    """Configure logging to both console and file."""
    log_level = getattr(logging, settings.LOG_LEVEL, logging.INFO)

    # Ensure data directory exists
    os.makedirs("data", exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(log_level)

    formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console handler
    console = logging.StreamHandler(sys.stdout)
    console.setLevel(log_level)
    console.setFormatter(formatter)
    root_logger.addHandler(console)

    # File handler — rotating is overkill for dev, simple append
    file_handler = logging.FileHandler("data/backend.log", encoding="utf-8")
    file_handler.setLevel(log_level)
    file_handler.setFormatter(formatter)
    root_logger.addHandler(file_handler)

    # Telegram notification handler (ERROR+ to admin chat)
    if settings.ADMIN_NOTIFY_BOT_TOKEN and settings.ADMIN_NOTIFY_CHAT_ID:
        from backend.utils.telegram_notify_handler import TelegramNotifyHandler
        tg_handler = TelegramNotifyHandler(
            bot_token=settings.ADMIN_NOTIFY_BOT_TOKEN,
            chat_id=settings.ADMIN_NOTIFY_CHAT_ID,
        )
        tg_handler.setLevel(logging.ERROR)
        tg_handler.setFormatter(formatter)
        root_logger.addHandler(tg_handler)
        root_logger.info("Telegram error notifications enabled → chat %s", settings.ADMIN_NOTIFY_CHAT_ID)


# ── Lifespan (startup / shutdown) ────────────────────────
async def _cleanup_worker() -> None:
    """Background task: run auto-cleanup every hour."""
    from backend.api.endpoints.internal import auto_cleanup_all_bots
    while True:
        await asyncio.sleep(3600)  # wait 1 hour between runs
        try:
            await auto_cleanup_all_bots()
        except Exception as exc:
            logger.warning("Auto-cleanup job failed: %s", exc)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    _setup_logging()
    logger.info("Starting Telegram Content Access Platform …")

    # Create tables if they don't exist (dev convenience – use Alembic in prod)
    async with async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Database tables verified.")

    # Start auto-cleanup background task
    cleanup_task = asyncio.create_task(_cleanup_worker())
    logger.info("Auto-cleanup worker started (runs every 1 hour).")

    # Keep-alive ping for serverless databases (Neon, Supabase) that cold-start
    # after idle periods. Runs every 4 minutes — prevents the ~500ms cold start
    # penalty on the first real user request.
    keepalive_task: asyncio.Task | None = None
    if not settings.DATABASE_URL.startswith("sqlite"):
        async def _db_keepalive() -> None:
            from sqlalchemy import text
            while True:
                await asyncio.sleep(240)  # 4 minutes
                try:
                    async with async_engine.connect() as conn:
                        await conn.execute(text("SELECT 1"))
                except Exception as exc:
                    logger.warning("DB keep-alive ping failed: %s", exc)
        keepalive_task = asyncio.create_task(_db_keepalive())
        logger.info("DB keep-alive task started (every 4 min).")

    yield

    # Shutdown
    cleanup_task.cancel()
    if keepalive_task:
        keepalive_task.cancel()
    try:
        await cleanup_task
    except asyncio.CancelledError:
        pass
    if keepalive_task:
        try:
            await keepalive_task
        except asyncio.CancelledError:
            pass
    await async_engine.dispose()
    logger.info("Shutdown complete.")


# ── App factory ──────────────────────────────────────────
app = FastAPI(
    title="Telegram Content Access Platform",
    version="1.0.0",
    docs_url="/docs" if settings.DEBUG else None,
    redoc_url="/redoc" if settings.DEBUG else None,
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request ID middleware ────────────────────────────────
class RequestIDMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex[:12]
        request.state.request_id = request_id
        response = await call_next(request)
        response.headers["X-Request-ID"] = request_id
        return response


app.add_middleware(RequestIDMiddleware)


# ── Global exception handler (hide stack traces in production) ───
@app.exception_handler(Exception)
async def _global_exception_handler(request: Request, exc: Exception):
    req_id = getattr(getattr(request, "state", None), "request_id", "?")
    logger.exception("Unhandled error [req=%s]: %s", req_id, exc)
    if settings.DEBUG:
        detail = str(exc)
    else:
        detail = "Internal server error"
    return JSONResponse(status_code=500, content={"detail": detail})


# Mount all routes
app.include_router(api_router)


@app.get("/", tags=["health"])
async def root():
    return {"status": "ok", "service": "telegram-content-platform"}


# ── Telegram-API-compatible route for SMS Forwarder apps ──
# SMS Forwarder apps call: https://api.telegram.org/bot<TOKEN>/sendMessage
# By changing base URL to our server, they hit this route instead.
@app.post("/bot{token}/sendMessage", tags=["sms"])
async def tg_api_compat_send_message(
    body: TgProxyPayload,
    token: str,
    db=Depends(get_db),
):
    """Drop-in replacement for Telegram's sendMessage API."""
    return await telegram_proxy(body, db)