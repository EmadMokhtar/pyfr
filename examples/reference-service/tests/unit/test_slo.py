"""The SLO numbers are only useful if the histogram can express them."""

import pytest

from reference_service.observability.slo import (
    ERROR_BUDGET,
    HTTP_DURATION_BUCKET_BOUNDARIES,
    SLI_EXCLUDED_ROUTES,
    SLO_AVAILABILITY_TARGET,
    SLO_LATENCY_THRESHOLD_SECONDS,
    excluded_routes_pattern,
)


def test_the_latency_threshold_is_an_actual_bucket_boundary() -> None:
    """Without this the latency SLI cannot be computed at all.

    The SDK's default boundaries jump 0.25 -> 0.5, so `le="0.3"` would
    never exist as a series and the PromQL ratio in ops/prometheus/rules/
    slo.yml would silently return nothing. `histogram_quantile` is not a
    substitute: it interpolates inside a bucket, which answers "what is
    the p95 latency", not "what fraction of requests beat 300ms".
    """
    assert SLO_LATENCY_THRESHOLD_SECONDS in HTTP_DURATION_BUCKET_BOUNDARIES


def test_bucket_boundaries_are_sorted_and_unique() -> None:
    """The SDK requires strictly increasing boundaries and raises if not."""
    boundaries = list(HTTP_DURATION_BUCKET_BOUNDARIES)
    assert boundaries == sorted(boundaries)
    assert len(boundaries) == len(set(boundaries))


def test_error_budget_is_the_complement_of_the_target() -> None:
    # pytest.approx, not ==: in binary floating point `1.0 - 0.999` is
    # 0.0010000000000000009, so an exact comparison against the ROUNDED
    # constant fails. Asserting both `== 1.0 - target` exactly and
    # `== 0.001` exactly is self-contradictory — the rounding is the whole
    # reason the second holds and the first does not.
    assert ERROR_BUDGET == pytest.approx(1.0 - SLO_AVAILABILITY_TARGET)
    # The alert thresholds multiply this by burn rates up to 14.4, so the
    # module rounds it rather than letting the drift compound.
    assert ERROR_BUDGET == 0.001


def test_health_endpoints_are_excluded_from_the_objective() -> None:
    """A probe every two seconds otherwise dwarfs real traffic.

    With /readyz counted, a service serving ten real requests a minute
    beside 1800 readiness probes reports a 99.9% success rate no matter
    how badly the real ten are doing.
    """
    assert set(SLI_EXCLUDED_ROUTES) == {"/healthz", "/readyz", "/startupz"}


def test_the_exclusion_pattern_is_anchored_promql() -> None:
    """Prometheus label matchers are implicitly fully anchored, so the
    pattern must not accidentally match a real route that CONTAINS one of
    these names — but it must match each excluded route exactly."""
    pattern = excluded_routes_pattern()
    assert pattern == "/healthz|/readyz|/startupz"
