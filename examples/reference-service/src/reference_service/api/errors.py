"""RFC 9457 Problem Details responses.

This is the only module that maps a domain error onto an HTTP status code.
The domain says which rule broke; deciding that "not found" means 404 is a
statement about a transport protocol and belongs here.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

import structlog
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from pydantic import ValidationError as PydanticValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from reference_service.api.middleware import CORRELATION_HEADER, _route_template
from reference_service.domain.errors import (
    DomainError,
    OrderNotFoundError,
    PaymentDeclinedError,
)
from reference_service.infrastructure.errors import PaymentUnavailableError

PROBLEM_MEDIA_TYPE = "application/problem+json"
PROBLEM_TYPE_BASE = "https://errors.example.com"

_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    OrderNotFoundError: status.HTTP_404_NOT_FOUND,
    PaymentDeclinedError: status.HTTP_402_PAYMENT_REQUIRED,
}

_DEFAULT_DOMAIN_STATUS = status.HTTP_422_UNPROCESSABLE_CONTENT

# The fallback only, for when no payment provider is configured and there
# is therefore no breaker window to read. Matches
# PaymentSettings.breaker_reset_after_seconds's own default in
# settings.py; `_retry_after_seconds` below prefers the CONFIGURED value,
# because telling a client to come back before the circuit could possibly
# have closed just wastes both sides' time.
RETRY_AFTER_SECONDS = 30


def _retry_after_seconds(request: Request) -> int:
    """How long to tell a client to wait, from the settings in force.

    Derived per request rather than fixed at import, because
    `breaker_reset_after_seconds` is configurable: an operator who widens
    the breaker's cool-down to 120s would otherwise still see the service
    advertise 30, inviting every client back four times too early — while
    the circuit is still open, so each of those requests earns another
    503. The header and the breaker have to move together.

    Rounded UP. The value is a float and the header is defined as a
    whole number of seconds (RFC 9110 delay-seconds), and of the two
    directions to be wrong in, early is the one that costs something.

    Falls back to the module default defensively: `app.state.container`
    is only bound once the lifespan has run, and while this handler
    cannot fire before then in practice — reaching it means a request
    already got as far as the service layer — an error handler is a bad
    place to raise a second error.
    """
    container = getattr(request.app.state, "container", None)
    payment = getattr(getattr(container, "settings", None), "payment", None)
    if payment is None:
        return RETRY_AFTER_SECONDS
    return math.ceil(payment.breaker_reset_after_seconds)


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
# these are applied globally, in main.py's `FastAPI(responses=...)`.
#
# 404 belongs here too, and this is NOT the same 404 as `get_order`'s
# per-route one below. This one describes "the framework could not match
# any route at all" — the `_http_exception` handler's `StarletteHTTPException`
# path, reachable under ANY prefix, on literally every request the router
# does not recognise. `get_order`'s is "this specific order id does not
# exist", raised by `OrderNotFoundError` and reachable ONLY from that one
# route. Both are genuinely 404, both are genuinely global-vs-per-route in
# the sense that matters, and they carry different `type` values precisely
# because they mean different things: `.../http_error` here,
# `.../order_not_found` there. See docs/reference/errors.md for both rows.
# (An earlier version of this comment claimed the global 404 was NOT
# registered here "because only some routes can produce it" — that was
# true of OrderNotFoundError, but false of this one, and the two were
# conflated. Read `_http_exception` below before touching this again.)
DEFAULT_PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    # 400 is reachable on EVERY route, not only ones with a body: it is
    # what FastAPI raises when it cannot read the request at all.
    status.HTTP_400_BAD_REQUEST: problem_response("Malformed request"),
    # "No such resource at this path" — an unmatched route, from
    # `_http_exception` below. Not to be confused with `get_order`'s
    # "this order id does not exist", which is a different 404 with a
    # different `type`, documented per-route in api/v1/router.py instead.
    status.HTTP_404_NOT_FOUND: problem_response("No such resource"),
    status.HTTP_405_METHOD_NOT_ALLOWED: problem_response("Method not allowed"),
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


def _problem_response(
    problem: ProblemDetail, headers: Mapping[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
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

    @app.exception_handler(PaymentUnavailableError)
    async def _payment_unavailable(
        request: Request, exc: PaymentUnavailableError
    ) -> JSONResponse:
        """503, not 500. The caller did nothing wrong and the same request
        may well succeed later — which is exactly what 503 means and 500
        does not.

        `detail` is a fixed string, never `str(exc)`: the exception
        carries the provider's name and sometimes its URL, and this
        response is public. The full exception goes to the log instead,
        the same division ReadinessRegistry already makes.
        """
        _logger.warning("request.payment_unavailable", exc_info=exc)
        return _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/payment_unavailable",
                title="Payment provider unavailable",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The payment provider could not be reached. Try again.",
                instance=request.url.path,
            ),
            headers={"Retry-After": str(_retry_after_seconds(request))},
        )

    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Problem Details for errors raised by the framework itself.

        Starlette answers routing and body-reading failures by raising
        HTTPException, and it handles that type before the catch-all
        `Exception` handler below can ever see it. Without this handler its
        default takes over and returns `{"detail": "..."}` as
        `application/json` — so a service that documents RFC 9457
        everywhere silently returns a different shape for three of its most
        common responses: 405 on a wrong method, 404 on an unknown path,
        and 400 when a request body is not decodable as UTF-8. Found by
        Schemathesis, which reported the 400 as an undocumented status code.

        `StarletteHTTPException`, not `fastapi.HTTPException`: FastAPI's is
        a subclass, and the routing and body-reading failures raise the
        Starlette one. Registering the subclass would miss exactly the
        cases this exists for.

        `exc.detail` is safe to echo. For these framework errors it is a
        fixed string chosen by Starlette ("Not Found", "Method Not
        Allowed"), never assembled from request content — contrast the
        deliberate silence about exception messages in ReadinessRegistry.
        """
        return _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/http_error",
                title=str(exc.detail),
                status=exc.status_code,
                instance=request.url.path,
            ),
            # Load-bearing, and easy to leave out. Starlette's own 405
            # sets `Allow: POST`, which RFC 9110 REQUIRES on a 405, and it
            # carries it on `exc.headers`. A handler built only from
            # `detail` and `status_code` drops it. Verified: without this
            # argument every operation failed Schemathesis's
            # `unsupported_method` check with "TRACE returned 405 without
            # required Allow header".
            headers=exc.headers,
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
        # a shallower layer already accepted: without this, such an error
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
        #
        # Scope, now that M1's Task 10 has drawn the boundary, and after the
        # fix wave that followed the whole-branch review: this handler is
        # INTENDED to see a PydanticValidationError only when a raw pydantic
        # model rejects input a shallower layer had already accepted —
        # genuinely a client fault, genuinely a 422. That intention already
        # failed to hold once: services/order.py's PlaceOrder used to let a
        # use-case defect reach here too, and Task 10 closed that specific
        # gap by catching it and raising ServiceDefectError instead, which
        # has no handler and falls through to the catch-all below as a 500.
        # Then infrastructure/db/order_repository.py's get() opened an
        # identical hole in the same milestone: to_domain() reruns every
        # domain validator on the way OUT of storage, so a row corrupted at
        # rest (a hand edit, a restore from a mid-migration backup) failed
        # HERE too — a storage fault, not a client one, and the detail=
        # below used to quote the row's own field values, including
        # internal_note, into the response. get() now catches that case
        # itself and raises infrastructure.errors.CorruptPersistedDataError,
        # which likewise has no handler and falls through as a 500, so it no
        # longer reaches here either. Two boundaries have now each needed a
        # fix to keep this handler's assumption true, which is reason enough
        # not to trust a third will not exist: `include_input=False` below
        # means the NEXT such gap — wherever it turns out to live — fails
        # safe by construction instead of by remembering to patch this
        # comment again. See tests/api/test_errors.py's /deep-validation
        # route for the case this handler DOES exist for,
        # test_a_service_defect_is_a_500_not_a_422 for the first gap it no
        # longer mislabels, and
        # test_a_corrupted_persisted_order_is_a_500_not_a_422_and_does_not_leak
        # for the second.
        _logger.warning(
            "request.validation_error",
            # Same key names as AccessLogMiddleware, _domain_error above,
            # and _unexpected_error below, so every request-outcome event
            # can be aggregated on the same fields — this one used to omit
            # http.response.status_code while the other three carried it.
            **{
                "http.route": _route_template(request.scope),
                "http.response.status_code": status.HTTP_422_UNPROCESSABLE_CONTENT,
            },
        )
        return _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/validation_error",
                title="Request validation failed",
                status=status.HTTP_422_UNPROCESSABLE_CONTENT,
                # include_input=False: pydantic's default .errors() embeds
                # the VALUE that failed validation, not just where it failed
                # and why. Echoing that value back is fine when it is the
                # client's own request body — but this handler's whole
                # reason to exist is catching validation that happens BELOW
                # the request boundary (see the Scope comment above), where
                # the value being validated is not always something the
                # client sent. Eliding it here keeps the field location and
                # the constraint message, which is what a caller needs to
                # fix a genuine 422, without depending on every future
                # caller of this handler being a case where echoing the
                # value back is safe. Contrast the RequestValidationError
                # handler above, which keeps str(exc.errors()) as is: there,
                # the input IS always the client's own request body, so
                # echoing it back is the entire point of a 422.
                detail=str(exc.errors(include_input=False)),
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
