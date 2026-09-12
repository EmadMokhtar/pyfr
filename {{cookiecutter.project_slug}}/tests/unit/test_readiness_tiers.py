"""The two readiness tiers.

Gating checks decide whether this instance receives traffic. Informational
checks are reported and never decide anything. The distinction exists
because a shared dependency that the service survives losing — the cache —
would otherwise take EVERY pod out of rotation at the same moment, turning
a latency degradation into a total outage.
"""

from __future__ import annotations

import pytest

from {{ cookiecutter.package_name }}.container import ReadinessRegistry

pytestmark = pytest.mark.asyncio


async def test_an_informational_failure_does_not_make_the_report_unhealthy() -> None:
    registry = ReadinessRegistry()

    async def ok() -> None:
        return None

    async def broken() -> None:
        raise ConnectionError("redis is down")

    registry.register("database", ok)
    registry.register_informational("cache", broken)

    report = await registry.run(timeout=1.0)

    assert report.healthy is True
    assert report.gating == {"database": "ok"}
    assert report.informational == {"cache": "error: ConnectionError"}


async def test_a_gating_failure_does_make_the_report_unhealthy() -> None:
    registry = ReadinessRegistry()

    async def broken() -> None:
        raise ConnectionError("postgres is down")

    registry.register("database", broken)

    report = await registry.run(timeout=1.0)

    assert report.healthy is False
    assert report.gating == {"database": "error: ConnectionError"}


async def test_both_tiers_run_concurrently_not_one_tier_after_the_other() -> None:
    """The whole point of the concurrency in run(): worst case is ONE
    timeout, not one per tier. Two tiers run sequentially would double the
    endpoint's worst case, which is the bug this asserts against."""
    import asyncio

    registry = ReadinessRegistry()

    async def slow() -> None:
        await asyncio.sleep(10)

    registry.register("database", slow)
    registry.register_informational("cache", slow)

    started = asyncio.get_running_loop().time()
    report = await registry.run(timeout=0.2)
    elapsed = asyncio.get_running_loop().time() - started

    # Two 0.2s timeouts run concurrently finish in ~0.2s. Sequentially they
    # would take ~0.4s. Allow generous headroom for a slow machine while
    # still failing if the two tiers were awaited one after the other.
    assert elapsed < 0.35
    assert report.gating["database"].startswith("error: timeout")
    assert report.informational["cache"].startswith("error: timeout")


async def test_no_checks_at_all_is_healthy() -> None:
    report = await ReadinessRegistry().run(timeout=1.0)
    assert report.healthy is True
    assert report.gating == {}
    assert report.informational == {}
