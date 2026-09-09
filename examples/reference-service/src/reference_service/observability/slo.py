"""The service level objective, as numbers that code and PromQL both read.

Nothing here imports anything. That is deliberate twice over: the gate in
tests/unit/test_slo_rules.py reads these constants to check the shipped
Prometheus rules agree with them, and M7 replaces the literals below with
cookiecutter variables. Both are simpler against a file with no imports.

Spec 7.5 fixes the defaults: 99.9% of requests succeed, 99.9% complete
within 300ms, measured over a rolling 30 days.
"""

from __future__ import annotations

# Fraction of requests that must not return 5xx, over the rolling window.
SLO_AVAILABILITY_TARGET = 0.999

# The window the objective is measured over.
SLO_WINDOW_DAYS = 30

# A request finishing within this many seconds counts as fast. This value
# MUST also appear in HTTP_DURATION_BUCKET_BOUNDARIES below — see the
# comment there — and as the `le` label in the latency recording rules in
# ops/prometheus/rules/slo.yml. tests/unit/test_slo.py checks the first,
# tests/unit/test_slo_rules.py checks the second.
SLO_LATENCY_THRESHOLD_SECONDS = 0.3

# How much failure the objective permits. Rounded on purpose: 1 - 0.999
# is 0.0010000000000000009 in binary floating point, and the burn-rate
# alerts multiply this by up to 14.4, so the drift would show up in the
# rendered alert thresholds.
ERROR_BUDGET = round(1.0 - SLO_AVAILABILITY_TARGET, 10)

# Explicit bucket boundaries for http.server.request.duration, in seconds.
#
# The OpenTelemetry SDK's own defaults are
#   0.005 0.01 0.025 0.05 0.075 0.1 0.25 0.5 0.75 1 2.5 5 7.5 10
# which steps straight from 0.25 to 0.5 and so has NO boundary at the
# latency threshold. Prometheus can only count requests faster than a
# boundary that exists: without adding it here, the series
# http_server_request_duration_seconds_bucket{le="0.3"} is never produced
# and the latency SLI is not merely inaccurate, it is uncomputable.
#
# Every other boundary is the SDK default, kept as-is so the numbers stay
# comparable with any other OpenTelemetry service in the same Grafana.
HTTP_DURATION_BUCKET_BOUNDARIES = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    SLO_LATENCY_THRESHOLD_SECONDS,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
)

# Routes that count towards neither SLI. Kubernetes probes a readiness
# endpoint every couple of seconds forever; counted, they would swamp real
# traffic and report a healthy objective for a service that is failing
# every request a user actually makes.
SLI_EXCLUDED_ROUTES = ("/healthz", "/readyz", "/startupz")


def excluded_routes_pattern() -> str:
    """The `http_route!~"..."` matcher body used by every SLI rule.

    Prometheus anchors label matchers at both ends already, so plain
    alternation is exact and no `^`/`$` is needed — adding them would be
    matched literally by some Prometheus versions rather than ignored.
    """
    return "|".join(SLI_EXCLUDED_ROUTES)
