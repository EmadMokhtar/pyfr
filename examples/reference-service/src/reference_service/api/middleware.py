"""Request middleware: correlation identifiers and the access log.

Both are plain ASGI callables rather than BaseHTTPMiddleware subclasses.
BaseHTTPMiddleware wraps each request in a task group, which interferes with
streaming responses and background tasks; a plain callable does not.
"""

from __future__ import annotations

import re
import time
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import structlog
from starlette.datastructures import Headers, MutableHeaders
from starlette.types import ASGIApp, Message, Receive, Scope, Send

CORRELATION_HEADER = "X-Request-ID"

EXCLUDED_FROM_ACCESS_LOG = frozenset({"/healthz", "/readyz", "/startupz"})

# Logged in place of a route template when nothing matched. See the comment
# at the fallback below for why this is not the raw path.
UNMATCHED_ROUTE = "<unmatched>"

_logger = structlog.get_logger("reference_service.access")

_PATH_PARAM = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)(?::[^}]+)?\}")


def _fill(template: str, params: Mapping[str, Any]) -> str:
    """Substitute matched values back into a route template.

    Handles Starlette's converter syntax (`{file_path:path}`), which
    `str.format` cannot: it would read `:path` as a format specification.
    """
    return _PATH_PARAM.sub(
        lambda match: str(params.get(match.group(1), match.group(0))), template
    )


def _route_template(scope: Scope) -> str:
    """The bounded route template for this request, including any prefix.

    Three approaches are wrong, and it is worth recording why.

    `scope["route"].path` alone: FastAPI 0.141 stores an included router
    lazily, so a router mounted under `/api/v1` reports only its inner
    `/orders/{order_id}`. Two API versions of one resource then look
    identical in the logs.

    `scope["path"]` alone: that is the raw path, so every identifier becomes
    a distinct value — the unbounded cardinality this field exists to avoid.

    Substituting parameter VALUES out of the raw path: subtly wrong, because
    it matches by text. A request to `/api/v1/orders/orders` would rewrite
    the literal `/orders` segment too, giving `/api/v1/{order_id}/{order_id}`.
    It also silently fails for a parameter whose value spans segments, such
    as a `:path` converter, falling back to the raw path.

    So work the other way round. Fill the route's own template with the
    matched values to get the concrete path it produced; whatever the raw
    path carries in front of that is the mount prefix. Positional rather
    than textual, and correct for multi-segment values.
    """
    inner: str | None = getattr(scope.get("route"), "path", None)
    if inner is None:
        # Nothing matched — usually a bot probing nonexistent URLs, where
        # the raw path would be one distinct value per probe.
        return UNMATCHED_ROUTE

    raw: str = scope.get("path", "")
    concrete = _fill(inner, scope.get("path_params") or {})
    if raw.endswith(concrete):
        return raw[: len(raw) - len(concrete)] + inner

    # The template could not be located inside the raw path. Return the
    # inner template anyway: it may be missing a prefix, but it is bounded,
    # and bounded matters more than complete.
    return inner


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

        # Also stashed on the scope, not just the contextvar: an unhandled
        # exception is handled by ServerErrorMiddleware, which sits OUTSIDE
        # this middleware and therefore outside the bound contextvars — by
        # the time its handler runs, clear_contextvars() below has already
        # fired. The scope survives that; ServerErrorMiddleware builds its
        # Request from this same scope, so api/errors.py can still recover
        # the id for the traceback log line and the response header.
        scope["correlation_id"] = correlation_id

        structlog.contextvars.clear_contextvars()
        structlog.contextvars.bind_contextvars(correlation_id=correlation_id)

        async def send_wrapper(message: Message) -> None:
            if message["type"] == "http.response.start":
                MutableHeaders(scope=message)[CORRELATION_HEADER] = correlation_id
            await send(message)

        try:
            await self.app(scope, receive, send_wrapper)
        finally:
            # Deliberately redundant with the clear above, and NOT reachable
            # by any test in this suite — do not delete it as dead code.
            # It narrows the window in which a finished request's context
            # stays visible to whatever runs next in the same task, before
            # the next request re-enters here. uvicorn does not reset
            # contextvars per request by default, and this service routes
            # uvicorn's own records through structlog, so a connection-level
            # line emitted in that gap would otherwise inherit a completed
            # request's correlation id.
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
            template = _route_template(scope)
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
