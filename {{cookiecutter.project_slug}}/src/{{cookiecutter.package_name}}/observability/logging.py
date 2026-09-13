"""Structured logging.

Every log record — ours and every third-party library's — passes through one
structlog processor chain and is written to standard output. Standard output
is the source of truth: it survives a collector outage and captures crashes
and any failure occurring before other telemetry has started.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Collection, Mapping, MutableMapping
from typing import Any

import orjson
import structlog
from opentelemetry import trace

# The handler comes from opentelemetry-instrumentation-logging, NOT from
# opentelemetry-sdk. The SDK's own LoggingHandler is deprecated as of
# 1.44.0 and emits a DeprecationWarning the moment it is constructed,
# which this project's filterwarnings = ["error"] turns into a test
# failure. The SDK's deprecation message names this handler as the
# replacement.
from opentelemetry.instrumentation.logging.handler import LoggingHandler
from opentelemetry.sdk._logs import LoggerProvider
from structlog.types import Processor

from {{ cookiecutter.package_name }}.observability.redaction import (
    DEFAULT_REDACT_FIELDS,
    RedactingFilter,
    make_redactor,
)


def _json_dumps(obj: Any, default: Any = None, **_: Any) -> str:
    """orjson returns bytes; structlog's renderer wants str."""
    return orjson.dumps(obj, default=default).decode()


