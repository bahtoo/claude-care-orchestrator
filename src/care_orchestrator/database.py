"""
Async database engine — SQLAlchemy 2.0 with asyncio.

Production: PostgreSQL via asyncpg
Development/test: SQLite via aiosqlite (zero-config)

Configure via DATABASE_URL environment variable:
    DATABASE_URL=postgresql+asyncpg://user:pass@host:5432/care_orchestrator
    DATABASE_URL=sqlite+aiosqlite:///./care_orchestrator.db  (default)

Call `await create_tables()` once on application startup.
"""

from __future__ import annotations

import os

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

_DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "sqlite+aiosqlite:///./care_orchestrator.db",
)

# connect_args is SQLite-specific; ignored by asyncpg
_connect_args = {"check_same_thread": False} if "sqlite" in _DATABASE_URL else {}

engine = create_async_engine(
    _DATABASE_URL,
    echo=False,
    connect_args=_connect_args,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


# ---------------------------------------------------------------------------
# Declarative base (shared by all ORM models)
# ---------------------------------------------------------------------------


class Base(DeclarativeBase):
    pass


# ---------------------------------------------------------------------------
# Table creation helper
# ---------------------------------------------------------------------------


async def create_tables() -> None:
    """Create all tables defined via ORM models. Idempotent (CREATE IF NOT EXISTS)."""
    # Import here to ensure all models are registered before metadata.create_all
    from care_orchestrator import models_db  # noqa: F401

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    """Yield an async DB session (for use as a FastAPI dependency)."""
    async with AsyncSessionLocal() as session:
        yield session
