import json
from collections.abc import Iterator
from uuid import uuid4

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from reference_service.api.errors import register_error_handlers, status_for
from reference_service.api.middleware import CORRELATION_HEADER, CorrelationIdMiddleware
from reference_service.domain.errors import DomainError, OrderNotFoundError
from reference_service.domain.order import OrderId
from reference_service.observability.logging import configure_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    structlog.reset_defaults()


class UnmappedError(DomainError):
    code = "unmapped"
    title = "Unmapped rule"


class _StrictlyPositive(BaseModel):
    value: int = Field(gt=0)


def build_app() -> FastAPI:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/missing")
    async def missing() -> None:
        raise OrderNotFoundError(OrderId(uuid4()))

    @app.get("/unmapped")
    async def unmapped() -> None:
        raise UnmappedError("something else broke")

    @app.get("/exploding")
    async def exploding() -> None:
        raise RuntimeError("a secret internal detail")

    @app.get("/deep-validation")
    async def deep_validation() -> None:
        # A raw pydantic model validated somewhere deep in a call stack,
        # the way a use case validates a domain value object — not the
        # request body FastAPI already validated on the way in.
        _StrictlyPositive(value=-1)

    return app


def test_a_domain_error_becomes_problem_details() -> None:
    client = TestClient(build_app())

    response = client.get("/missing")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    body = response.json()
    assert body["title"] == "Order not found"
    assert body["status"] == 404
    assert body["instance"] == "/missing"
    assert "order_not_found" in body["type"]


def test_an_unmapped_domain_error_defaults_to_422() -> None:
    client = TestClient(build_app())

    assert client.get("/unmapped").status_code == 422


def test_an_unexpected_error_does_not_leak_internals() -> None:
    client = TestClient(build_app(), raise_server_exceptions=False)

    response = client.get("/exploding")

    assert response.status_code == 500
    body = response.json()
    assert "a secret internal detail" not in response.text
    assert body["title"] == "Internal server error"


def test_an_unhandled_error_still_carries_the_correlation_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The one scenario correlation ids exist for: joining a crash to its request.

    A handler registered for `Exception` becomes ServerErrorMiddleware's
    handler, which sits OUTSIDE CorrelationIdMiddleware. Without recovering
    the id from the ASGI scope, the response would carry no X-Request-ID
    and the traceback log line would carry no correlation_id — a customer
    reporting a request id could never be joined to its stack trace.
    """
    configure_logging(environment="production", level="info", levels={})

    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/exploding")
    async def exploding() -> None:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    response = client.get("/exploding", headers={CORRELATION_HEADER: "crash-1"})

    assert response.status_code == 500
    assert response.headers[CORRELATION_HEADER] == "crash-1"

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    error_record = next(r for r in records if r["event"] == "request.unhandled_error")
    assert error_record["correlation_id"] == "crash-1"
    # Same key names as AccessLogMiddleware, and no raw path: "/exploding"
    # itself would be a bounded route here, but the point is that this
    # field is the ROUTE TEMPLATE, not request.url.path.
    assert error_record["http.route"] == "/exploding"
    assert error_record["http.response.status_code"] == 500
    assert "path" not in error_record


def test_a_domain_error_log_line_uses_the_same_field_names_as_the_access_log(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`errors.py` and `middleware.py` must agree on field names.

    Otherwise a dashboard querying the OpenTelemetry HTTP semantic
    convention names (`http.response.status_code`) never sees a domain
    error's log line, which used to say `status` instead.
    """
    configure_logging(environment="production", level="info", levels={})
    client = TestClient(build_app())

    client.get("/missing")

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    domain_record = next(r for r in records if r["event"] == "request.domain_error")
    assert domain_record["http.response.status_code"] == 404
    assert "status" not in domain_record


def test_a_raw_pydantic_validation_error_becomes_a_422_not_a_500() -> None:
    """The net: a raw pydantic ValidationError raised below the api layer.

    Without a handler for it, this is neither a DomainError nor a
    RequestValidationError, so it falls through to the catch-all and
    answers 500 for input FastAPI's own request validation never saw.
    """
    client = TestClient(build_app())

    response = client.get("/deep-validation")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Request validation failed"


def test_a_pydantic_validation_error_is_logged_at_warning(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The safety net for cross-layer validation gaps must stay loud.

    Before this handler existed, the same input crashed with a 500 and a
    full traceback via `_logger.exception`. The status change to 422 was
    correct; going from a full traceback to no log record at all was not
    - it made the next cross-layer validation asymmetry invisible instead
    of loud. `warning`, not `exception`: this is a client-fault 422, not a
    server fault, but it must still be visible.
    """
    configure_logging(environment="production", level="info", levels={})

    app = FastAPI()
    register_error_handlers(app)
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/deep-validation")
    async def deep_validation() -> None:
        _StrictlyPositive(value=-1)

    client = TestClient(app)
    response = client.get("/deep-validation", headers={CORRELATION_HEADER: "warn-1"})

    assert response.status_code == 422

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    warning_record = next(
        r for r in records if r["event"] == "request.validation_error"
    )
    assert warning_record["level"] == "warning"
    # Carried via structlog.contextvars.merge_contextvars, not passed
    # explicitly - this handler runs inside CorrelationIdMiddleware, unlike
    # the catch-all Exception handler.
    assert warning_record["correlation_id"] == "warn-1"
    assert warning_record["http.route"] == "/deep-validation"
    # Regression: this field used to be missing here while the access log,
    # request.domain_error and request.unhandled_error all carried it,
    # making this one event unable to join the others on status code.
    assert warning_record["http.response.status_code"] == 422


def test_request_validation_produces_problem_details() -> None:
    app = FastAPI()
    register_error_handlers(app)

    @app.get("/items")
    async def items(count: int) -> dict[str, int]:
        return {"count": count}

    response = TestClient(app).get("/items?count=not-a-number")

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Request validation failed"


def test_status_for_maps_known_errors_and_defaults_unknown_ones() -> None:
    assert status_for(OrderNotFoundError(OrderId(uuid4()))) == 404
    assert status_for(UnmappedError("x")) == 422


def test_a_subclass_inherits_its_parent_status() -> None:
    """A subclass must not silently fall through to the 422 default."""

    class OrderAlreadyShippedError(OrderNotFoundError):
        code = "order_already_shipped"
        title = "Order already shipped"

    assert status_for(OrderAlreadyShippedError(OrderId(uuid4()))) == 404
