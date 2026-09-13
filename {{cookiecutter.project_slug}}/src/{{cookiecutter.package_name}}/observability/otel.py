"""OpenTelemetry SDK wiring: resource, providers, exporters, instrumentation.

Everything the SDK needs is built here and nowhere else, so the rest of the
service never imports `opentelemetry` — a rule the import-linter contracts
enforce for domain/ and services/.

Two functions build providers. `build_providers` is pure construction and
takes exporter overrides, which is what the tests use. `configure_otel`
wraps it and additionally installs the process-global providers, so that
application code written later can call `trace.get_tracer(__name__)` and
get a real tracer. OpenTelemetry permits that global installation exactly
once per process, which is why no test calls `configure_otel` twice.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

import httpx
from fastapi import FastAPI
from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
from opentelemetry.instrumentation.httpx import HTTPXClientInstrumentor
{%- if cookiecutter.cache == "redis" %}
from opentelemetry.instrumentation.redis import RedisInstrumentor
{%- endif %}
{%- if cookiecutter.database == "postgres" %}
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
{%- endif %}
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import (
    BatchSpanProcessor,
    SimpleSpanProcessor,
    SpanExporter,
)
from opentelemetry.sdk.trace.sampling import ParentBased, Sampler, TraceIdRatioBased
{%- if cookiecutter.database == "postgres" %}
from sqlalchemy.ext.asyncio import AsyncEngine
{%- endif %}

from {{ cookiecutter.package_name }}.observability.slo import HTTP_DURATION_BUCKET_BOUNDARIES
from {{ cookiecutter.package_name }}.settings import Settings

# Selects the STABLE HTTP semantic conventions. Without it the FastAPI
# instrumentation emits the legacy set — `http.server.duration` in
# milliseconds with `http.method` and `http.status_code` — instead of the
# `http.server.request.duration` in seconds with `http.route`,
# `http.request.method` and `http.response.status_code` that spec 7.2
# requires and that every dashboard and SLO rule in ops/ queries.
#
# This is read on the FIRST instrument*() call in the process and cached
# for the life of the process; setting it afterwards changes nothing.
# Verified directly: instrumenting once without it and then setting it
# still produced the legacy names. So it is applied by
# _opt_in_to_stable_semconv() below, called at the top of BOTH
# instrumentation entry points rather than left to the environment —
# a developer running `just dev` must not get different metric names from
# the compose stack.
_STABLE_SEMCONV_ENV_VAR = "OTEL_SEMCONV_STABILITY_OPT_IN"
_STABLE_SEMCONV_VALUE = "http"

# Traced and measured for nobody's benefit: an orchestrator probes these
# every couple of seconds forever, so left in they become most of what the
# tracing backend stores and most of what it bills for. The same three
# paths api/middleware.py already keeps out of the access log.
#
# The SLI recording rules in ops/prometheus/rules/slo.yml ALSO exclude
# these routes, which is deliberate duplication rather than an oversight:
# this setting is about cost, and an operator may reasonably widen or
# narrow it, while the objective's definition must not change when they do.
_UNTRACED_PATHS = "healthz,readyz,startupz"


def _opt_in_to_stable_semconv() -> None:
    """Ask for the stable HTTP conventions before anything instruments.

    `setdefault`, not assignment: an operator who has deliberately set this
    variable — to add `database` alongside `http`, say — keeps their value.
    """
    os.environ.setdefault(_STABLE_SEMCONV_ENV_VAR, _STABLE_SEMCONV_VALUE)


def _is_insecure(endpoint: str) -> bool:
    """Plain http:// means no TLS; anything else is treated as TLS.

    The gRPC exporters take this as a separate flag rather than reading the
    scheme themselves, and defaulting it wrongly fails at connect time on a
    background thread rather than at startup.
    """
    return urlsplit(endpoint).scheme == "http"


def build_resource(settings: Settings, service_version: str) -> Resource:
    """The attributes every span, metric and log record carries.

    `deployment.environment` and `deployment.environment.name` are both set
    to the same value on purpose. The first is what spec 7.6's log field
    contract names and what observability/logging.py already emits. The
    second is the current semantic convention. Which of the two Prometheus
    promotes to a label depends on the image version — 0.11.11 promoted
    only the second, 0.32.1 promotes both — so setting both is what makes
    this survive that list changing underneath us.
    """
    return Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": service_version,
            "deployment.environment": settings.environment,
            "deployment.environment.name": settings.environment,
        }
    )


def build_sampler(sample_ratio: float) -> Sampler:
    """Parent-based ratio sampling.

    Parent-based is the part that matters. A request arriving with a
    sampled parent is always recorded regardless of the ratio, so a trace
    crossing several services is never half-recorded — a gap in the middle
    of a distributed trace reads as "the next service never got the
    request", which is a much more alarming thing to see than no trace.
    The ratio then decides only for requests whose trace starts here.
    """
    return ParentBased(root=TraceIdRatioBased(sample_ratio))


def build_views() -> tuple[View, ...]:
    """Metric views. One is load-bearing for the latency SLO.

    See observability/slo.py's comment on HTTP_DURATION_BUCKET_BOUNDARIES:
    the SDK's default boundaries step from 0.25s straight to 0.5s, so the
    series http_server_request_duration_seconds_bucket{le="0.3"} would
    never exist and the latency objective could not be computed at all.
    """
    return (
        View(
            instrument_name="http.server.request.duration",
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=HTTP_DURATION_BUCKET_BOUNDARIES
            ),
        ),
        View(
            instrument_name="event_loop.lag",
            aggregation=ExplicitBucketHistogramAggregation(
                # Finer at the bottom than the SDK default, which starts at
                # 5ms. A loop lagging 5ms is healthy; the interesting
                # question is whether it is lagging 1ms or 100ms, and the
                # default boundaries cannot tell those apart usefully.
                boundaries=(
                    0.001,
                    0.0025,
                    0.005,
                    0.01,
                    0.025,
                    0.05,
                    0.1,
                    0.25,
                    0.5,
                    1.0,
                    2.5,
                    5.0,
                )
            ),
        ),
    )


@dataclass
class OtelRuntime:
    """The providers, held so `lifespan` can flush and close them."""

    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    logger_provider: LoggerProvider | None
    _shut_down: bool = False

    def shutdown(self) -> None:
        """Flush and close every provider. Safe to call more than once.

        Idempotence is not decoration: `lifespan`'s finally block runs even
        when startup raised partway, and the SDK's own shutdown methods log
        a warning when called twice. One flag here keeps that noise out of
        the shutdown path of a process that is already having a bad day.

        Order matters. Logs go last because the other two providers can
        emit log records while shutting down, and a closed logger provider
        would drop exactly the lines explaining why shutdown was unhappy.
        """
        if self._shut_down:
            return
        self._shut_down = True
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()
        if self.logger_provider is not None:
            self.logger_provider.shutdown()


def build_providers(
    settings: Settings,
    service_version: str,
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> OtelRuntime:
    """Construct the providers. Installs nothing globally.

    The two keyword arguments exist for the tests, which substitute
    in-memory exporters so the suite needs no collector and no network.
    Production passes neither and gets the OTLP exporters.
    """
    endpoint = settings.otel.endpoint or ""
    insecure = _is_insecure(endpoint)
    resource = build_resource(settings, service_version)

    tracer_provider = TracerProvider(
        resource=resource, sampler=build_sampler(settings.otel.sample_ratio)
    )
    tracer_provider.add_span_processor(
        # SimpleSpanProcessor when an exporter is injected, Batch otherwise.
        # This is not a cosmetic difference. BatchSpanProcessor exports on
        # its own background timer, so a test that makes a request and then
        # reads the exporter sees NOTHING. Two kinds of test break on that,
        # and the second kind is worse: a test asserting a span EXISTS
        # fails loudly, but a test asserting NO span exists (the health
        # endpoint exclusion) passes vacuously and can never fail.
        #
        # The injection argument exists only for tests, so binding it to a
        # synchronous processor keeps that trap shut by construction rather
        # than relying on every future test author to remember a flush.
        SimpleSpanProcessor(span_exporter)
        if span_exporter is not None
        else BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=insecure))
    )

    reader = (
        metric_reader
        if metric_reader is not None
        else PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=insecure),
            export_interval_millis=settings.otel.metric_export_interval_ms,
        )
    )
    meter_provider = MeterProvider(
        resource=resource, metric_readers=[reader], views=build_views()
    )

    logger_provider: LoggerProvider | None = None
    if settings.otel.logs_enabled:
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=endpoint, insecure=insecure)
            )
        )

    return OtelRuntime(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
    )


def configure_otel(settings: Settings, service_version: str) -> OtelRuntime | None:
    """Build the providers and install them globally, or do nothing.

    Returns None when telemetry is off, which is the default. On that path
    this function imports no exporter, opens no socket and starts no
    thread: a generated service that wants none of this pays nothing.

    The global installation is what makes `trace.get_tracer(__name__)` work
    in code written later, in a service generated from this template, that
    wants a manual span around something this milestone knows nothing
    about. It happens once per process; tests use build_providers instead.
    """
    if not settings.otel.enabled:
        return None

    runtime = build_providers(settings, service_version)
    trace.set_tracer_provider(runtime.tracer_provider)
    metrics.set_meter_provider(runtime.meter_provider)
    if runtime.logger_provider is not None:
        set_logger_provider(runtime.logger_provider)
    return runtime


def instrument_fastapi(app: FastAPI, runtime: OtelRuntime) -> None:
    """Add the server span and the RED metrics to one application.

    Call this AFTER the application's own middleware has been added.
    Starlette makes the most recently added middleware the outermost one,
    so instrumenting last puts the OpenTelemetry middleware outside
    AccessLogMiddleware — which is what allows the access log record to
    carry the trace_id of the span the request is running in. Instrument
    first and the span does not exist yet when that line is written, so
    every access log entry loses its link to its own trace.
    """
    _opt_in_to_stable_semconv()
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=runtime.tracer_provider,
        meter_provider=runtime.meter_provider,
        excluded_urls=_UNTRACED_PATHS,
    )
{%- if cookiecutter.database == "postgres" %}


def instrument_database(engine: AsyncEngine, runtime: OtelRuntime) -> None:
    """Add a span per statement to an async engine.

    `engine.sync_engine`, not `engine`: SQLAlchemyInstrumentor attaches to
    the synchronous core event system and does not accept an AsyncEngine
    at all. The async engine is a thin wrapper over exactly that core, so
    instrumenting the inner object covers every statement the outer one
    runs.

    Deliberately no meter_provider argument. The instrumentation's own
    connection-pool metrics duplicate the ones observability/metrics.py
    registers from the pool object directly, and the two disagree at the
    edges because they count at different moments. One source for a number
    is worth more than two nearly-right ones.
    """
    _opt_in_to_stable_semconv()
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine, tracer_provider=runtime.tracer_provider
    )
{%- endif %}


def instrument_http_client(client: httpx.AsyncClient, runtime: OtelRuntime) -> None:
    """Add a CLIENT span per outbound request to one client.

    `instrument_client`, not the global `instrument()`: this attaches to
    the single instance the composition root built, so a service running
    with APP_OTEL__ENABLED false has nothing patched anywhere. The global
    form would monkey-patch httpx itself, which is both wider than we
    need and impossible to undo cleanly in tests.

    `_opt_in_to_stable_semconv()` first, for the reason spelled out in the
    M2 plan: the opt-in is read on the FIRST instrument*() call in a
    process and cached forever, so every instrumentor must be preceded by
    it or the first one to run decides for all of them.
    """
    _opt_in_to_stable_semconv()
    HTTPXClientInstrumentor.instrument_client(
        client, tracer_provider=runtime.tracer_provider
    )
{%- if cookiecutter.cache == "redis" %}


def instrument_redis(runtime: OtelRuntime) -> None:
    """Spans for every Redis command.

    A GLOBAL instrumentor, unlike instrument_http_client's per-client
    attachment: redis-py has no per-client hook, so this patches the
    library. `RedisInstrumentor` is also a process-wide SINGLETON
    (`BaseInstrumentor.__new__` always returns the same instance), so only
    the FIRST call in a process binds `tracer_provider` — every later call
    is a no-op regardless of which provider it is given.

    A raw double call would already be harmless without this guard:
    `RedisInstrumentor.instrument()` calls `super().instrument()`, and
    `BaseInstrumentor.instrument()` itself checks
    `_is_instrumented_by_opentelemetry` and returns `None` before it could
    double-patch. What the guard here actually earns its place for is
    quieter test output: without it, every one of the many app instances
    the test suite builds in one process would re-trigger that base-class
    check and log a `WARNING: Attempting to instrument while already
    instrumented` — this short-circuits before that call, so the log stays
    clean.

    Worth having despite the cache being optional: the span is how you find
    out that a "fast" cache read is actually costing 40ms, which is the
    exact failure a fail-open cache hides from every other signal — the
    request still succeeds, so no error rate moves.

    No `_opt_in_to_stable_semconv()` call here, unlike the instrumentors
    above: redis-py has no legacy/stable HTTP semantic-convention split to
    opt into — that env var governs only the HTTP attribute set, and a
    Redis span's attributes (`db.system`, `db.statement`) are unaffected
    by it either way.

    Deliberately no `opentelemetry-instrumentation-botocore` counterpart
    beside this function. Task 12's Step 1 measured whether that
    instrumentor sees `aioboto3`'s S3 calls at all: instrumenting, then
    running ListBuckets, CreateBucket, PutObject and GetObject through an
    `aioboto3.Session` against a real MinIO container produced zero spans
    on an `InMemorySpanExporter`/`ConsoleSpanExporter`, even though
    `is_instrumented_by_opentelemetry` reported `True` and every call
    itself succeeded. `aioboto3` runs on `aiobotocore`, which replaces the
    parts of `botocore`'s client machinery the instrumentor patches with
    async equivalents the instrumentor's hooks never see. Shipping that
    instrumentation would mean an S3 span that silently never appears,
    which is worse than no span: a dashboard or trace search built against
    it would read as "S3 calls are always fast" rather than "S3 calls are
    not observed". See the Task 12 report for the full probe transcript.
    """
    instrumentor = RedisInstrumentor()
    if instrumentor.is_instrumented_by_opentelemetry:
        return
    instrumentor.instrument(tracer_provider=runtime.tracer_provider)
{%- endif %}
