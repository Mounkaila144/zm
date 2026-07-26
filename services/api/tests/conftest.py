"""Fixtures partagées : base SQLite async isolée pour chaque test."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator

import pytest
from app.config import get_settings
from app.core.rate_limit import limiter
from app.db.models import Base
from app.db.session import get_session
from app.main import app
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import NullPool


@pytest.fixture(autouse=True)
def reset_rate_limiter() -> Iterator[None]:
    """Empêche les compteurs de quota de fuir entre deux tests."""

    limiter.reset()
    try:
        yield
    finally:
        limiter.reset()


@pytest.fixture(autouse=True)
def legacy_request_compatibility(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Isole les tests historiques des deux nouvelles gardes de production."""

    monkeypatch.setenv("MOBILE_ENFORCE_MIN_BUILD", "false")
    monkeypatch.setenv("REQUIRE_TRAINING_CONSENT", "false")
    get_settings.cache_clear()
    try:
        yield
    finally:
        get_settings.cache_clear()


@pytest.fixture
def db_engine(tmp_path) -> Iterator[AsyncEngine]:
    engine = create_async_engine(
        f"sqlite+aiosqlite:///{tmp_path / 'test.db'}",
        poolclass=NullPool,
    )

    async def create_schema() -> None:
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)

    asyncio.run(create_schema())
    try:
        yield engine
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def db_session_factory(
    db_engine: AsyncEngine,
) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(db_engine, expire_on_commit=False)


@pytest.fixture(autouse=True)
def override_database(
    db_session_factory: async_sessionmaker[AsyncSession],
) -> Iterator[None]:
    async def override_get_session():
        async with db_session_factory() as session:
            try:
                yield session
                await session.commit()
            except Exception:
                await session.rollback()
                raise

    app.dependency_overrides[get_session] = override_get_session
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_session, None)
