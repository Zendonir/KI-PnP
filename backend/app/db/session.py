"""Datenbankanbindung (Async SQLAlchemy)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import Settings


class Database:
    """Kapselt Engine und Session-Factory."""

    def __init__(self, settings: Settings) -> None:
        kwargs: dict[str, object] = {"echo": settings.db_echo, "pool_pre_ping": True}
        if not settings.database_url.startswith("sqlite"):
            kwargs["pool_size"] = settings.db_pool_size
            kwargs["max_overflow"] = settings.db_max_overflow
        self._engine: AsyncEngine = create_async_engine(settings.database_url, **kwargs)
        self._sessionmaker = async_sessionmaker(
            self._engine, expire_on_commit=False, class_=AsyncSession
        )

    @property
    def engine(self) -> AsyncEngine:
        return self._engine

    @asynccontextmanager
    async def session(self) -> AsyncIterator[AsyncSession]:
        """Session mit automatischem Rollback im Fehlerfall."""
        async with self._sessionmaker() as session:
            try:
                yield session
            except Exception:
                await session.rollback()
                raise

    async def dispose(self) -> None:
        await self._engine.dispose()
