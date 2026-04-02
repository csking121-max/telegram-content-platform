"""
Tests for Telegram Gateway handler utilities — pure functions and
in-memory deduplication logic.

Covers:
  - _md_escape(): Telegram Markdown v1 character escaping
  - _build_main_menu(): keyboard layout with/without channel link
  - _build_join_channel_kb(): join-channel keyboard
  - _claim_message(): multi-bot deduplication in upload handler
  - Channel join cache behaviour
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest


# ── Markdown escape ─────────────────────────────────────────

class TestMdEscape:
    def setup_method(self):
        from telegram_gateway.handlers.start import _md_escape
        self._fn = _md_escape

    def test_no_special_chars(self):
        assert self._fn("hello world") == "hello world"

    def test_escapes_underscore(self):
        assert self._fn("hello_world") == "hello\\_world"

    def test_escapes_asterisk(self):
        assert self._fn("*bold*") == "\\*bold\\*"

    def test_escapes_backtick(self):
        assert self._fn("`code`") == "\\`code\\`"

    def test_escapes_bracket(self):
        assert self._fn("[link]") == "\\[link]"

    def test_multiple_special_chars(self):
        result = self._fn("_hello_ *world* `code` [link]")
        assert "\\_" in result
        assert "\\*" in result
        assert "\\`" in result
        assert "\\[" in result


# ── Main menu keyboard ──────────────────────────────────────

class TestBuildMainMenu:
    def setup_method(self):
        from telegram_gateway.handlers.start import _build_main_menu
        self._fn = _build_main_menu

    def test_without_channel_link(self):
        kb = self._fn()
        # First row: only Buy Membership (no Browse Content without link)
        assert len(kb.inline_keyboard[0]) == 1
        assert kb.inline_keyboard[0][0].text == "Buy Membership"

    def test_with_channel_link(self):
        kb = self._fn(content_channel_link="https://t.me/channel")
        # First row: Browse Content + Buy Membership
        assert len(kb.inline_keyboard[0]) == 2
        assert kb.inline_keyboard[0][0].text == "Browse Content"
        assert kb.inline_keyboard[0][0].url == "https://t.me/channel"

    def test_has_profile_and_credits(self):
        kb = self._fn()
        texts = [btn.text for row in kb.inline_keyboard for btn in row]
        assert "My Profile" in texts
        assert "My Credits" in texts
        assert "Buy Credits" in texts
        assert "Help" in texts


# ── Join channel keyboard ──────────────────────────────────

class TestBuildJoinChannelKb:
    def setup_method(self):
        from telegram_gateway.handlers.start import _build_join_channel_kb
        self._fn = _build_join_channel_kb

    def test_with_channel_link(self):
        kb = self._fn("https://t.me/chan", token="abc123")
        assert kb.inline_keyboard[0][0].text == "Join Channel"
        assert kb.inline_keyboard[0][0].url == "https://t.me/chan"
        # Second row: Check Again button
        assert "check_join:abc123" in kb.inline_keyboard[1][0].callback_data

    def test_without_token(self):
        kb = self._fn("https://t.me/chan")
        assert kb.inline_keyboard[1][0].callback_data == "check_join:"


# ── Upload deduplication (_claim_message) ──────────────────

class TestClaimMessage:
    def setup_method(self):
        # Reset the global OrderedDict before each test
        from telegram_gateway.handlers import upload
        upload._handled_upload_messages.clear()
        self._claim = upload._claim_message
        self._handled = upload._handled_upload_messages
        self._max = upload._MAX_HANDLED

    def _make_msg(self, chat_id: int, message_id: int) -> MagicMock:
        msg = MagicMock()
        msg.chat = MagicMock()
        msg.chat.id = chat_id
        msg.message_id = message_id
        return msg

    def test_first_claim_succeeds(self):
        msg = self._make_msg(100, 1)
        assert self._claim(msg) is True

    def test_second_claim_same_message_fails(self):
        msg = self._make_msg(100, 1)
        assert self._claim(msg) is True
        assert self._claim(msg) is False

    def test_different_messages_both_succeed(self):
        msg1 = self._make_msg(100, 1)
        msg2 = self._make_msg(100, 2)
        assert self._claim(msg1) is True
        assert self._claim(msg2) is True

    def test_eviction_when_over_limit(self):
        """When the handled set exceeds MAX, oldest entries are evicted."""
        from telegram_gateway.handlers import upload
        original_max = upload._MAX_HANDLED
        upload._MAX_HANDLED = 5  # temporarily reduce limit for testing

        try:
            # Fill beyond limit
            for i in range(7):
                self._claim(self._make_msg(200, i))

            # Oldest entries (0, 1) should have been evicted
            assert (200, 0) not in self._handled
            # Recent entries should still be present
            assert (200, 6) in self._handled
        finally:
            upload._MAX_HANDLED = original_max


# ── Channel join cache ──────────────────────────────────────

class TestJoinCache:
    def setup_method(self):
        from telegram_gateway.handlers import start
        start._join_cache.clear()
        self._cache = start._join_cache

    def test_cache_stores_and_retrieves(self):
        import time
        from telegram_gateway.handlers.start import _JOIN_CACHE_TTL
        key = ("@test_channel", 12345)
        self._cache[key] = (True, time.monotonic() + _JOIN_CACHE_TTL)
        result, expires = self._cache[key]
        assert result is True

    def test_cache_expired_entry(self):
        import time
        key = ("@test_channel", 99999)
        self._cache[key] = (True, time.monotonic() - 10)  # already expired
        result, expires = self._cache[key]
        assert time.monotonic() > expires  # entry is stale
