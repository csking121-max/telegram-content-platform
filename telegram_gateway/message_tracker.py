"""
Message tracker — collects message IDs for cleanup feature.

Incoming user messages and outgoing bot messages are queued here,
then flushed in batches to the backend POST /internal/track-messages.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import Message, TelegramObject

from telegram_gateway.http_client import api_post

logger = logging.getLogger(__name__)

# In-memory queue flushed every few seconds
_queue: list[dict] = []
_queue_lock = asyncio.Lock()
_flush_task: asyncio.Task | None = None
_MAX_QUEUE_SIZE = 10_000

FLUSH_INTERVAL = 5  # seconds


async def track(bot_id: int, chat_id: int, message_id: int, direction: str = "out") -> None:
    """Add a message to the tracking queue."""
    async with _queue_lock:
        _queue.append({
            "bot_id": bot_id,
            "chat_id": chat_id,
            "message_id": message_id,
            "direction": direction,
        })
        # Drop oldest entries if queue grows too large (backend is unreachable)
        if len(_queue) > _MAX_QUEUE_SIZE:
            overflow = len(_queue) - _MAX_QUEUE_SIZE
            del _queue[:overflow]
            logger.warning("Message tracker queue overflow — dropped %d oldest entries", overflow)


async def _flush() -> None:
    """Send queued messages to the backend. Only clears queue on success."""
    async with _queue_lock:
        if not _queue:
            return
        batch = list(_queue)
        _queue.clear()

    try:
        result = await api_post("/internal/track-messages", batch)
        if result is None or (isinstance(result, dict) and result.get("_error")):
            # Failed — put items back at the front of the queue for retry
            logger.warning("Backend rejected tracked messages batch, will retry")
            async with _queue_lock:
                _queue[:0] = batch
    except Exception as e:
        logger.warning("Failed to flush tracked messages (will retry): %s", e)
        # Put items back for retry
        async with _queue_lock:
            _queue[:0] = batch


async def _flush_loop() -> None:
    """Background loop that flushes the queue periodically."""
    while True:
        await asyncio.sleep(FLUSH_INTERVAL)
        try:
            await _flush()
        except Exception:
            pass


def start_flush_task() -> None:
    """Start the background flush loop (call once at gateway startup)."""
    global _flush_task
    if _flush_task is None or _flush_task.done():
        _flush_task = asyncio.create_task(_flush_loop())


class MessageTrackingMiddleware(BaseMiddleware):
    """Outer middleware that tracks incoming user message IDs.

    Outgoing messages are tracked by calling ``track()`` explicitly
    in handlers after sending.
    """

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        # Track incoming user messages in private chats
        if isinstance(event, Message) and event.chat and event.chat.type == "private":
            bot = data.get("bot")
            if bot:
                from telegram_gateway.bot_manager import _BOT_CONFIGS
                cfg = _BOT_CONFIGS.get(bot.id, {})
                db_id = cfg.get("db_id", 0)
                if db_id:
                    await track(db_id, event.chat.id, event.message_id, "in")

        return await handler(event, data)
