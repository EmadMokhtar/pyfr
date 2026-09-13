"""The whole chain, once: app -> OTLP -> Prometheus -> rules -> Grafana.

Every other test in this milestone checks one link. This one checks that
they are actually connected, which is the failure the others cannot see:
each half correct, the join wrong, and every dashboard empty.

Slow — roughly a minute — and container-bound, so it lives in the
integration tier.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from testcontainers.core.container import DockerContainer

# The structured wait strategy, not wait_for_logs: passing a string
# predicate to that function is deprecated and warns, which this project's
# filterwarnings = ["error"] turns into a test error.
from testcontainers.core.wait_strategies import LogMessageWaitStrategy

from {{ cookiecutter.package_name }}.main import create_app
from {{ cookiecutter.package_name }}.observability.otel import (
    build_providers,
    instrument_fastapi,
)
from {{ cookiecutter.package_name }}.settings import Settings
from tests.compose_images import compose_image

pytestmark = pytest.mark.integration

LGTM_IMAGE = compose_image("lgtm")
OPS = Path(__file__).resolve().parents[2] / "ops"
EXPECTED_DASHBOARD_UIDS = {"pyfr-service-health", "pyfr-slo", "pyfr-runtime"}
READY_LINE = "The OpenTelemetry collector and the Grafana LGTM stack are up"


def _get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
        return json.loads(response.read())


@pytest.fixture(scope="module")
def stack() -> Iterator[DockerContainer]:
    """The same image and mounts the o11y compose profile uses.

    Kept in step with compose.yaml by hand. If a mount is added there and
    not here, this test stops covering it — which is why the mounts below
    name the same four paths in the same order as the compose service.
    Ports are NOT the same: testcontainers maps to random host ports, so
    they are read back through get_exposed_port rather than fixed.
    """
    container = (
        DockerContainer(LGTM_IMAGE)
        .with_exposed_ports(3000, 4317, 9090)
        .with_volume_mapping(
            str(OPS / "prometheus" / "prometheus.yaml"),
            "/otel-lgtm/prometheus.yaml",
            "ro",
        )
        .with_volume_mapping(
            str(OPS / "prometheus" / "rules"), "/otel-lgtm/rules", "ro"
        )
        .with_volume_mapping(
            str(
                OPS / "grafana" / "provisioning" / "dashboards" / "pyfr-dashboards.yaml"
            ),
            "/otel-lgtm/grafana/conf/provisioning/dashboards/pyfr-dashboards.yaml",
            "ro",
        )
        .with_volume_mapping(
            str(OPS / "grafana" / "dashboards"), "/otel-lgtm/pyfr-dashboards", "ro"
        )
    )
    container.waiting_for(LogMessageWaitStrategy(READY_LINE).with_startup_timeout(240))
    with container as started:
        yield started


@pytest.fixture(scope="module")
def prometheus_url(stack: DockerContainer) -> str:
    return f"http://{stack.get_container_host_ip()}:{stack.get_exposed_port(9090)}"


@pytest.fixture(scope="module")
def grafana_url(stack: DockerContainer) -> str:
    return f"http://{stack.get_container_host_ip()}:{stack.get_exposed_port(3000)}"


def test_prometheus_loaded_our_rule_groups(prometheus_url: str) -> None:
    """The image's own config has no rule_files key at all.

    If ops/prometheus/prometheus.yaml stops being mounted, or loses its
    rule_files entry, every SLO recording rule quietly ceases to exist —
    and every SLO dashboard panel goes blank rather than erroring.
    """
    payload = _get_json(f"{prometheus_url}/api/v1/rules")

    groups = {group["name"] for group in payload["data"]["groups"]}
    assert {"slo_sli_short", "slo_sli_long", "slo_burn_alerts"} <= groups

    unhealthy = [
        rule["name"]
        for group in payload["data"]["groups"]
        for rule in group["rules"]
        if rule["type"] == "recording" and rule["health"] not in ("ok", "unknown")
    ]
    assert unhealthy == [], f"recording rules failed to evaluate: {unhealthy}"


def test_grafana_provisioned_all_three_dashboards(grafana_url: str) -> None:
    """Anonymous admin access is on in this image, so no credentials."""
    dashboards = _get_json(f"{grafana_url}/api/search?type=dash-db")

    assert EXPECTED_DASHBOARD_UIDS <= {dashboard["uid"] for dashboard in dashboards}


def test_a_real_request_reaches_prometheus_with_the_stable_names(
    stack: DockerContainer, prometheus_url: str, settings: Settings
) -> None:
    """The join every other test takes on trust.

    Proves three things at once that are each invisible in isolation: the
    semantic convention opt-in survived into the exported data, the
    histogram view's extra boundary survived the round trip, and the
    resource attributes were promoted to the labels the rules match on.
    """
    endpoint = f"http://{stack.get_container_host_ip()}:{stack.get_exposed_port(4317)}"
    enabled = settings.model_copy(
        update={
            "otel": settings.otel.model_copy(
                update={
                    "enabled": True,
                    "endpoint": endpoint,
                    "metric_export_interval_ms": 1000,
                }
            )
        }
    )
    runtime = build_providers(enabled, "1.2.3")
    # `settings`, not `enabled`, on purpose. `with TestClient(app)` runs the
    # lifespan, and an enabled configuration would make create_app build a
    # SECOND set of providers behind the one just built here and instrument
    # the app twice. Do not "fix" this to `enabled`.
    app: FastAPI = create_app(settings)
    instrument_fastapi(app, runtime)

    try:
        with TestClient(app) as client:
            for _ in range(5):
                client.get("/api/v1/orders/does-not-exist")
        runtime.meter_provider.force_flush()

        # Prometheus ingests over OTLP through the collector's batch
        # processor, so the sample is not queryable the instant it is
        # pushed. Poll rather than sleep a guessed interval.
        deadline = time.monotonic() + 90
        series: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            payload = _get_json(
                f"{prometheus_url}/api/v1/query"
                f"?query=http_server_request_duration_seconds_count"
            )
            series = payload["data"]["result"]
            if series:
                break
            time.sleep(2)

        assert series, "no http.server.request.duration reached Prometheus"

        labels = series[0]["metric"]
        assert labels["job"] == "{{ cookiecutter.project_slug }}"
        assert labels["service_version"] == "1.2.3"
        assert "http_route" in labels, "legacy semantic conventions leaked in"
        assert "http_target" not in labels
    finally:
        runtime.shutdown()


def test_the_slo_latency_bucket_exists_in_prometheus(prometheus_url: str) -> None:
    """The single series the entire latency objective rests on.

    Without observability/otel.py's histogram view the boundaries jump
    0.25 -> 0.5, this series never exists, and every latency rule
    evaluates to nothing at all — silently, because an empty PromQL
    result is not an error.
    """
    payload = _get_json(
        f"{prometheus_url}/api/v1/query"
        f'?query=http_server_request_duration_seconds_bucket{% raw %}{{le="0.3"}}{% endraw %}'
    )

    assert payload["data"]["result"], 'no bucket with le="0.3"'
