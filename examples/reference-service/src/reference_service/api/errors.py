"""RFC 9457 Problem Details responses.

This is the only module that maps a domain error onto an HTTP status code.
The domain says which rule broke; deciding that "not found" means 404 is a
statement about a transport protocol and belongs here.
"""

from __future__ import annotations

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel

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
        _logger.info(
            "request.domain_error",
            error_code=exc.code,
            status=http_status,
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

    @app.exception_handler(Exception)
    async def _unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        # Log the full traceback; return nothing that describes our internals.
        _logger.exception("request.unhandled_error", path=request.url.path)
        return _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/internal_error",
                title="Internal server error",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
                instance=request.url.path,
            )
        )
