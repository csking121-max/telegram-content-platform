"""
Database engine and session factories.

• Async engine / session  → used by FastAPI endpoints
• Sync  engine / session  → used by Alembic migrations & RQ workers

Supports both PostgreSQL (production) and SQLite (local development).
Set DATABASE_URL=sqlite+aiosqlite:///./data/platform.db for local dev.
"""
from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from backend.config import settings

_is_sqlite = settings.DATABASE_URL.startswith("sqlite")

# ── Async (FastAPI) ──────────────────────────────────────
_async_kwargs: dict = {"echo": settings.DEBUG and settings.LOG_LEVEL == "DEBUG"}
if _is_sqlite:
    # SQLite: no pool settings, needs check_same_thread=False
    _async_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _async_kwargs.update(pool_size=20, max_overflow=10, pool_pre_ping=True)

async_engine = create_async_engine(settings.DATABASE_URL, **_async_kwargs)

AsyncSessionLocal = async_sessionmaker(
    bind=async_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# ── Sync (Alembic & workers) ────────────────────────────
_sync_kwargs: dict = {"echo": settings.DEBUG and settings.LOG_LEVEL == "DEBUG"}
if _is_sqlite:
    _sync_url = settings.DATABASE_URL_SYNC or settings.DATABASE_URL.replace("+aiosqlite", "")
    _sync_kwargs["connect_args"] = {"check_same_thread": False}
else:
    _sync_url = settings.DATABASE_URL_SYNC
    _sync_kwargs.update(pool_size=10, max_overflow=5, pool_pre_ping=True)

sync_engine = create_engine(_sync_url, **_sync_kwargs)

SyncSessionLocal = sessionmaker(
    bind=sync_engine,
    class_=Session,
    expire_on_commit=False,
)


# ── Declarative Base ────────────────────────────────────
class Base(DeclarativeBase):
    """Shared base for every ORM model."""
    pass


# ── Dependency helpers ──────────────────────────────────
async def get_async_session() -> AsyncSession:  # type: ignore[misc]
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


def get_sync_session() -> Session:  # type: ignore[misc]
    session = SyncSessionLocal()
    try:
        yield session
    finally:
        session.close()