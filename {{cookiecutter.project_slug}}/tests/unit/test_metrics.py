"""The saturation signals, read through an in-memory reader."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from reference_service.observability.metrics import register_runtime_metrics
from reference_service.observability.otel import OtelRuntime, build_views


@pytest.fixture(autouse=True)
def _uninstrument_system_metrics() -> Iterator[None]:
    """SystemMetricsInstrumentor is a process-wide singleton.

    Left instrumented, the next instrument() call hits the
    already-instrumented guard, which logs a warning and returns None —
    so that meter provider silently never receives the process metrics.

    Guards BEFORE the test as well as after. Teardown alone only protects
    against state this module created; pytest collects in path order, so
    an EARLIER module that ran a lifespan with telemetry on would leave
    the singleton instrumented and make the first test here fail with a
    misleading "process.memory.usage not in names".

    Note that the already-instrumented case is a standard-library
    `logging` warning, not `warnings.warn`, so `filterwarnings = ["error"]`
    gives no protection here at all — hence an explicit fixture.
    """
    SystemMetricsInstrumentor().uninstrument()
    yield
    SystemMetricsInstrumentor().uninstrument()


@pytest.fixture
def reader() -> InMemoryMetricReader:
    return InMemoryMetricReader()


@pytest.fixture
def runtime(reader: InMemoryMetricReader) -> OtelRuntime:
    return OtelRuntime(
        tracer_provider=TracerProvider(),
        meter_provider=MeterProvider(metric_readers=[reader], views=build_views()),
        logger_provider=None,
    )


@pytest.fixture
def engine() -> AsyncEngine:
    """No connection is opened by create_async_engine, so no database.

    pool_size=7 with max_overflow=0 is what makes the ceiling an exact
    number the test can assert on.
    """
    return create_async_engine(
        "postgresql+asyncpg://u:p@localhost:5432/db", pool_size=7, max_overflow=0
    )


def _points(reader: InMemoryMetricReader, name: str) -> list[Any]:
    data = reader.get_metrics_data()
    if data is None:
        return []
    return [
        point
        for resource_metrics in data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name == name
        for point in metric.data.data_points
    ]


def _names(reader: InMemoryMetricReader) -> set[str]:
    data = reader.get_metrics_data()
    assert data is not None
    return {
        metric.name
        for resource_metrics in data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }


async def test_service_info_reports_one_carrying_the_version(
    runtime: OtelRuntime, reader: InMemoryMetricReader
) -> None:
    """Spec 7.4: the metric that lets a dashboard annotate deployments.

    Its value is always 1 and carries no information. The information is
    the service_version label, promoted from the resource, which changes
    the instant a new release starts serving — so a latency step and the
    deployment that caused it land on the same chart.
    """
    metrics = register_runtime_metrics(runtime, service_version="1.2.3")
    try:
        assert [point.value for point in _points(reader, "service.info")] == [1]
    finally:
        await metrics.stop()


async def test_pool_gauges_report_used_idle_and_the_ceiling(
    runtime: OtelRuntime, reader: InMemoryMetricReader, engine: AsyncEngine
) -> None:
    """A pool at its ceiling is a queue, and a queue is latency.

    This is visible minutes before the error rate moves, which is the
    entire reason spec 7.4 asks for saturation beside RED.
    """
    metrics = register_runtime_metrics(runtime, service_version="1.2.3", engine=engine)
    try:
        states = {
            point.attributes["state"]: point.value
            for point in _points(reader, "db.client.connection.count")
        }
        assert states == {"used": 0, "idle": 0}
        assert [
            point.value for point in _points(reader, "db.client.connection.max")
        ] == [7]
    finally:
        await metrics.stop()
        await engine.dispose()


async def test_no_pool_gauges_without_a_database(
    runtime: OtelRuntime, reader: InMemoryMetricReader
) -> None:
    """The in-memory adapter path must not report a pool it does not have."""
    metrics = register_runtime_metrics(runtime, service_version="1.2.3")
    try:
        assert _points(reader, "db.client.connection.count") == []
    finally:
        await metrics.stop()


async def test_event_loop_lag_is_recorded(
    runtime: OtelRuntime, reader: InMemoryMetricReader
) -> None:
    """Lag is how long a ready callback waited for the loop to reach it.

    It is the number that explains a service being slow while the
    database is fast and the CPU is idle: something is blocking the loop.
    """
    metrics = register_runtime_metrics(
        runtime, service_version="1.2.3", event_loop_probe_interval_seconds=0.01
    )
    try:
        await asyncio.sleep(0.05)
        points = _points(reader, "event_loop.lag")
        assert points, "the probe task recorded nothing"
        assert points[0].count >= 1
        assert points[0].sum >= 0.0
    finally:
        await metrics.stop()


async def test_stop_cancels_the_probe_task(runtime: OtelRuntime) -> None:
    """A task left running past shutdown keeps the loop alive."""
    metrics = register_runtime_metrics(
        runtime, service_version="1.2.3", event_loop_probe_interval_seconds=0.01
    )
    task = metrics.probe_task

    await metrics.stop()

    assert task is not None
    assert task.done()
    assert metrics.probe_task is None


async def test_stop_is_idempotent(runtime: OtelRuntime) -> None:
    metrics = register_runtime_metrics(runtime, service_version="1.2.3")

    await metrics.stop()
    await metrics.stop()


async def test_stop_uninstruments_so_a_second_app_still_gets_metrics(
    runtime: OtelRuntime, reader: InMemoryMetricReader
) -> None:
    """The singleton must be released, or the next lifespan gets nothing.

    Without uninstrument() in stop(), a second application built in the
    same process hits the already-instrumented guard, which logs a warning
    and returns None — no exception, just no process metrics for the rest
    of the process.
    """
    first = register_runtime_metrics(runtime, service_version="1.2.3")
    await first.stop()

    second_reader = InMemoryMetricReader()
    second_runtime = OtelRuntime(
        tracer_provider=TracerProvider(),
        meter_provider=MeterProvider(metric_readers=[second_reader]),
        logger_provider=None,
    )
    second = register_runtime_metrics(second_runtime, service_version="1.2.3")
    try:
        assert "process.memory.usage" in _names(second_reader)
    finally:
        await second.stop()


async def test_process_and_gc_metrics_are_present_but_not_the_host_ones(
    runtime: OtelRuntime, reader: InMemoryMetricReader
) -> None:
    """Verified fact 14: the instrumentor's defaults are wrong for us.

    Left at defaults it emits both the current names and their deprecated
    `process.runtime.cpython.*` duplicates, plus whole-host `system.*`
    series describing the developer's laptop rather than this service.
    """
    metrics = register_runtime_metrics(runtime, service_version="1.2.3")
    try:
        names = _names(reader)
        assert "process.memory.usage" in names
        assert "process.thread.count" in names
        assert "cpython.gc.collections" in names

        assert not [name for name in names if name.startswith("system.")]
        assert not [name for name in names if name.startswith("process.runtime.")]
    finally:
        await metrics.stop()
