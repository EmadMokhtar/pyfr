"""The SDK wiring, with no network and no globals touched.

Every test here uses build_providers rather than configure_otel. Only the
latter installs the process-global providers, and OpenTelemetry allows that
exactly once per process — a test that did it would poison every test after
it in the same run.
"""

from __future__ import annotations

import httpx
import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.sampling import ParentBased
from opentelemetry.trace import SpanKind

from reference_service.observability.otel import (
    build_providers,
    build_resource,
    build_sampler,
    build_views,
    configure_otel,
    instrument_http_client,
)
from reference_service.observability.slo import (
    HTTP_DURATION_BUCKET_BOUNDARIES,
    SLO_LATENCY_THRESHOLD_SECONDS,
)
from reference_service.settings import OtelSettings, Settings


def _enabled_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="production",
        otel=OtelSettings(enabled=True, endpoint="http://localhost:4317"),
    )


def test_resource_carries_the_three_attributes_the_log_contract_names() -> None:
    resource = build_resource(_enabled_settings(), "1.2.3")

    assert resource.attributes["service.name"] == "reference-service"
    assert resource.attributes["service.version"] == "1.2.3"
    assert resource.attributes["deployment.environment"] == "production"


def test_resource_also_carries_the_current_semconv_environment_key() -> None:
    """Both spellings, so the promote list changing cannot break us.

    grafana/otel-lgtm's Prometheus promotes a fixed list of resource
    attributes to labels. 0.32.1 carries both spellings, but 0.11.11
    carried only `deployment.environment.name` — setting both is what
    makes this survive that list changing underneath us. Spec 7.6's log
    field contract separately names the older spelling.
    """
    resource = build_resource(_enabled_settings(), "1.2.3")

    assert resource.attributes["deployment.environment.name"] == "production"


def test_sampler_is_parent_based() -> None:
    """A request arriving with a sampled parent must stay sampled.

    Otherwise a trace crossing two services is recorded in one and dropped
    in the next, which is worse than not tracing: the gap looks like the
    second service never received the request.
    """
    assert isinstance(build_sampler(0.25), ParentBased)


@pytest.mark.parametrize("ratio", [0.0, 0.5, 1.0])
def test_sampler_accepts_the_whole_configured_range(ratio: float) -> None:
    assert build_sampler(ratio) is not None


def test_the_duration_view_adds_the_slo_bucket_boundary() -> None:
    """Verified fact 3: the SDK default set has no 0.3 boundary."""
    views = build_views()

    duration_views = [
        view
        for view in views
        if getattr(view, "_instrument_name", None) == "http.server.request.duration"
    ]
    assert len(duration_views) == 1

    aggregation = duration_views[0]._aggregation
    assert isinstance(aggregation, ExplicitBucketHistogramAggregation)
    # `_boundaries` is Sequence[float] | None on the SDK's own type, so it
    # is narrowed before use rather than silenced with a type: ignore.
    boundaries = aggregation._boundaries
    assert boundaries is not None
    assert tuple(boundaries) == HTTP_DURATION_BUCKET_BOUNDARIES
    assert SLO_LATENCY_THRESHOLD_SECONDS in boundaries


def test_build_providers_accepts_injected_exporters() -> None:
    """The seam every later task's tests hang off."""
    runtime = build_providers(
        _enabled_settings(),
        "1.2.3",
        span_exporter=InMemorySpanExporter(),
        metric_reader=InMemoryMetricReader(),
    )

    assert runtime.tracer_provider is not None
    assert runtime.meter_provider is not None
    # logs_enabled is false in these settings, so no logger provider.
    assert runtime.logger_provider is None

    runtime.shutdown()


def test_shutdown_is_idempotent() -> None:
    """lifespan's finally block can run after an already-failed startup."""
    runtime = build_providers(
        _enabled_settings(),
        "1.2.3",
        span_exporter=InMemorySpanExporter(),
        metric_reader=InMemoryMetricReader(),
    )

    runtime.shutdown()
    runtime.shutdown()


def test_configure_otel_returns_none_when_disabled() -> None:
    """The default path: no providers, no exporter, no background thread."""
    settings = Settings(_env_file=None, environment="production")  # type: ignore[call-arg]

    assert configure_otel(settings, "1.2.3") is None


async def test_an_instrumented_client_produces_a_client_span() -> None:
    """A request through an instrumented client is a CLIENT span, and its
    method attribute uses the STABLE convention.

    `SimpleSpanProcessor` is what `build_providers` attaches when an
    exporter is injected (see its own comment), so the span is visible in
    the exporter as soon as the request completes — no force_flush needed,
    matching test_db_instrumentation.py's pattern for the same reason.

    `http.request.method`, not `http.method`: matching every other span
    this service emits (see the M2 plan's Verified Fact 2). Were the
    legacy attribute to leak in here, outbound spans could not be queried
    alongside the inbound ones that FastAPIInstrumentor already emits
    under the stable convention.
    """
    span_exporter = InMemorySpanExporter()
    runtime = build_providers(_enabled_settings(), "1.2.3", span_exporter=span_exporter)
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(201, json={})),
        base_url="http://gateway",
    )
    instrument_http_client(client, runtime)

    try:
        await client.post("/authorisations", json={})
    finally:
        await client.aclose()
        runtime.shutdown()

    spans = span_exporter.get_finished_spans()
    assert [span.kind for span in spans] == [SpanKind.CLIENT]
    attributes = spans[0].attributes
    assert attributes is not None
    assert attributes["http.request.method"] == "POST"
    assert "http.method" not in attributes
