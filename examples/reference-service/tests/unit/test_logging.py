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


def test_records_carry_the_three_static_resource_attributes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Spec 7.6's field contract, minus trace_id/span_id (legitimately M2).

    Without service.name you cannot filter one service's records out of a
    shared backend; without service.version you cannot tell which release
    produced a line during a rollout.
    """
    configure_logging(
        environment="production",
        level="info",
        levels={},
        service_name="reference-service",
        service_version="1.2.3",
    )

    structlog.get_logger().info("order.placed")

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["service.name"] == "reference-service"
    assert payload["service.version"] == "1.2.3"
    assert payload["deployment.environment"] == "production"


def test_a_standard_library_record_also_carries_resource_attributes(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The resource attributes go through `foreign_pre_chain` too.

    A library logging through the standard `logging` module must not
    bypass the same shared processors a structlog call goes through.
    """
    configure_logging(
        environment="production",
        level="info",
        levels={},
        service_name="reference-service",
        service_version="1.2.3",
    )

    logging.getLogger("some.library").warning("connection retried")

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["service.name"] == "reference-service"
    assert payload["service.version"] == "1.2.3"
    assert payload["deployment.environment"] == "production"


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


def test_a_uvicorn_record_gets_the_same_shape_as_everything_else(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """uvicorn installs its own non-propagating handlers before the app
    factory runs, so clearing only the root logger's handlers is not
    enough — its records would keep going through uvicorn's own text
    handler instead of reaching this bridge. configure_logging must also
    clear uvicorn's own loggers' handlers and re-enable propagation so
    uvicorn's records pass through the same processor chain as every
    other record, contradicting nothing in the module's "every log
    record" claim.
    """
    configure_logging(environment="production", level="info", levels={})

    logging.getLogger("uvicorn.error").warning("application shutdown complete")

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["event"] == "application shutdown complete"
    assert payload["level"] == "warning"
    assert payload["logger"] == "uvicorn.error"
    assert payload["service.name"] == "reference-service"
    assert "timestamp" in payload


def test_local_environment_uses_the_console_renderer(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="local", level="info", levels={})

    structlog.get_logger().info("order.placed", order_id="abc")

    out = capsys.readouterr().out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip())
    assert "order.placed" in out