def _bind_resource_attributes(
    *, service_name: str, service_version: str, environment: str
) -> Processor:
    """Bind the three static resource attributes spec 7.6 requires.

    `trace_id`/`span_id` are legitimately M2 — they need an active
    OpenTelemetry span. These three are plain strings already known at
    configuration time, so every record can carry them from line one:
    without `service.name` you cannot filter one service's records out of
    a shared backend, and without `service.version` you cannot tell which
    release produced a line during a rollout.
    """
    resource = {
        "service.name": service_name,
        "service.version": service_version,
        "deployment.environment": environment,
    }

    def add_resource_attributes(
        logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        event_dict.update(resource)
        return event_dict

    return add_resource_attributes


def _add_otel_context(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Stamp the active trace and span identifiers onto the record.

    Reads the AMBIENT span from the OpenTelemetry context rather than any
    provider, so this works no matter who configured the SDK — and costs
    almost nothing when nobody did, because with telemetry off there is
    never a valid span and the function returns after one check.

    The `is_valid` guard is load-bearing. Outside a span the context is
    the invalid one, whose trace_id is the integer zero: formatting it
    regardless would put
    trace_id="00000000000000000000000000000000" on every record emitted
    at startup, shutdown, or from a background task. That value looks
    exactly like a real identifier, matches nothing in Tempo, and files
    every uncorrelated line in the service under a single enormous
    fictional trace.

    The 32- and 16-hex-digit formats are the W3C Trace Context wire
    formats, which is what Tempo indexes and what the Loki datasource in
    the local stack already has a derived-field link configured for.
    """
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event_dict["trace_id"] = format(context.trace_id, "032x")
        event_dict["span_id"] = format(context.span_id, "016x")
    return event_dict


def _shared_processors(
    *,
    service_name: str,
    service_version: str,
    environment: str,
    redact_fields: Collection[str],
) -> list[Processor]:
    return [
        # Correlation id and anything else middleware bound for this request.
        structlog.contextvars.merge_contextvars,
        _bind_resource_attributes(
            service_name=service_name,
            service_version=service_version,
            environment=environment,
        ),
        _add_otel_context,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        # One exception becomes one structured field rather than thirty
        # unrelated log lines in the backend.
        structlog.processors.dict_tracebacks,
        # LAST, deliberately: it must see the fully assembled record —
        # everything the processors above added, bound context included —
        # and because this same list is the `foreign_pre_chain` below, a
        # third-party record is masked by the same rule. A secret bound
        # into context by middleware reaches a library's log line already
        # redacted (spec 7.6, spec 12 item 6).
        make_redactor(redact_fields),
    ]


def configure_logging(
    *,
    environment: str,
    level: str,
    # `Mapping`, not `dict`: `dict` is invariant in its value type, so a
    # caller passing `dict[str, LogLevel]` (settings.py's validated type)
    # would fail mypy against a plain `dict[str, str]` parameter here.
    levels: Mapping[str, str],
    # Replaced wholesale by APP_LOG__REDACT_FIELDS; see redaction.py.
    redact_fields: Collection[str] = DEFAULT_REDACT_FIELDS,
    service_name: str = "{{ cookiecutter.project_slug }}",
    service_version: str = "0.0.0",
    logger_provider: LoggerProvider | None = None,
) -> None:
    """Configure structlog and route the standard library through it."""
    shared = _shared_processors(
        service_name=service_name,
        service_version=service_version,
        environment=environment,
        redact_fields=redact_fields,
    )

    renderer: Processor = (
        structlog.dev.ConsoleRenderer()
        if environment == "local"
        else structlog.processors.JSONRenderer(serializer=_json_dumps)
    )

    structlog.configure(
        processors=[
            *shared,
            structlog.stdlib.ProcessorFormatter.wrap_for_formatter,
        ],
        logger_factory=structlog.stdlib.LoggerFactory(),
        wrapper_class=structlog.stdlib.BoundLogger,
        cache_logger_on_first_use=False,
    )

    # `foreign_pre_chain` is what pulls records emitted by libraries using
    # the standard library's logging module into the same processor chain.
    formatter = structlog.stdlib.ProcessorFormatter(
        foreign_pre_chain=shared,
        processors=[
            structlog.stdlib.ProcessorFormatter.remove_processors_meta,
            renderer,
        ],
    )

    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level.upper())

    # uvicorn installs its own handlers on these three loggers, and sets
    # them non-propagating, before the app factory ever runs — so clearing
    # only the root logger's handlers (above) is not enough; uvicorn's
    # records would still reach uvicorn's own text handler instead of this
    # one, and never propagate up to root at all. Clearing their handlers
    # and turning propagation back on routes their records through this
    # same formatter, so "every log record passes through one processor
    # chain" (the module docstring's promise) also holds for uvicorn's own
    # startup, access, and connection-level lines, not just third-party
    # libraries that log through the standard logging module the ordinary
    # way.
    for uvicorn_logger_name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(uvicorn_logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True

    if logger_provider is not None:
        # A SECOND handler on the same root logger, so every record goes to
        # standard output AND to OTLP. Standard output is the source of
        # truth (spec D15): it survives a collector outage and captures
        # crashes and any failure happening before the SDK initialised.
        # This leg exists so that locally a developer sees log lines beside
        # the matching trace in Grafana without wiring up a log scraper.
        #
        # Its own ProcessorFormatter instance, not the one above, for two
        # reasons. The renderer differs — a backend has no use for the
        # colourised console output `local` gets on stdout, so this leg is
        # always JSON — and two handlers formatting the same record through
        # one shared formatter object is a needless shared-mutation risk
        # for the sake of saving an allocation made once per process.
        #
        # No `level=` argument, deliberately. The stdout handler above sets
        # none either, so both legs pass whatever their LOGGER allowed and
        # the per-logger `levels` mapping below governs both identically.
        # Pinning this handler to the global level would silently drop the
        # records that mapping exists to let through — set
        # APP_LOG__LEVELS='{"sqlalchemy.engine":"debug"}' under a global
        # `info` and those lines would reach stdout but never OTLP,
        # contradicting this function's "one pipeline for every record".
        #
        # trace_id and span_id are set on the OTLP record automatically by
        # LoggingHandler from the active span; the copies inside the JSON
        # body come from _add_otel_context and are for whoever reads the
        # body directly.
        otlp_handler = LoggingHandler(logger_provider=logger_provider)
        # The body goes through the redacting chain below, but the handler
        # copies `extra=` attributes straight across -- see RedactingFilter.
        otlp_handler.addFilter(RedactingFilter(redact_fields))
        otlp_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=shared,
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer(serializer=_json_dumps),
                ],
            )
        )
        root.addHandler(otlp_handler)

    for logger_name, logger_level in levels.items():
        logging.getLogger(logger_name).setLevel(logger_level.upper())
