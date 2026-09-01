"""The composition root's adapter choice. No database is contacted."""

from __future__ import annotations

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from reference_service.container import build_container, close_container
from reference_service.infrastructure.db.order_repository import (
    PostgresOrderRepository,
)
from reference_service.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from reference_service.settings import Settings

DSN = "postgresql://app:secret@localhost:5432/app"


def test_no_database_configured_selects_the_in_memory_adapter() -> None:
    """A service generated with database=none must still start and serve."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert isinstance(container.orders, InMemoryOrderRepository)
    assert container.engine is None


def test_no_database_configured_registers_no_readiness_check() -> None:
    """/readyz must not report on a dependency this service does not have."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert container.readiness._checks == {}


def test_a_configured_dsn_selects_the_postgresql_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE__DSN", DSN)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert isinstance(container.orders, PostgresOrderRepository)
    assert container.engine is not None


def test_a_configured_dsn_registers_a_database_readiness_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE__DSN", DSN)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert "database" in container.readiness._checks


async def test_close_container_disposes_the_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pool left open holds connections after shutdown begins.

    M0's close_container did nothing and said so; this is the M1 case it
    was waiting for.

    Patched on the class, not the instance: AsyncEngine declares
    `__slots__` with no `__dict__` (every class in its MRO does), so
    `monkeypatch.setattr(container.engine, "dispose", ...)` raises
    `AttributeError: 'AsyncEngine' object attribute 'dispose' is
    read-only` — confirmed directly against the pinned SQLAlchemy 2.0.52.
    Patching the class is the supported way to intercept it; monkeypatch
    still reverts this after the test.
    """
    monkeypatch.setenv("APP_DATABASE__DSN", DSN)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    container = build_container(settings)
    assert container.engine is not None

    disposed = False

    async def record_dispose(self: AsyncEngine) -> None:
        nonlocal disposed
        disposed = True

    monkeypatch.setattr(AsyncEngine, "dispose", record_dispose)

    await close_container(container)

    assert disposed


async def test_close_container_is_safe_without_a_database() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    await close_container(build_container(settings))  # must not raise
