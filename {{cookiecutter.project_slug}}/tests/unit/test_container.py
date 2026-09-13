"""The composition root's adapter choice. No database is contacted."""

from __future__ import annotations
{%- if cookiecutter.database == "postgres" or cookiecutter.cache == "redis" or cookiecutter.object_storage == "s3" %}

import pytest
{%- endif %}
{%- if cookiecutter.cache == "redis" %}
from redis.asyncio import Redis
{%- endif %}
{%- if cookiecutter.database == "postgres" %}
from sqlalchemy.ext.asyncio import AsyncEngine
{%- endif %}

from {{ cookiecutter.package_name }}.container import build_container, close_container
{%- if cookiecutter.cache == "redis" %}
from {{ cookiecutter.package_name }}.infrastructure.cache.order_repository import (
    CachedOrderRepository,
)
{%- endif %}
{%- if cookiecutter.database == "postgres" %}
from {{ cookiecutter.package_name }}.infrastructure.db.order_repository import (
    PostgresOrderRepository,
)
{%- endif %}
from {{ cookiecutter.package_name }}.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
{%- if cookiecutter.object_storage == "s3" %}
from {{ cookiecutter.package_name }}.infrastructure.memory.receipt_store import (
    InMemoryReceiptStore,
)
from {{ cookiecutter.package_name }}.infrastructure.storage.receipt_store import (
    S3ReceiptStore,
)
{%- endif %}
from {{ cookiecutter.package_name }}.settings import Settings
{%- if cookiecutter.database == "postgres" %}

DSN = "postgresql://app:secret@localhost:5432/app"
{%- endif %}


def test_no_database_configured_selects_the_in_memory_adapter() -> None:
    """A service generated with database=none must still start and serve."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert isinstance(container.orders, InMemoryOrderRepository)
{%- if cookiecutter.database == "postgres" %}
    assert container.engine is None
{%- endif %}


def test_no_database_configured_registers_no_readiness_check() -> None:
    """/readyz must not report on a dependency this service does not have."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert container.readiness._gating == {}
{%- if cookiecutter.database == "postgres" %}


def test_a_configured_dsn_selects_the_postgresql_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE__DSN", DSN)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert isinstance(container.orders, PostgresOrderRepository)
    assert container.engine is not None
{%- endif %}
{%- if cookiecutter.database == "postgres" %}


def test_a_configured_dsn_registers_a_database_readiness_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE__DSN", DSN)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert "database" in container.readiness._gating
{%- endif %}
{%- if cookiecutter.database == "postgres" %}


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
{%- endif %}


async def test_close_container_is_safe_without_a_database() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    await close_container(build_container(settings))  # must not raise
{%- if cookiecutter.cache == "redis" %}


async def test_close_container_closes_the_redis_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pool left open holds connections after shutdown begins — the same
    concern test_close_container_disposes_the_pool covers for the database,
    now for the cache. Before this test, deleting `await
    container.redis.aclose()` from close_container left the whole suite
    green: a resource-leak path with no regression net.

    Patched on the class, for the same reason as
    test_close_container_disposes_the_pool: `Redis` is a concrete class
    from redis-py, and monkeypatch reverts this after the test either way.
    """
    monkeypatch.setenv("APP_CACHE__DSN", "redis://localhost:6379/0")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    container = build_container(settings)
    assert container.redis is not None

    closed = False

    async def record_aclose(self: Redis) -> None:
        nonlocal closed
        closed = True

    monkeypatch.setattr(Redis, "aclose", record_aclose)

    await close_container(container)

    assert closed
{%- endif %}
{%- if cookiecutter.cache == "redis" %}


def test_no_cache_settings_means_no_cache_and_no_report() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    container = build_container(settings)

    assert container.redis is None
    assert "cache" not in container.readiness._informational
{%- endif %}
{%- if cookiecutter.cache == "redis" %}


def test_cache_settings_wrap_the_repository_and_register_a_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
{%- if cookiecutter.database == "postgres" %}
    monkeypatch.setenv(
        "APP_DATABASE__DSN", "postgresql://app:secret@localhost:5432/app"
    )
{%- endif %}
    monkeypatch.setenv("APP_CACHE__DSN", "redis://localhost:6379/0")
    container = build_container(Settings(_env_file=None))  # type: ignore[call-arg]

    assert isinstance(container.orders, CachedOrderRepository)
    assert container.redis is not None
    # Reported, and NOT gating — the distinction Task 2 exists for.
    assert "cache" in container.readiness._informational
    assert "cache" not in container.readiness._gating
{%- endif %}
{%- if cookiecutter.cache == "redis" %}


def test_a_cache_without_a_database_still_wraps_the_in_memory_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An odd combination, but it must not crash: the decorator wraps
    whatever repository was selected, and neither one knows about the
    other."""
    monkeypatch.setenv("APP_CACHE__DSN", "redis://localhost:6379/0")
    container = build_container(Settings(_env_file=None))  # type: ignore[call-arg]

    assert isinstance(container.orders, CachedOrderRepository)
{%- endif %}
{%- if cookiecutter.object_storage == "s3" %}


def test_no_storage_settings_means_the_in_memory_store() -> None:
    container = build_container(Settings(_env_file=None))  # type: ignore[call-arg]

    assert isinstance(container.receipts, InMemoryReceiptStore)
    assert "storage" not in container.readiness._informational


def test_storage_settings_select_the_s3_store_and_register_a_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_STORAGE__BUCKET", "receipts")
    monkeypatch.setenv("APP_STORAGE__ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("APP_STORAGE__ACCESS_KEY_ID", "key")
    monkeypatch.setenv("APP_STORAGE__SECRET_ACCESS_KEY", "secret")
    container = build_container(Settings(_env_file=None))  # type: ignore[call-arg]

    assert isinstance(container.receipts, S3ReceiptStore)
    # Reported, never gating: losing the store breaks ONE endpoint, so
    # taking the pod out of rotation would cost far more than it saves.
    assert "storage" in container.readiness._informational
    assert "storage" not in container.readiness._gating
{%- endif %}
{%- if cookiecutter.database == "postgres" and cookiecutter.cache == "redis" and cookiecutter.object_storage == "s3" %}


def test_all_three_dependencies_together_split_into_the_right_tiers(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Each dependency's readiness split was tested alone above; this is
    the INTERACTION, which is exactly what a whole-branch review worries
    about and what no single-dependency test can show.

    No real connections are made: build_container constructs its clients
    lazily and opens no sockets, so this needs no Docker, the same as
    every other test in this module.
    """
    monkeypatch.setenv("APP_DATABASE__DSN", DSN)
    monkeypatch.setenv("APP_CACHE__DSN", "redis://localhost:6379/0")
    monkeypatch.setenv("APP_STORAGE__BUCKET", "receipts")
    monkeypatch.setenv("APP_STORAGE__ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("APP_STORAGE__ACCESS_KEY_ID", "key")
    monkeypatch.setenv("APP_STORAGE__SECRET_ACCESS_KEY", "secret")
    container = build_container(Settings(_env_file=None))  # type: ignore[call-arg]

    assert set(container.readiness._gating) == {"database"}
    assert set(container.readiness._informational) == {"cache", "storage"}
{%- endif %}
