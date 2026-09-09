"""Instruments this service reports about itself.

RED — rate, errors, duration — arrives free from the FastAPI
instrumentation. What is here instead is saturation: the signals that
move BEFORE the error rate does, which is what makes them worth a panel.
A connection pool sitting at its ceiling is a queue, and a queue is
latency that has not been served yet. An event loop that has stopped
keeping up is the explanation for a service being slow while the database
is fast and the processor is idle.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

import structlog
from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.metrics import CallbackOptions, Meter, Observation
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import QueuePool

from reference_service.observability.otel import OtelRuntime

_logger = structlog.get_logger(__name__)

METER_NAME = "reference_service.runtime"

# How often the event loop is probed. Every tick is one histogram
# observation, so this trades resolution against series volume; two
# seconds is frequent enough to catch a blocking call inside one scrape
# interval and rare enough to be free.
DEFAULT_EVENT_LOOP_PROBE_INTERVAL_SECONDS = 2.0

# Exactly what dashboard 3 draws, and nothing else. The instrumentor's
# own defaults emit around thirty metrics: the current process and
# garbage-collection names, their deprecated `process.runtime.cpython.*`
# duplicates carrying the SAME numbers under different names, and a set
# of whole-host `system.*` series that describe the machine rather than
# this service — actively misleading in a container, where the host is
# shared with everything else on the node.
_PROCESS_METRICS_CONFIG: dict[str, list[str] | None] = {
    # `process.cpu.time`, not `process.cpu.utilization`. Verified against a
    # live stack: utilization is emitted with NO attributes at all — the
    # ["user", "system"] value is accepted for that key and then ignored —
    # so a panel doing `sum by (type)` over it collapses to one unlabelled
    # series with an empty legend. process.cpu.time genuinely does carry
    # `type=user` / `type=system`.
    "process.cpu.time": ["user", "system"],
    "process.memory.usage": None,
    "process.memory.virtual": None,
    "process.open_file_descriptor.count": None,
    "process.thread.count": None,
    "cpython.gc.collections": None,
    "cpython.gc.collected_objects": None,
    "cpython.gc.uncollectable_objects": None,
}


@dataclass
class RuntimeMetrics:
    """Handle for the things here that need stopping."""

    probe_task: asyncio.Task[None] | None
    # Held so stop() can undo instrument(). SystemMetricsInstrumentor is a
    # process-wide singleton: instrument it and never undo it, and the
    # SECOND application built in the same process hits the
    # already-instrumented guard, which logs a warning and returns None.
    # No exception, no failure — just no process or garbage-collection
    # metrics for the rest of the process. That bites any test suite that
    # runs more than one lifespan, and production on an in-process restart.
    instrumentor: SystemMetricsInstrumentor | None = None

    async def stop(self) -> None:
        """Cancel the probe, report why it died if it did, and uninstrument.

        Awaiting the cancellation rather than firing and forgetting is
        what makes shutdown deterministic: an un-awaited cancelled task
        can still be pending when the loop closes, which asyncio reports
        as "Task was destroyed but it is pending" on the way out — noise
        in exactly the logs someone is reading to find out why shutdown
        went wrong. Safe to call twice; lifespan's finally block may run
        after a startup that already failed.

        `asyncio.wait` rather than `await self.probe_task` inside a
        `try/except CancelledError`. That pattern catches the child's
        cancellation, but it also swallows an OUTER one: if shutdown is
        itself being cancelled — a lifespan timeout, an enclosing
        `asyncio.timeout` — that CancelledError is delivered to THIS task
        and then discarded, so the enclosing deadline never takes effect.
        `wait` re-raises neither the child's cancellation nor its
        exception, which is what lets the outcome be inspected explicitly
        below instead of guessed at.
        """
        if self.probe_task is not None:
            self.probe_task.cancel()
            await asyncio.wait([self.probe_task])
            if not self.probe_task.cancelled():
                # The task finished on its own, which for an infinite loop
                # means it raised. Retrieving the exception is also what
                # stops asyncio logging "Task exception was never
                # retrieved" from a garbage collector much later, detached
                # from anything that explains it.
                error = self.probe_task.exception()
                if error is not None:
                    _logger.error("event_loop.lag.probe_died", exc_info=error)
            self.probe_task = None

        if self.instrumentor is not None:
            self.instrumentor.uninstrument()
            self.instrumentor = None


def _register_service_info(meter: Meter, service_version: str) -> None:
    """A constant 1 whose labels are the point (spec 7.4).

    The value never changes and means nothing. `service_version` — which
    Prometheus promotes from the resource onto every series — changes the
    moment a new release starts serving, so a dashboard can draw the
    deployment as a marker and put a latency step beside its cause.

    An OBSERVABLE gauge rather than a plain one: a plain gauge set once
    depends on the SDK holding that last value for the life of the
    process, whereas a callback is asked afresh on every collection and
    cannot go stale.
    """

    def observe(options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(1, {"service.version": service_version})

    meter.create_observable_gauge(
        "service.info",
        callbacks=[observe],
        unit="{info}",
        description="Always 1. Carries the running version as a label.",
    )


def _register_pool_metrics(meter: Meter, engine: AsyncEngine) -> None:
    """Connections in use, idle, and the hard ceiling.

    Read straight off the pool object rather than taken from the
    SQLAlchemy instrumentation's own pool metrics, which measure at a
    different moment and would disagree at the edges. One number with one
    source beats two nearly-right ones.

    `db.client.connection.count` with a `state` attribute is the
    OpenTelemetry convention, so this panel works unchanged against a
    service written in another language.

    build_engine pins max_overflow to 0, which is what makes `max` an
    exact ceiling rather than a floor — see its comment in
    infrastructure/db/engine.py.
    """

    pool = engine.pool
    if not isinstance(pool, QueuePool):
        # Only a queueing pool has connections to be saturated. An engine
        # configured with NullPool or StaticPool has no ceiling to report
        # against, and the base Pool class does not expose these counters
        # at all — so registering gauges here would mean inventing numbers.
        # build_engine always produces an AsyncAdaptedQueuePool, which is a
        # QueuePool; this guard is for an engine built some other way.
        _logger.info("db.pool.metrics.skipped", pool_type=type(pool).__name__)
        return

    def observe_count(options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(pool.checkedout(), {"state": "used"})
        yield Observation(pool.checkedin(), {"state": "idle"})

    def observe_max(options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(pool.size())

    meter.create_observable_gauge(
        "db.client.connection.count",
        callbacks=[observe_count],
        unit="{connection}",
        description="Connections currently checked out of, or idle in, the pool.",
    )
    meter.create_observable_gauge(
        "db.client.connection.max",
        callbacks=[observe_max],
        unit="{connection}",
        description="The pool ceiling. Exact, because max_overflow is 0.",
    )


async def _probe_event_loop_lag(histogram: Any, interval_seconds: float) -> None:
    """Sleep a known interval and record how much longer it really took.

    That overshoot IS the lag: the time between the sleep becoming ready
    and the loop getting round to it. On an idle loop it is microseconds.
    When something synchronous blocks — a large JSON parse, a driver
    without an async path, a call that forgot its `await` — it climbs
    immediately, while every other signal still looks fine.

    `loop.time()` rather than `time.perf_counter()` because it is the
    same clock asyncio schedules against, so the subtraction has no
    cross-clock error in it.
    """
    loop = asyncio.get_running_loop()
    while True:
        started = loop.time()
        await asyncio.sleep(interval_seconds)
        lag = loop.time() - started - interval_seconds
        try:
            # Clamped: a clock adjustment can make this microscopically
            # negative, and a negative observation on a histogram is an
            # error the SDK logs rather than a number anyone can use.
            histogram.record(max(lag, 0.0))
        except Exception:
            # Without this the coroutine ends at the first failed record
            # and the task stays done() forever. The symptom is the worst
            # kind in this milestone: `event_loop.lag` simply stops
            # producing points, the panel reads "No data", and a dead
            # detector is indistinguishable from a healthy event loop.
            #
            # `except Exception` and not `BaseException`: CancelledError is
            # a BaseException, so an ordinary shutdown still cancels this
            # loop rather than being caught and logged here.
            _logger.warning("event_loop.lag.record_failed", exc_info=True)


def register_runtime_metrics(
    runtime: OtelRuntime,
    *,
    service_version: str,
    engine: AsyncEngine | None = None,
    event_loop_probe_interval_seconds: float = (
        DEFAULT_EVENT_LOOP_PROBE_INTERVAL_SECONDS
    ),
) -> RuntimeMetrics:
    """Register every instrument and start the event loop probe.

    Must be called from inside a running event loop — the probe task
    needs one — which is why `lifespan` calls it rather than `create_app`.
    """
    meter = runtime.meter_provider.get_meter(METER_NAME)

    _register_service_info(meter, service_version)
    if engine is not None:
        _register_pool_metrics(meter, engine)

    instrumentor = SystemMetricsInstrumentor(config=_PROCESS_METRICS_CONFIG)
    instrumentor.instrument(meter_provider=runtime.meter_provider)

    lag = meter.create_histogram(
        "event_loop.lag",
        unit="s",
        description="How long a ready callback waited for the event loop.",
    )
    return RuntimeMetrics(
        probe_task=asyncio.create_task(
            _probe_event_loop_lag(lag, event_loop_probe_interval_seconds),
            name="event-loop-lag-probe",
        ),
        instrumentor=instrumentor,
    )
