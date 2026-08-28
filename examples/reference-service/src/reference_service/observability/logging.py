"""Structured logging.

Every log record — ours and every third-party library's — passes through one
structlog processor chain and is written to standard output. Standard output
is the source of truth: it survives a collector outage and captures crashes
and any failure occurring before other telemetry has started.
"""

from __future__ import annotations

import logging
import sys
from typing import Any

import orjson
import structlog
from structlog.types import Processor


def _json_dumps(obj: Any, default: Any = None, **_: Any) -> str:
    """orjson returns bytes; structlog's renderer wants str."""
    return orjson.dumps(obj, default=default).decode()


def _shared_processors() -> list[Processor]:
    return [
        # Correlation id and anything else middleware bound for this request.
        structlog.contextvars.merge_contextvars,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        # One exception becomes one structured field rather than thirty
        # unrelated log lines in the backend.
        structlog.processors.dict_tracebacks,
    ]


def configure_logging(
    *,
    environment: str,
    level: str,
    levels: dict[str, str],
) -> None:
    """Configure structlog and route the standard library through it."""
    shared = _shared_processors()

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

    for logger_name, logger_level in levels.items():
        logging.getLogger(logger_name).setLevel(logger_level.upper())
