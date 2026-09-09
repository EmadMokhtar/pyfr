"""The gate: the shipped PromQL and the Python constants must agree.

Every SLO number lives twice — once in observability/slo.py where the code
reads it, once in ops/prometheus/rules/slo.yml where Prometheus reads it.
Nothing at runtime would notice them diverging. The symptom of divergence
is the worst kind there is: an objective that reports a comfortable number
while users experience something else.

Pure Python and no Docker, so this runs in the fast tier on every commit.
`just o11y-gates` runs promtool over the same files in the container tier.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from reference_service.observability.slo import (
    ERROR_BUDGET,
    SLO_LATENCY_THRESHOLD_SECONDS,
    excluded_routes_pattern,
)

RULES_FILE = (
    Path(__file__).resolve().parents[2] / "ops" / "prometheus" / "rules" / "slo.yml"
)


@pytest.fixture(scope="module")
def rules() -> list[dict[str, Any]]:
    document = yaml.safe_load(RULES_FILE.read_text())
    return [rule for group in document["groups"] for rule in group["rules"]]


def _expressions(rules: list[dict[str, Any]]) -> list[str]:
    return [rule["expr"] for rule in rules]


def test_the_rules_file_is_where_this_test_thinks_it_is() -> None:
    """Names the problem when ops/ moves.

    Without it a relocated file still fails every test in this module, but
    as a `FileNotFoundError` raised inside the fixture — six errors whose
    message is a path, rather than one assertion that says the rules file
    is not where the gate expects it.
    """
    assert RULES_FILE.is_file(), f"{RULES_FILE} not found"


def test_every_latency_bucket_matcher_uses_the_python_threshold(
    rules: list[dict[str, Any]],
) -> None:
    """`le="0.3"` and SLO_LATENCY_THRESHOLD_SECONDS are one number.

    Compared as floats, not strings: Prometheus renders bucket boundaries
    with the shortest representation that round-trips, so a threshold of
    1.0 is stored as le="1" while Python's str() gives "1.0".
    """
    found = [
        float(value)
        for expression in _expressions(rules)
        for value in re.findall(r'le="([0-9.]+)"', expression)
    ]

    assert found, "no le= matcher found at all; the latency rules are missing"
    assert set(found) == {SLO_LATENCY_THRESHOLD_SECONDS}

    # Set equality alone is satisfied by ONE surviving matcher, so five of
    # the six latency rules could lose theirs and this would still pass.
    # A latency rule without `le=` sums every bucket, making the ratio far
    # greater than 1 and the reported "error" fraction negative.
    latency_rules = [rule for rule in rules if "latency" in rule.get("record", "")]
    assert len(latency_rules) == 6, (
        f"expected 6 latency rules, got {len(latency_rules)}"
    )
    for rule in latency_rules:
        assert rule["expr"].count('le="') == 1, (
            f"{rule['record']} has no le= bucket matcher"
        )


def test_every_burn_rate_threshold_uses_the_python_error_budget(
    rules: list[dict[str, Any]],
) -> None:
    """The alerts are written as `<burn rate> * <error budget>`.

    Keeping the multiplication visible in the PromQL is deliberate: a
    bare 0.0144 says nothing about where it came from, and nobody can
    review a number whose origin is invisible.
    """
    budgets = [
        float(value)
        for rule in rules
        if "alert" in rule
        for value in re.findall(r"\*\s*([0-9.]+)\)", rule["expr"])
    ]

    assert budgets, "no burn-rate threshold found; the alerts are missing"
    assert set(budgets) == {ERROR_BUDGET}


def test_every_sli_rule_excludes_the_health_endpoints(
    rules: list[dict[str, Any]],
) -> None:
    """The exclusion is a string in a YAML file and nothing else guards it.

    Dropped, the objective silently starts measuring readiness probes —
    which never fail — and reports a healthy service forever.
    """
    pattern = excluded_routes_pattern()
    recording_rules = [rule for rule in rules if "record" in rule]

    assert recording_rules, "no recording rules found"
    for rule in recording_rules:
        expression = rule["expr"]
        # EVERY rate() over the request counter must carry the exclusion,
        # not merely one of them. `in` alone would accept a rule that had
        # lost the matcher from its DENOMINATOR, which is the dangerous
        # direction: probe traffic then inflates the denominator and the
        # error ratio collapses towards zero, reporting a healthy
        # objective for a service failing every real request.
        assert expression.count("rate(") == expression.count(
            f'http_route!~"{pattern}"'
        ), f"{rule['record']}: not every rate() excludes the health endpoints"


def test_every_window_an_alert_uses_has_a_recording_rule(
    rules: list[dict[str, Any]],
) -> None:
    """A typo in an alert's window is otherwise invisible.

    PromQL against a series that does not exist is not an error; it is an
    empty result, and an empty result never fires. The alert would simply
    never trigger, and nothing would ever say so.
    """
    recorded = {rule["record"] for rule in rules if "record" in rule}
    referenced = {
        name
        for rule in rules
        if "alert" in rule
        for name in re.findall(r"job:slo_\w+:ratio_rate\w+", rule["expr"])
    }

    assert referenced, "no alert references a recording rule"
    assert referenced <= recorded, (
        f"alerts reference missing rules: {referenced - recorded}"
    )


def test_each_rule_name_matches_the_window_in_its_expression(
    rules: list[dict[str, Any]],
) -> None:
    """`ratio_rate5m` computing a `[1h]` rate would pass every other gate.

    Nothing else here reads the range inside the expression, and no
    promtool test would catch it either: the tests assert ratios, and a
    ratio does not change when the window does. It is the same class of
    silent divergence this whole file exists to close.
    """
    for rule in rules:
        if "record" not in rule:
            continue
        window = rule["record"].rsplit("ratio_rate", 1)[1]
        ranges = set(re.findall(r"\[(\w+)\]", rule["expr"]))
        assert ranges == {window}, (
            f"{rule['record']} computes {ranges} rather than [{window}]"
        )


def test_both_indicators_are_alerted_on(rules: list[dict[str, Any]]) -> None:
    """Spec 7.5 names two indicators; two objectives need two alerts."""
    slos = {rule["labels"]["slo"] for rule in rules if "alert" in rule}

    assert slos == {"availability", "latency"}
