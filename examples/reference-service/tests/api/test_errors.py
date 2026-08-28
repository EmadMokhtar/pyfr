from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic import BaseModel, Field

from reference_service.api.errors import register_error_handlers, status_for
from reference_service.domain.errors import DomainError, OrderNotFoundError
from reference_service.domain.order import OrderId


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
