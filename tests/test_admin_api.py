"""
Tests for admin API endpoints — auth protection + basic CRUD.

Covers:
  - 401 when no token / invalid token
  - Valid token: list users, user count, user detail, grant credits
  - Valid token: list bots, register bot, get bot, delete bot
  - CSRF check on cookie-based state-changing request
"""
from __future__ import annotations

from datetime import datetime, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from backend.models.bot import Bot
from backend.models.credit import Credit
from backend.models.user import User
from backend.security.auth import create_admin_token

from tests.conftest import TestSessionLocal, test_engine
from backend.database import Base


# ── Build a lightweight test app with dependency overrides ───

def _build_test_app():
    """
    Import the real FastAPI app and override get_db to use the test session.
    We also skip lifespan to avoid auto-cleanup worker.
    """
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


@pytest_asyncio.fixture
async def client():
    """Provide an AsyncClient aimed at the test app."""
    app = _build_test_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as c:
        yield c


@pytest_asyncio.fixture
async def admin_token() -> str:
    return create_admin_token("admin")


@pytest_asyncio.fixture
async def auth_headers(admin_token: str) -> dict:
    return {"Authorization": f"Bearer {admin_token}"}


# ── Seed data ───────────────────────────────────────────────

@pytest_asyncio.fixture
async def seeded_user(db: AsyncSession) -> User:
    u = User(telegram_id=900001, username="admin_test_user")
    db.add(u)
    await db.flush()
    db.add(Credit(user_id=u.id, balance=200))
    await db.flush()
    await db.commit()
    return u


@pytest_asyncio.fixture
async def seeded_bot(db: AsyncSession) -> Bot:
    b = Bot(
        bot_username="admin_test_bot",
        bot_token="999:ADMIN-TEST",
        webhook_secret="hmac_secret",
        status="active",
    )
    db.add(b)
    await db.flush()
    await db.commit()
    return b


# ── Auth protection ─────────────────────────────────────────

class TestAdminAuthProtection:
    @pytest.mark.asyncio
    async def test_no_token_returns_401(self, client):
        resp = await client.get("/admin/users")
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_invalid_token_returns_401(self, client):
        resp = await client.get(
            "/admin/users",
            headers={"Authorization": "Bearer garbage.token.value"},
        )
        assert resp.status_code == 401

    @pytest.mark.asyncio
    async def test_valid_token_succeeds(self, client, auth_headers, seeded_user):
        resp = await client.get("/admin/users", headers=auth_headers)
        assert resp.status_code == 200


# ── User endpoints ──────────────────────────────────────────

class TestAdminUsers:
    @pytest.mark.asyncio
    async def test_list_users(self, client, auth_headers, seeded_user):
        resp = await client.get("/admin/users", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_user_count(self, client, auth_headers, seeded_user):
        resp = await client.get("/admin/users/count", headers=auth_headers)
        assert resp.status_code == 200
        assert resp.json()["count"] >= 1

    @pytest.mark.asyncio
    async def test_user_detail(self, client, auth_headers, seeded_user):
        resp = await client.get(
            f"/admin/users/{seeded_user.id}/detail",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["telegram_id"] == 900001
        assert data["credit_balance"] == 200

    @pytest.mark.asyncio
    async def test_user_detail_not_found(self, client, auth_headers):
        resp = await client.get("/admin/users/99999/detail", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_grant_credits(self, client, auth_headers, seeded_user):
        resp = await client.post(
            f"/admin/users/{seeded_user.id}/grant-credits",
            headers=auth_headers,
            json={"amount": 50, "reason": "test bonus"},
        )
        assert resp.status_code == 200
        assert resp.json()["balance"] == 250


# ── Bot endpoints ───────────────────────────────────────────

class TestAdminBots:
    @pytest.mark.asyncio
    async def test_list_bots(self, client, auth_headers, seeded_bot):
        resp = await client.get("/admin/bots", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    @pytest.mark.asyncio
    async def test_register_bot(self, client, auth_headers):
        resp = await client.post(
            "/admin/bots",
            headers=auth_headers,
            json={
                "bot_username": "new_test_bot",
                "bot_token": "111:NEW-BOT-TOKEN",
                "webhook_secret": "new_secret",
            },
        )
        assert resp.status_code == 201
        assert resp.json()["bot_username"] == "new_test_bot"

    @pytest.mark.asyncio
    async def test_get_bot(self, client, auth_headers, seeded_bot):
        resp = await client.get(
            f"/admin/bots/{seeded_bot.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json()["bot_username"] == "admin_test_bot"

    @pytest.mark.asyncio
    async def test_get_bot_not_found(self, client, auth_headers):
        resp = await client.get("/admin/bots/99999", headers=auth_headers)
        assert resp.status_code == 404

    @pytest.mark.asyncio
    async def test_delete_bot(self, client, auth_headers, seeded_bot):
        resp = await client.delete(
            f"/admin/bots/{seeded_bot.id}",
            headers=auth_headers,
        )
        assert resp.status_code == 200


# ── CSRF on cookie-based auth ──────────────────────────────

class TestCSRFProtection:
    @pytest.mark.asyncio
    async def test_cookie_auth_post_without_csrf_rejected(self, client, admin_token, seeded_user):
        """POST using cookie auth without CSRF header → 403."""
        client.cookies.set("admin_access_token", admin_token)
        resp = await client.post(
            f"/admin/users/{seeded_user.id}/grant-credits",
            json={"amount": 10, "reason": "test"},
        )
        assert resp.status_code == 403
        assert "csrf" in resp.json()["detail"].lower()

    @pytest.mark.asyncio
    async def test_cookie_auth_post_with_csrf_succeeds(self, client, admin_token, seeded_user):
        """POST using cookie auth with matching CSRF header → 200."""
        csrf_value = "test-csrf-token-123"
        client.cookies.set("admin_access_token", admin_token)
        client.cookies.set("csrf_token", csrf_value)
        resp = await client.post(
            f"/admin/users/{seeded_user.id}/grant-credits",
            headers={"X-CSRF-Token": csrf_value},
            json={"amount": 10, "reason": "test"},
        )
        assert resp.status_code == 200
