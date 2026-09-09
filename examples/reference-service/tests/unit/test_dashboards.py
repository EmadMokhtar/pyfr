"""Structural checks on the dashboard JSON.

These cannot tell you a dashboard is USEFUL. They can tell you it will
load, point at a datasource that exists, and not hard-code a service name
— which are the three ways a provisioned dashboard fails silently, showing
an empty panel rather than an error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

DASHBOARD_DIR = Path(__file__).resolve().parents[2] / "ops" / "grafana" / "dashboards"
EXPECTED_UIDS = {"pyfr-service-health", "pyfr-slo", "pyfr-runtime"}


# Parametrise over PATHS, not parsed dictionaries. Two reasons, both real:
# parametrising over the parsed dict puts the whole ~4KB JSON blob into
# every test id, which makes `pytest -v` unreadable and `-k` unusable; and
# parsing at COLLECTION time means one malformed file errors the entire
# module — including the guard test that would otherwise have named it.
def _dashboard_paths() -> list[Path]:
    return sorted(DASHBOARD_DIR.glob("*.json"))


def _load(path: Path) -> dict[str, Any]:
    parsed: dict[str, Any] = json.loads(path.read_text())
    return parsed


def test_all_three_dashboards_exist() -> None:
    assert DASHBOARD_DIR.is_dir(), f"{DASHBOARD_DIR} not found"
    assert {_load(path)["uid"] for path in _dashboard_paths()} == EXPECTED_UIDS


@pytest.mark.parametrize("path", _dashboard_paths(), ids=lambda path: path.name)
def test_dashboard_has_a_title_and_a_stable_uid(path: Path) -> None:
    """The uid is the permalink. Changing it breaks every saved link."""
    name, dashboard = path.name, _load(path)
    assert dashboard.get("uid"), f"{name} has no uid"
    assert dashboard.get("title"), f"{name} has no title"


@pytest.mark.parametrize("path", _dashboard_paths(), ids=lambda path: path.name)
def test_every_panel_targets_the_prometheus_datasource(path: Path) -> None:
    """`prometheus` is the datasource uid grafana/otel-lgtm provisions.

    A panel referencing any other uid renders "Datasource not found" —
    which looks like a broken dashboard rather than a broken reference.
    """
    name, dashboard = path.name, _load(path)
    for panel in dashboard["panels"]:
        assert panel["datasource"]["uid"] == "prometheus", (
            f"{name}: panel {panel['title']!r} points at the wrong datasource"
        )
        for target in panel["targets"]:
            assert target["datasource"]["uid"] == "prometheus"


@pytest.mark.parametrize("path", _dashboard_paths(), ids=lambda path: path.name)
def test_no_panel_hard_codes_the_service_name(path: Path) -> None:
    """Spec 3.4: these files are copied verbatim into every generated
    project, never rendered. A hard-coded job name would ship every
    generated service a dashboard showing this one."""
    name, dashboard = path.name, _load(path)
    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            assert "reference-service" not in target["expr"], (
                f"{name}: panel {panel['title']!r} hard-codes the service name"
            )


@pytest.mark.parametrize("path", _dashboard_paths(), ids=lambda path: path.name)
def test_every_panel_has_a_title_and_at_least_one_target(path: Path) -> None:
    name, dashboard = path.name, _load(path)
    for panel in dashboard["panels"]:
        assert panel.get("title"), f"{name}: a panel has no title"
        assert panel.get("targets"), f"{name}: panel {panel['title']!r} queries nothing"


@pytest.mark.parametrize("path", _dashboard_paths(), ids=lambda path: path.name)
def test_every_target_has_a_ref_id(path: Path) -> None:
    """Grafana rejects a target with no refId."""
    name, dashboard = path.name, _load(path)
    for panel in dashboard["panels"]:
        ref_ids = [target.get("refId") for target in panel["targets"]]
        assert all(ref_ids), (
            f"{name}: panel {panel['title']!r} has a target with no refId"
        )
        assert len(set(ref_ids)) == len(ref_ids), (
            f"{name}: panel {panel['title']!r} repeats a refId"
        )


@pytest.mark.parametrize("path", _dashboard_paths(), ids=lambda path: path.name)
def test_every_target_declares_range_or_instant(path: Path) -> None:
    """Grafana runs neither kind of query unless the target says which.

    A Prometheus target with neither `range` nor `instant` set renders
    "No data" no matter how healthy the underlying series is — and
    nothing outside Grafana can see it, because querying Prometheus
    directly bypasses exactly the code that needs the flag. That is how
    this shipped once already.

    A stat or gauge shows one current number, so it takes an instant
    query; a timeseries plots the window, so it takes a range query.
    """
    name, dashboard = path.name, _load(path)
    for panel in dashboard["panels"]:
        wants_instant = panel["type"] in ("stat", "gauge")
        for target in panel["targets"]:
            assert target.get("range") is not wants_instant, (
                f"{name}: {panel['title']!r} target {target['refId']} "
                f"has the wrong range flag for a {panel['type']}"
            )
            assert target.get("instant") is wants_instant, (
                f"{name}: {panel['title']!r} target {target['refId']} "
                f"has the wrong instant flag for a {panel['type']}"
            )


@pytest.mark.parametrize("path", _dashboard_paths(), ids=lambda path: path.name)
def test_stat_and_gauge_panels_say_which_value_to_show(path: Path) -> None:
    """A stat or gauge with no reduceOptions renders nothing at all.

    The panel receives the data — Grafana's own /api/ds/query returns the
    value — but has no instruction for which point of the series to
    display, so it draws an empty box. Nothing outside a browser can see
    this: the query succeeds, the API returns 200, and every check that
    stops at "does the data exist" passes. That is how it shipped once.

    A timeseries needs no such block, because plotting the whole series
    is already its default.
    """
    name, dashboard = path.name, _load(path)
    for panel in dashboard["panels"]:
        if panel["type"] not in ("stat", "gauge"):
            continue
        options = panel.get("options", {})
        assert options.get("reduceOptions", {}).get("calcs"), (
            f"{name}: {panel['type']} panel {panel['title']!r} has no "
            f"reduceOptions.calcs, so it will render empty"
        )


def test_every_dashboard_declares_the_service_variable() -> None:
    """`$service` in a query with no matching variable silently matches
    nothing, and the panel just looks like a service with no traffic."""
    for path in _dashboard_paths():
        name, dashboard = path.name, _load(path)
        variables = {variable["name"] for variable in dashboard["templating"]["list"]}
        assert "service" in variables, f"{name} uses $service without declaring it"
