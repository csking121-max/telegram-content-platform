"""
Logging handler that sends ERROR/CRITICAL log records to a Telegram chat.

Only activates when ADMIN_NOTIFY_BOT_TOKEN and ADMIN_NOTIFY_CHAT_ID are set.
Uses synchronous urllib to avoid asyncio dependency inside the logging chain.
"""
from __future__ import annotations

import logging
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)


class TelegramNotifyHandler(logging.Handler):
    """Send ERROR+ logs to a Telegram chat via Bot API (non-blocking)."""

    API_URL = "https://api.telegram.org/bot{token}/sendMessage"

    # Throttle: max 1 message per 5 seconds to prevent flood
    MIN_INTERVAL = 5.0

    def __init__(self, bot_token: str, chat_id: str, level: int = logging.ERROR) -> None:
        super().__init__(level)
        self._token = bot_token
        self._chat_id = chat_id
        self._url = self.API_URL.format(token=bot_token)
        self._last_sent: float = 0.0
        self._lock = threading.Lock()

    def emit(self, record: logging.LogRecord) -> None:
        # Ignore logs from this module to prevent recursion
        if record.name == __name__:
            return

        with self._lock:
            now = time.monotonic()
            if now - self._last_sent < self.MIN_INTERVAL:
                return
            self._last_sent = now

        # Fire-and-forget in background thread
        threading.Thread(target=self._send, args=(record,), daemon=True).start()

    def _send(self, record: logging.LogRecord) -> None:
        try:
            text = self.format(record)
            # Truncate to Telegram's 4096 char limit
            if len(text) > 4000:
                text = text[:4000] + "\n… (truncated)"

            payload = urllib.parse.urlencode({
                "chat_id": self._chat_id,
                "text": f"🚨 *{record.levelname}*\n```\n{text}\n```",
                "parse_mode": "Markdown",
                "disable_web_page_preview": "true",
            }).encode()

            req = urllib.request.Request(self._url, data=payload, method="POST")
            req.add_header("Content-Type", "application/x-www-form-urlencoded")
            with urllib.request.urlopen(req, timeout=10):
                pass
        except Exception:
            # Silently ignore send failures — we don't want logging to crash
            pass
