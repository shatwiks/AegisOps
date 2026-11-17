"""Async SQLAlchemy engine, session factory, and database readiness checks."""

from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy import text
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import Settings


def build_engine(settings: Settings) -> AsyncEngine:
    """Create the async SQLAlchemy engine for PostgreSQL + pgvector."""
    return create_async_engine(
        settings.aegisops_database_url,
        pool_pre_ping=True,
        pool_size=10,
        max_overflow=10,
        echo=False,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Create an async_sessionmaker with expire_on_commit=False."""
    return async_sessionmaker(engine, expire_on_commit=False, autoflush=False)


async def check_postgres_ready(engine: AsyncEngine) -> dict[str, str | bool]:
    """Verify PostgreSQL connectivity and pgvector extension presence."""
    async with engine.connect() as conn:
        await conn.execute(text("SELECT 1"))
        row = (
            await conn.execute(text("SELECT extversion FROM pg_extension WHERE extname = 'vector'"))
        ).first()
    if row is None:
        return {"connected": True, "pgvector_installed": False}
    return {"connected": True, "pgvector_installed": True, "pgvector_version": str(row[0])}


async def get_db_session(
    session_factory: async_sessionmaker[AsyncSession],
) -> AsyncGenerator[AsyncSession, None]:
    """Yield an AsyncSession per request and ensure cleanup."""
    async with session_factory() as session:
        yield session
