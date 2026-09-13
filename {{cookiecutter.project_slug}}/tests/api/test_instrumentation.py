"""A real request through the real app, with in-memory exporters.

No collector, no network, no globals: build_providers takes the exporters
and instrument_fastapi is handed the result.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from {{ cookiecutter.package_name }}.main import create_app
from {{ cookiecutter.package_name }}.observability.otel import (
    OtelRuntime,
    build_providers,
    instrument_fastapi,
)
from {{ cookiecutter.package_name }}.observability.slo import SLO_LATENCY_THRESHOLD_SECONDS
from {{ cookiecutter.package_name }}.settings import Settings


@pytest.fixture
def exporters() -> tuple[InMemorySpanExporter, InMemoryMetricReader]:
    return InMemorySpanExporter(), InMemoryMetricReader()


@pytest.fixture
def runtime(
    settings: Settings,
    exporters: tuple[InMemorySpanExporter, InMemoryMetricReader],
) -> Iterator[OtelRuntime]:
    span_exporter, metric_reader = exporters
    enabled = settings.model_copy(
        update={
            "otel": settings.otel.model_copy(
                update={"enabled": True, "endpoint": "http://localhost:4317"}
            )
        }
    )
    built = build_providers(
        enabled, "1.2.3", span_exporter=span_exporter, metric_reader=metric_reader
    )
    yield built
    built.shutdown()


@pytest.fixture
def instrumented_client(
    settings: Settings, runtime: OtelRuntime
) -> Iterator[TestClient]:
    app = create_app(settings)
    instrument_fastapi(app, runtime)
    with TestClient(app) as client:
        yield client


def _metric_names(reader: InMemoryMetricReader) -> set[str]:
    # get_metrics_data() is typed MetricsData | None — None when nothing
    # has been recorded — so it is narrowed rather than silenced.
    data = reader.get_metrics_data()
    assert data is not None, "the reader collected nothing at all"
    return {
        metric.name
        for resource_metrics in data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }


def test_a_request_produces_a_server_span_naming_the_route_template(
    instrumented_client: TestClient,
    exporters: tuple[InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    """The template, never the raw path.

    Same reasoning as the access log's http.route field: a raw path makes
    every order identifier its own distinct value, which is the standard
    way to overwhelm a tracing backend.
    """
    span_exporter, _ = exporters

    instrumented_client.get("/api/v1/orders/does-not-exist")

    routes = {
        span.attributes["http.route"]
        for span in span_exporter.get_finished_spans()
        if span.attributes and "http.route" in span.attributes
    }
    assert "/api/v1/orders/{order_id}" in routes


def test_metrics_use_the_stable_semantic_conventions(
    instrumented_client: TestClient,
    exporters: tuple[InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    """Verified fact 2 — this does NOT happen by default.

    Without the opt-in the instrumentation emits `http.server.duration` in
    milliseconds, and every PromQL expression in ops/ queries a series
    that would then never exist.
    """
    _, metric_reader = exporters

    instrumented_client.get("/api/v1/orders/does-not-exist")

    names = _metric_names(metric_reader)
    assert "http.server.request.duration" in names
    assert "http.server.duration" not in names, "legacy convention leaked in"


def test_the_duration_histogram_has_the_slo_bucket(
    instrumented_client: TestClient,
    exporters: tuple[InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    """End to end proof that build_views reached the real instrument."""
    _, metric_reader = exporters

    instrumented_client.get("/api/v1/orders/does-not-exist")

    data = metric_reader.get_metrics_data()
    assert data is not None, "the reader collected nothing at all"

    boundaries: list[float] = []
    for resource_metrics in data.resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name != "http.server.request.duration":
                    continue
                for point in metric.data.data_points:
                    # A histogram instrument yields HistogramDataPoint, but
                    # the union covers every point type, so narrow rather
                    # than assume.
                    bounds = getattr(point, "explicit_bounds", None)
                    assert bounds is not None, "not a histogram data point"
                    boundaries = list(bounds)

    assert SLO_LATENCY_THRESHOLD_SECONDS in boundaries


def test_health_endpoints_produce_no_spans(
    instrumented_client: TestClient,
    exporters: tuple[InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    """A readiness probe every two seconds is not a trace anyone wants.

    The real request at the end is load-bearing, not padding. A test that
    only asserts an absence passes just as happily against an exporter
    that never receives anything at all. Proving the exporter WOULD have
    caught a span is what makes the absence mean something.
    """
    span_exporter, _ = exporters

    instrumented_client.get("/healthz")
    instrumented_client.get("/readyz")

    assert span_exporter.get_finished_spans() == ()

    instrumented_client.get("/api/v1/orders/does-not-exist")

    assert span_exporter.get_finished_spans(), (
        "the exporter captured nothing at all, so the assertion above proved nothing"
    )


def test_create_app_leaves_the_app_uninstrumented_when_otel_is_off(
    settings: Settings,
) -> None:
    """The default path stays exactly what M1 shipped."""
    app = create_app(settings)

    assert getattr(app, "_is_instrumented_by_opentelemetry", False) is False


def test_create_app_instruments_and_shuts_down_when_otel_is_on(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, runtime: OtelRuntime
) -> None:
    """`configure_otel` is substituted so no OTLP exporter is constructed."""
    monkeypatch.setattr(
        "{{ cookiecutter.package_name }}.main.configure_otel",
        lambda _settings, _version: runtime,
    )

    app = create_app(settings)
    with TestClient(app) as client:
        client.get("/api/v1/orders/does-not-exist")
        assert app.state.otel is runtime

    assert runtime._shut_down is True, "lifespan must flush telemetry on exit"
