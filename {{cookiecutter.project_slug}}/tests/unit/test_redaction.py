"""Redaction sits in the SHARED processor chain, so it covers every record
however it was produced — a structlog call, a value bound into context
variables by middleware, or a standard-library record from a third-party
library — at every depth of nesting. These tests go through
configure_logging and read the rendered output, because
structlog.testing.capture_logs bypasses the processors entirely.
"""

import json
import logging
import string
from collections.abc import Callable, Iterator

import pytest
import structlog
from hypothesis import given
from hypothesis import strategies as st

from {{ cookiecutter.package_name }}.observability.logging import configure_logging
from {{ cookiecutter.package_name }}.observability.redaction import (
    DEFAULT_REDACT_FIELDS,
    REDACTED,
    make_redactor,
)


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    structlog.contextvars.clear_contextvars()
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


def _only_record(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    lines = [line for line in capsys.readouterr().out.splitlines() if line.strip()]
    assert len(lines) == 1, lines
    record: dict[str, object] = json.loads(lines[0])
    return record


def test_a_top_level_field_is_masked(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(environment="production", level="info", levels={})

    structlog.get_logger("test").info("user.login", password="hunter2", user="ann")  # noqa: S106

    record = _only_record(capsys)
    assert record["password"] == REDACTED
    assert record["user"] == "ann"
    assert "hunter2" not in json.dumps(record)


def test_a_nested_field_is_masked_at_any_depth(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="production", level="info", levels={})

    structlog.get_logger("test").info(
        "http.request",
        request={"headers": {"Authorization": "Bearer abc", "Accept": "*/*"}},
        attempts=[{"Set-Cookie": "sid=1"}, {"note": "fine"}],
    )

    record = _only_record(capsys)
    request = record["request"]
    attempts = record["attempts"]
    assert isinstance(request, dict) and isinstance(attempts, list)
    assert request["headers"]["Authorization"] == REDACTED
    assert request["headers"]["Accept"] == "*/*"
    assert attempts[0]["Set-Cookie"] == REDACTED
    assert attempts[1]["note"] == "fine"


def test_matching_ignores_case_and_treats_dash_as_underscore(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="production", level="info", levels={})

    structlog.get_logger("test").info("x", API_KEY="k1", **{"api-key": "k2"})

    record = _only_record(capsys)
    assert record["API_KEY"] == REDACTED
    assert record["api-key"] == REDACTED


def test_a_value_bound_into_context_is_masked_on_a_third_party_record(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The reason the processor is in the SHARED chain. A standard-library
    record from a library never passes through a structlog call, but it
    does pass through foreign_pre_chain — which is the same list."""
    configure_logging(environment="production", level="info", levels={})
    structlog.contextvars.bind_contextvars(token="tok-123", request_id="r1")  # noqa: S106

    logging.getLogger("some.library").warning("retrying")

    record = _only_record(capsys)
    assert record["token"] == REDACTED
    assert record["request_id"] == "r1"
    assert "tok-123" not in json.dumps(record)


def test_the_configured_list_replaces_the_default(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(
        environment="production", level="info", levels={}, redact_fields={"pin"}
    )

    structlog.get_logger("test").info("x", pin="1234", password="still-visible")  # noqa: S106

    record = _only_record(capsys)
    assert record["pin"] == REDACTED
    assert record["password"] == "still-visible"  # noqa: S105


def test_the_console_renderer_is_covered_too(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="local", level="info", levels={})

    structlog.get_logger("test").info("x", secret="s3cr3t")  # noqa: S106

    out = capsys.readouterr().out
    assert "s3cr3t" not in out
    assert REDACTED in out


@given(
    name=st.sampled_from(sorted(DEFAULT_REDACT_FIELDS)),
    casing=st.sampled_from([str.lower, str.upper, str.title]),
    dashed=st.booleans(),
    depth=st.integers(min_value=0, max_value=4),
    secret=st.text(
        alphabet=string.ascii_letters + string.digits, min_size=8, max_size=24
    ),
)
def test_a_default_field_never_survives_at_any_depth_or_casing(
    name: str, casing: Callable[[str], str], dashed: bool, depth: int, secret: str
) -> None:
    """The pure property, on the processor alone: no fixture, so Hypothesis
    can run its examples freely."""
    key = casing(name.replace("_", "-") if dashed else name)
    payload: dict[str, object] = {key: secret}
    for level in range(depth):
        payload = {f"level{level}": payload}
    event_dict: dict[str, object] = {"event": "x", **payload}

    rendered = make_redactor(DEFAULT_REDACT_FIELDS)(None, "info", event_dict)

    assert secret not in json.dumps(rendered)
