"""Engine async, fabrique de sessions et dépendance FastAPI."""

from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import get_settings


def create_engine(database_url: str) -> AsyncEngine:
    """Construit un engine async depuis une URL fournie par ``Settings``."""

    return create_async_engine(database_url, future=True)


engine = create_engine(get_settings().DATABASE_URL)
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Fournit une transaction par requête avec commit/rollback/close garantis."""

    async with SessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


__all__ = ["SessionFactory", "create_engine", "engine", "get_session"]
