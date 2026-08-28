from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from reference_service.api.errors import register_error_handlers, status_for
from reference_service.domain.errors import DomainError, OrderNotFoundError
from reference_service.domain.order import OrderId


class UnmappedError(DomainError):
    code = "unmapped"
    title = "Unmapped rule"


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


def test_status_for_is_the_only_place_that_knows_http() -> None:
    assert status_for(OrderNotFoundError(OrderId(uuid4()))) == 404
    assert status_for(UnmappedError("x")) == 422
