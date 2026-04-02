"""
Logging / metrics middleware for the Telegram gateway.

aiogram 3.x uses outer-middleware pattern: wrap each update handler.
"""

from __future__ import annotations

import logging
import time
from typing import Any, Awaitable, Callable, Dict

from aiogram import BaseMiddleware
from aiogram.types import TelegramObject

logger = logging.getLogger(__name__)


class BotConfigMiddleware(BaseMiddleware):
    """Inject per-bot ``bot_username`` and ``hmac_secret`` into handler data.

    With a single shared Dispatcher serving multiple bots, DI keys like
    ``dp["bot_username"]`` would only hold the *last* bot's config.  This
    middleware resolves the correct config at request-time using ``bot.id``.
    """

    def __init__(self, bot_configs: Dict[int, Dict[str, str]]) -> None:
        self._configs = bot_configs

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        bot = data.get("bot")
        if bot is not None:
            cfg = self._configs.get(bot.id, {})
            data["bot_username"] = cfg.get("username", "")
            data["hmac_secret"] = cfg.get("hmac_secret", "")
        return await handler(event, data)


class RequestLoggingMiddleware(BaseMiddleware):
    """Log every incoming update with timing."""

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any],
    ) -> Any:
        t0 = time.perf_counter()
        try:
            result = await handler(event, data)
        finally:
            elapsed = (time.perf_counter() - t0) * 1000
            logger.info(
                "Processed update in %.1f ms | type=%s",
                elapsed,
                type(event).__name__,
            )
        return result