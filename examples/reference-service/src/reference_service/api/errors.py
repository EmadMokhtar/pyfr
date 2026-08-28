"""RFC 9457 Problem Details responses.

This is the only module that maps a domain error onto an HTTP status code.
The domain says which rule broke; deciding that "not found" means 404 is a
statement about a transport protocol and belongs here.
"""

from __future__ import annotations

from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError

from reference_service.api.middleware import CORRELATION_HEADER, _route_template
from reference_service.domain.errors import DomainError, OrderNotFoundError

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://errors.example.com"

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    OrderNotFoundError: status.HTTP_404_NOT_FOUND,
}

_DEFAULT_DOMAIN_STATUS = status.HTTP_422_UNPROCESSABLE_CONTENT

_logger = structlog.get_logger(__name__)


class ProblemDetail(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    instance: str | None = None


def _problem_content() -> dict[str, Any]:
    """The `content` dict FastAPI needs to document a response at its real
    media type.

    NOT `{"model": ProblemDetail}` at the top level of a `responses` entry:
    FastAPI always attaches a `model` entry's schema under the ROUTE's own
    response media type (`application/json` by default) no matter what
    `content` key is also present — verified against a minimal app: giving
    both produced an empty `application/problem+json` entry AND a
    duplicate `application/json` entry carrying the schema, which is
    exactly the drift this exists to remove. Embedding the JSON schema
    directly under the real media type is the only way to get one correct
    entry instead of two, one of them wrong.
    """
    return {PROBLEM_MEDIA_TYPE: {"schema": ProblemDetail.model_json_schema()}}


def problem_response(description: str) -> dict[str, Any]:
    """One reusable OpenAPI `responses` entry describing a Problem Details
    response, for use in a route decorator's or `FastAPI()`'s `responses=`.

    Registering the runtime exception handlers below does not, by itself,
    change what FastAPI generates for `/docs` or `/openapi.json` — a
    generated client built from the undocumented schema would disagree
    with what the service actually returns. This is what makes the two
    agree.
    """
    return {"description": description, "content": _problem_content()}


# Every route can hit request validation (422, via RequestValidationError)
# or an unexpected failure (500, via the catch-all Exception handler), so
# these are applied globally, in main.py's `FastAPI(responses=...)`. The
# 404 for OrderNotFoundError is NOT included here: unlike 422 and 500, only
# some routes can actually produce it, so it is applied per-route instead,
# where it is true — see api/v1/router.py's `get_order`.
DEFAULT_PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    status.HTTP_422_UNPROCESSABLE_CONTENT: problem_response(
        "Request validation failed"
    ),
    status.HTTP_500_INTERNAL_SERVER_ERROR: problem_response("Internal server error"),
}


def status_for(error: DomainError) -> int:
    """Map a domain error to a status code, honouring subclasses.

    Walks the method resolution order rather than looking up `type(error)`
    directly, so a subclass inherits its parent's status instead of silently
    falling through to the default. A future `OrderAlreadyShippedError`
    subclassing `OrderNotFoundError` should answer 404, not 422.
    """
    for error_class in type(error).__mro__:
        if error_class in _STATUS_BY_ERROR:
            return _STATUS_BY_ERROR[error_class]
    return _DEFAULT_DOMAIN_STATUS


def _problem_response(problem: ProblemDetail) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
    )


def register_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def _domain_error(request: Request, exc: DomainError) -> JSONResponse:
        http_status = status_for(exc)
        # Same key names as api/middleware.py's AccessLogMiddleware, so a
        # dashboard querying the OpenTelemetry HTTP semantic-convention
        # names sees these lines too, instead of a second, incompatible
        # naming scheme for the same kind of fact.
        _logger.info(
            "request.domain_error",
            error_code=exc.code,
            **{"http.response.status_code": http_status},
        )
        return _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/{exc.code}",
                title=exc.title,
                status=http_status,
                detail=str(exc),
                instance=request.url.path,
            )
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/validation_error",
                title="Request validation failed",
                status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc.errors()),
                instance=request.url.path,
            )
        )

    @app.exception_handler(PydanticValidationError)
    async def _pydantic_validation_error(
        request: Request, exc: PydanticValidationError
    ) -> JSONResponse:
        # A net for the next place a raw pydantic model validates input
        # a shallower layer already accepted: without this, such a error
        # is neither a DomainError nor a RequestValidationError, so it falls
        # through to the catch-all below and becomes an unearned 500.
        #
        # warning, not exception: this is a client-fault path (a 422), not
        # a server fault. But this handler exists precisely to catch
        # cross-layer validation asymmetries, so the next one must stay
        # loud in the logs, not silent. correlation_id is not passed
        # explicitly: this handler runs inside CorrelationIdMiddleware, so
        # structlog.contextvars.merge_contextvars already carries it, the
        # same way _domain_error's log line above does.
        _logger.warning(
            "request.validation_error",
            **{"http.route": _route_template(request.scope)},
        )
        return _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/validation_error",
                title="Request validation failed",
                status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail=str(exc.errors()),
                instance=request.url.path,
            )
        )

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # A handler registered for `Exception` becomes ServerErrorMiddleware's
        # handler, which sits OUTSIDE CorrelationIdMiddleware — by the time
        # it runs, that middleware's `finally` has already cleared the bound
        # contextvars, so `_logger.exception` alone would log a traceback
        # with no correlation id. Recover it from the scope instead: it
        # survives, because ServerErrorMiddleware builds this Request from
        # that same scope. See CorrelationIdMiddleware for the other half.
        correlation_id = request.scope.get("correlation_id")

        # Log the full traceback; return nothing that describes our internals.
        # http.route, not the raw path: same bounded-cardinality reasoning
        # and the same field name as AccessLogMiddleware — logging
        # request.url.path here would be exactly the unbounded-cardinality
        # field that middleware works to avoid.
        _logger.exception(
            "request.unhandled_error",
            correlation_id=correlation_id,
            **{
                "http.route": _route_template(request.scope),
                "http.response.status_code": status.HTTP_500_INTERNAL_SERVER_ERROR,
            },
        )
        response = _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/internal_error",
                title="Internal server error",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                instance=request.url.path,
            )
        )
        if correlation_id is not None:
            response.headers[CORRELATION_HEADER] = correlation_id
        return response
