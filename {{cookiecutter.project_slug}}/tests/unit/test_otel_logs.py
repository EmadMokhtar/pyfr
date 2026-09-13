"""OTLP log export (spec D15). Additive, opt-in, never a replacement."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
import structlog
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)

from {{ cookiecutter.package_name }}.observability.logging import configure_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


@pytest.fixture
def exporter() -> InMemoryLogRecordExporter:
    # InMemoryLogRecordExporter, NOT InMemoryLogExporter: the latter is
    # deprecated and emits a DeprecationWarning on import, which this
    # project's filterwarnings = ["error"] turns into a test failure.
    return InMemoryLogRecordExporter()


@pytest.fixture
def logger_provider(exporter: InMemoryLogRecordExporter) -> LoggerProvider:
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    return provider


def _body(record: object) -> dict[str, object]:
    """Parse an exported record's body as JSON.

    `LogRecord.body` is typed as the whole AnyValue union (string, number,
    sequence, mapping, None), because OTLP allows any of those. This
    project's handler always renders a JSON string, so the body is
    narrowed here once rather than at each call site.
    """
    body = record.log_record.body  # type: ignore[attr-defined]
    assert isinstance(body, str), f"expected a JSON string body, got {type(body)}"
    parsed: dict[str, object] = json.loads(body)
    return parsed


def test_without_a_provider_nothing_is_exported(
    capsys: pytest.CaptureFixture[str], exporter: InMemoryLogRecordExporter
) -> None:
    """The default. Standard output only."""
    configure_logging(environment="production", level="info", levels={})

    structlog.get_logger().info("order.placed")

    assert capsys.readouterr().out.strip() != ""
    assert exporter.get_finished_logs() == ()


def test_with_a_provider_the_record_goes_BOTH_places(
    capsys: pytest.CaptureFixture[str],
    exporter: InMemoryLogRecordExporter,
    logger_provider: LoggerProvider,
) -> None:
    """D15: OTLP is added on top of standard output, not instead of it.

    Standard output survives a collector outage and captures crashes and
    anything failing before the SDK started, which is exactly the output
    you need when a service will not start. Losing it in exchange for
    OTLP would be a downgrade dressed as an upgrade.
    """
    configure_logging(
        environment="production",
        level="info",
        levels={},
        logger_provider=logger_provider,
    )

    structlog.get_logger().info("order.placed", order_id="abc")

    stdout_payload = json.loads(capsys.readouterr().out.strip())
    assert stdout_payload["event"] == "order.placed"

    exported = exporter.get_finished_logs()
    assert len(exported) == 1
    assert _body(exported[0])["order_id"] == "abc"


def test_the_exported_body_is_json_even_in_local_mode(
    exporter: InMemoryLogRecordExporter, logger_provider: LoggerProvider
) -> None:
    """Locally stdout is colourised console text for a human to read.

    A backend is not a human. The OTLP handler renders JSON regardless of
    environment, so what Loki stores is always machine-parseable and
    always the same shape as production.
    """
    configure_logging(
        environment="local",
        level="info",
        levels={},
        logger_provider=logger_provider,
    )

    structlog.get_logger().info("order.placed", order_id="abc")

    assert _body(exporter.get_finished_logs()[0])["event"] == "order.placed"


def test_a_third_party_record_is_exported_too(
    exporter: InMemoryLogRecordExporter, logger_provider: LoggerProvider
) -> None:
    """One pipeline for every record, OTLP leg included."""
    configure_logging(
        environment="production",
        level="info",
        levels={},
        logger_provider=logger_provider,
    )

    logging.getLogger("some.library").warning("connection retried")

    assert _body(exporter.get_finished_logs()[0])["logger"] == "some.library"


def test_a_third_party_extra_field_is_redacted_in_the_exported_attributes(
    exporter: InMemoryLogRecordExporter, logger_provider: LoggerProvider
) -> None:
    """LoggingHandler copies record attributes into OTLP attributes without
    the processor chain; RedactingFilter masks them first."""
    configure_logging(
        environment="production",
        level="info",
        levels={},
        logger_provider=logger_provider,
    )

    logging.getLogger("some.library").warning(
        "retrying", extra={"authorization": "Bearer abc", "attempt": 2}
    )

    [exported] = exporter.get_finished_logs()
    attributes = dict(exported.log_record.attributes or {})
    assert attributes["authorization"] == "[REDACTED]"
    assert attributes["attempt"] == 2
    assert "Bearer abc" not in json.dumps(attributes)
    assert "Bearer abc" not in str(exported.log_record.body)
