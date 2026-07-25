"""Fabrique de session locale pour les outils opérateurs (hors requête HTTP).

Les scripts CLI n'ont pas d'``AsyncSession`` fournie par FastAPI : ce helper
construit un engine éphémère à partir de la configuration (``Settings``) — donc
depuis ``DATABASE_URL``, jamais d'accès ``os.environ`` dispersé (NFR3).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_settings


@asynccontextmanager
async def session_scope(database_url: str | None = None) -> AsyncIterator[AsyncSession]:
    """Ouvre une session locale, commit à la sortie, dispose l'engine ensuite."""

    url = database_url or get_settings().DATABASE_URL
    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise
    finally:
        await engine.dispose()


__all__ = ["session_scope"]
