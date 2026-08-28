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

# Logged in place of a route template when nothing matched. See the comment
# at the fallback below for why this is not the raw path.
UNMATCHED_ROUTE = "<unmatched>"

_logger = structlog.get_logger("reference_service.access")


def _route_template(scope: Scope) -> str:
    """The bounded route template for this request.

    Deliberately not `scope["route"].path`: FastAPI records an included
    router's routes with their INNER path only, so a router mounted under
    `/api/v1` reports `/orders/{order_id}`, and two API versions of the same
    resource become indistinguishable in the logs.

    Deliberately not `scope["path"]` either: that is the raw path, and every
    distinct identifier would become a distinct value — the unbounded
    cardinality this field exists to avoid.

    Instead, rebuild the template from the raw path by substituting each
    matched path parameter back into place. That is exact, keeps the full
    prefix, and does not depend on how the framework stores its routes.
    """
    if scope.get("route") is None:
        # Nothing matched, so this is usually a bot probing nonexistent
        # URLs. Logging the raw path would put one distinct value in the
        # log per probe.
        return UNMATCHED_ROUTE

    raw: str = scope.get("path", "")
    params: dict[str, Any] = scope.get("path_params") or {}
    if not params:
        # A literal route with no parameters: the raw path IS the template,
        # and it is bounded because the route is registered.
        return raw

    # Substitute whole segments only. Replacing by substring would corrupt a
    # path where a parameter's value also appears as a literal segment.
    name_by_value = {str(value): name for name, value in params.items()}
    return "/".join(
        "{" + name_by_value[segment] + "}" if segment in name_by_value else segment
        for segment in raw.split("/")
    )


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
