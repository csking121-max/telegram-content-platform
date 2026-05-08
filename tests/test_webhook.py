"""
Tests for HMAC validation and webhook signature verification.
"""
import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from backend.database import Base
from backend.models.bot import Bot
from backend.models.content_pack import ContentPack
from backend.models.cooldown import Cooldown  # noqa: F401 - ensure table is registered
from backend.models.platform_setting import PlatformSetting
from backend.models.token import Token
from tests.conftest import TestSessionLocal, test_engine
from backend.security.hmac_validation import validate_hmac


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def test_valid_hmac():
    secret = "my-secret"
    body = b'{"action":"test"}'
    sig = _sign(secret, body)
    assert validate_hmac(secret, body, sig) is True


def test_invalid_hmac():
    secret = "my-secret"
    body = b'{"action":"test"}'
    assert validate_hmac(secret, body, "invalid-signature") is False


def test_wrong_secret():
    body = b'{"data":"hello"}'
    sig = _sign("correct-secret", body)
    assert validate_hmac("wrong-secret", body, sig) is False


def test_tampered_body():
    secret = "my-secret"
    original = b'{"amount":100}'
    sig = _sign(secret, original)
    tampered = b'{"amount":9999}'
    assert validate_hmac(secret, tampered, sig) is False


def test_empty_body():
    secret = "s"
    body = b""
    sig = _sign(secret, body)
    assert validate_hmac(secret, body, sig) is True


def test_empty_signature():
    assert validate_hmac("secret", b"body", "") is False


class _FakeRedisClient:
    def __init__(self):
        self.values: dict[str, str] = {}
        self.counts: dict[str, int] = {}

    def incr(self, key: str) -> int:
        self.counts[key] = self.counts.get(key, 0) + 1
        return self.counts[key]

    def expire(self, key: str, _ttl: int) -> None:
        return None

    def delete(self, key: str) -> None:
        self.counts.pop(key, None)
        self.values.pop(key, None)

    def get(self, key: str):
        return self.values.get(key)

    def setex(self, key: str, _ttl: int, value: str) -> None:
        self.values[key] = value


class _FakeRedis:
    def __init__(self):
        self.client = _FakeRedisClient()


def _build_test_app():
    from fastapi import FastAPI
    from backend.api.router import api_router
    from backend.dependencies import get_db

    app = FastAPI()
    app.include_router(api_router)

    async def _override_db():
        async with TestSessionLocal() as session:
            yield session

    app.dependency_overrides[get_db] = _override_db
    return app


@pytest.mark.asyncio
async def test_webhook_access_check_applies_cooldown(monkeypatch):
    fake_redis = _FakeRedis()
    monkeypatch.setattr(
        "backend.redis_client.RedisClient.get",
        staticmethod(lambda: fake_redis),
    )

    secret = "cooldown-secret"
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with TestSessionLocal() as db:
        bot = Bot(
            bot_username="coolbot",
            bot_token="123:COOL",
            webhook_secret=secret,
            status="active",
        )
        pack = ContentPack(title="Cooldown Pack", access_type="free", credit_cost=0)
        db.add_all([
            bot,
            pack,
            PlatformSetting(key="cooldown_links_limit", value="1", category="cooldown"),
            PlatformSetting(key="cooldown_seconds", value="60", category="cooldown"),
        ])
        await db.flush()
        db.add(Token(token="cool-token", pack_id=pack.id, single_use=False, used_count=0))
        await db.commit()

    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "telegram_id": 444555,
            "username": "cooluser",
            "action": "access_check",
            "token": "cool-token",
        }
        body = json.dumps(payload).encode()
        headers = {"X-Signature": _sign(secret, body), "Content-Type": "application/json"}

        first = await client.post("/webhook/coolbot", content=body, headers=headers)
        assert first.status_code == 200
        assert first.json()["allowed"] is True

        second = await client.post("/webhook/coolbot", content=body, headers=headers)
        assert second.status_code == 200
        data = second.json()
        assert data["allowed"] is False
        assert "cooldown" in data["reason"].lower()
