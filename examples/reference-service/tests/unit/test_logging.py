import json
import logging
from collections.abc import Iterator

import pytest
import structlog

from reference_service.observability.logging import configure_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


def test_structlog_call_renders_json_to_stdout(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="production", level="info", levels={})

    structlog.get_logger("my.logger").info("order.placed", order_id="abc")

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["event"] == "order.placed"
    assert payload["level"] == "info"
    assert payload["order_id"] == "abc"
    assert "timestamp" in payload


def test_standard_library_record_gets_the_same_shape(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """A third-party library logging through `logging` must not bypass us."""
    configure_logging(environment="production", level="info", levels={})

    logging.getLogger("some.library").warning("connection retried")

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["event"] == "connection retried"
    assert payload["level"] == "warning"
    assert payload["logger"] == "some.library"
    assert "timestamp" in payload


def test_exception_is_one_structured_field_not_many_lines(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="production", level="info", levels={})

    try:
        raise ValueError("boom")
    except ValueError:
        structlog.get_logger().exception("order.failed")

    out = capsys.readouterr().out.strip()
    assert len(out.splitlines()) == 1, "an exception must stay a single event"
    payload = json.loads(out)
    assert payload["exception"][0]["exc_type"] == "ValueError"


def test_per_logger_level_silences_a_chatty_library(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(
        environment="production", level="info", levels={"chatty": "error"}
    )

    logging.getLogger("chatty").info("this must not appear")
    logging.getLogger("quiet").info("this must appear")

    out = capsys.readouterr().out
    assert "this must not appear" not in out
    assert "this must appear" in out


def test_local_environment_uses_the_console_renderer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="local", level="info", levels={})

    structlog.get_logger().info("order.placed", order_id="abc")

    out = capsys.readouterr().out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip())
    assert "order.placed" in out
