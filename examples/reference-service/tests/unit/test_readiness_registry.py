"""The readiness registry runs its checks concurrently."""

from __future__ import annotations

import asyncio

from reference_service.container import ReadinessRegistry


async def test_checks_run_concurrently_not_one_after_another() -> None:
    """Two mutually dependent checks pass only if they actually overlap.

    The first waits for an event that only the second sets. Under a
    sequential implementation the first would exhaust its timeout before
    the second ever started, so this fails on sequential execution without
    depending on wall-clock thresholds, which flake under load.
    """
    registry = ReadinessRegistry()
    released = asyncio.Event()

    async def waits_for_the_other() -> None:
        await released.wait()

    async def releases_the_first() -> None:
        released.set()

    registry.register("waiter", waits_for_the_other)
    registry.register("releaser", releases_the_first)

    results = await registry.run(timeout=1.0)

    assert results == {"waiter": "ok", "releaser": "ok"}


async def test_a_failing_check_does_not_prevent_others_from_reporting() -> None:
    registry = ReadinessRegistry()

    async def fails() -> None:
        raise RuntimeError("database is down")

    async def succeeds() -> None:
        return None

    registry.register("database", fails)
    registry.register("cache", succeeds)

    results = await registry.run(timeout=1.0)

    assert results["cache"] == "ok"
    assert results["database"].startswith("error")


async def test_a_failing_check_reports_the_exception_type_not_its_message() -> None:
    """The response must not leak internal detail.

    /readyz is often reachable inside a cluster. An exception's own
    message routinely carries a hostname, a connection string, or
    credentials — a database driver's error commonly includes all three.
    The response gets a bounded value (the exception's type name); the
    operator-facing detail goes to the log instead, not the HTTP response.
    """
    registry = ReadinessRegistry()

    async def fails() -> None:
        raise RuntimeError("postgres://user:hunter2@db.internal:5432/orders")

    registry.register("database", fails)

    results = await registry.run(timeout=1.0)

    assert results["database"] == "error: RuntimeError"
    assert "hunter2" not in results["database"]
    assert "db.internal" not in results["database"]


async def test_no_checks_returns_an_empty_mapping() -> None:
    assert await ReadinessRegistry().run(timeout=1.0) == {}
