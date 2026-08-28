"""Request middleware: correlation identifiers and the access log.

Both are plain ASGI callables rather than BaseHTTPMiddleware subclasses.
BaseHTTPMiddleware wraps each request in a task group, which interferes with
streaming responses and background tasks; a plain callable does not.
"""

from __future__ import annotations

import time
from typing import Any
from uuid import uuid4

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CORRELATION_HEADER = "X-Request-ID"

EXCLUDED_FROM_ACCESS_LOG = frozenset({"/healthz", "/readyz", "/startupz"})

_logger = structlog.get_logger("reference_service.access")


class CorrelationIdMiddleware:
    """Bind one identifier to every log line produced during a request."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        incoming = Headers(scope=scope).get(CORRELATION_HEADER.lower())
        correlation_id = incoming or uuid4().hex

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[CORRELATION_HEADER] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            structlog.contextvars.clear_contextvars()


class AccessLogMiddleware:
    """One structured record per request.

    uvicorn's own access log is plain text and records the raw path, which
    turns every identifier into a distinct value. This logs the route
    template instead.
    """

    def __init__(
        self,
        app: ASGIApp,
        excluded_paths: frozenset[str] = EXCLUDED_FROM_ACCESS_LOG,
    ) -> None:
        self.app = app
        self.excluded_paths = excluded_paths

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        status_code = 500
        started = time.perf_counter()

        async def send_wrapper(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            duration_ms = round((time.perf_counter() - started) * 1000, 3)
            route: Any = scope.get("route")
            template = getattr(route, "path", scope.get("path", ""))
            if template not in self.excluded_paths:
                _logger.info(
                    "http.access",
                    **{
                        "http.request.method": scope.get("method", ""),
                        "http.route": template,
                        "http.response.status_code": status_code,
                        "duration_ms": duration_ms,
                    },
                )
