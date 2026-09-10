"""The SDK wiring, with no network and no globals touched.

Every test here uses build_providers rather than configure_otel. Only the
latter installs the process-global providers, and OpenTelemetry allows that
exactly once per process — a test that did it would poison every test after
it in the same run.
"""

from __future__ import annotations

from collections.abc import Iterator

import httpx
import pytest
from opentelemetry.instrumentation._semconv import (
    _OpenTelemetrySemanticConventionStability,
)
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.sampling import ParentBased
from opentelemetry.trace import SpanKind

from reference_service.observability.otel import (
    _STABLE_SEMCONV_ENV_VAR,
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


@pytest.fixture
def _reset_semconv_stability_cache(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Force the SDK to re-decide the HTTP semantic-convention mode.

    `_OpenTelemetrySemanticConventionStability._initialize()` (in the
    `opentelemetry-instrumentation` package) reads the
    `OTEL_SEMCONV_STABILITY_OPT_IN` environment variable exactly ONCE per
    process and then sets its own `_initialized` flag so every later call
    is a no-op that returns the first decision, forever. Under `just
    test`, `tests/api/test_instrumentation.py` calls `instrument_fastapi`
    (which also calls `_opt_in_to_stable_semconv()`) before this file
    even collects, on pytest's default alphabetical module order
    (`tests/api/` sorts before `tests/unit/`) — so by the time
    `test_an_instrumented_client_produces_a_client_span` below runs, the
    decision is ALREADY cached as "stable", regardless of whether
    `instrument_http_client` remembers to opt in itself. A test that
    reads `http.request.method` under those conditions passes even if
    the opt-in call in `instrument_http_client` were deleted — a guard
    that cannot fail is not a guard.

    This fixture resets both places that decision lives, so the test
    below observes the SAME "nothing has opted in yet" state regardless
    of what ran before it in the same process:

    - `_OpenTelemetrySemanticConventionStability._initialized` and its
      `_OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING` dict. These are PRIVATE
      attributes (leading underscore on the class, and on the
      `_semconv.py` module it lives in) of a third-party package we do
      not own — there is no public API to un-decide this, because the
      SDK's own contract is that the decision is made once and never
      revisited. Reaching in here is deliberate: if a future release of
      `opentelemetry-instrumentation` renames `_initialized` or replaces
      the mapping with something else, this fixture raises
      `AttributeError` at test setup — loudly, immediately, and pointing
      straight back at this comment — rather than silently leaving the
      mutation guard below unable to fail.
    - The `OTEL_SEMCONV_STABILITY_OPT_IN` environment variable itself,
      via `monkeypatch.delenv` rather than `os.environ.pop`: `_opt_in_to_
      stable_semconv()` sets it with `setdefault`, which is a no-op once
      any earlier test has already set it, so without clearing it here
      the "opt-in never happened" state we are trying to reproduce would
      still read a stale "http" left behind by that earlier test.
      `monkeypatch` restores whatever value (or absence) it found, even
      if this test fails partway through.

    Only the two SDK-private attributes need manual restoration below —
    `monkeypatch` already reverses the environment-variable change on its
    own once this fixture's consumer finishes, which is what keeps this
    reset from leaking into every test that runs after it in the same
    session.
    """
    stability = _OpenTelemetrySemanticConventionStability
    initialized_before = stability._initialized
    mapping_before = dict(stability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING)

    monkeypatch.delenv(_STABLE_SEMCONV_ENV_VAR, raising=False)
    stability._initialized = False
    stability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING = {}
    try:
        yield
    finally:
        stability._initialized = initialized_before
        stability._OTEL_SEMCONV_STABILITY_SIGNAL_MAPPING = mapping_before


async def test_an_instrumented_client_produces_a_client_span(
    _reset_semconv_stability_cache: None,
) -> None:
    """A request through an instrumented client is a CLIENT span, and its
    method attribute uses the STABLE convention — genuinely, not by the
    accident of test execution order.

    `SimpleSpanProcessor` is what `build_providers` attaches when an
    exporter is injected (see its own comment), so the span is visible in
    the exporter as soon as the request completes — no force_flush needed,
    matching test_db_instrumentation.py's pattern for the same reason.

    `http.request.method`, not `http.method`: matching every other span
    this service emits (see the M2 plan's Verified Fact 2). Were the
    legacy attribute to leak in here, outbound spans could not be queried
    alongside the inbound ones that FastAPIInstrumentor already emits
    under the stable convention.

    The `_reset_semconv_stability_cache` fixture is what makes that
    assertion mean something: without it, an earlier-running test module
    may already have locked the process-wide semconv decision to
    "stable" before this test ever runs, and the assertion below would
    pass even if `instrument_http_client` stopped calling
    `_opt_in_to_stable_semconv()` entirely. See that fixture's docstring
    for the mechanism, and this task's report for the mutation check that
    proved it: deleting the opt-in call from `instrument_http_client`
    makes this exact test fail, with the fixture in place.
    """
    span_exporter = InMemorySpanExporter()
    runtime = build_providers(
        _enabled_settings(),
        "1.2.3",
        span_exporter=span_exporter,
        metric_reader=InMemoryMetricReader(),
    )
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
