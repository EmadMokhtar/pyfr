import json
from collections.abc import Iterator

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from reference_service.api.middleware import (
    CORRELATION_HEADER,
    AccessLogMiddleware,
    CorrelationIdMiddleware,
)
from reference_service.observability.logging import configure_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    structlog.reset_defaults()


def build_app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/orders/{order_id}")
    async def get_order(order_id: str) -> dict[str, str]:
        structlog.get_logger().info("handler.ran")
        return {"order_id": order_id}

    @app.get("/healthz")
    async def healthz() -> dict[str, str]:
        return {"status": "ok"}

    return app


def test_an_absent_correlation_id_is_generated_and_returned() -> None:
    client = TestClient(build_app())

    response = client.get("/orders/abc")

    assert response.headers[CORRELATION_HEADER]
    assert len(response.headers[CORRELATION_HEADER]) >= 8


def test_a_supplied_correlation_id_is_echoed_back() -> None:
    client = TestClient(build_app())

    response = client.get("/orders/abc", headers={CORRELATION_HEADER: "abc-123"})

    assert response.headers[CORRELATION_HEADER] == "abc-123"


def test_the_correlation_id_reaches_log_lines_from_the_handler(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="production", level="info", levels={})
    client = TestClient(build_app())

    client.get("/orders/abc", headers={CORRELATION_HEADER: "abc-123"})

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    handler_record = next(r for r in records if r["event"] == "handler.ran")
    assert handler_record["correlation_id"] == "abc-123"


def test_the_access_log_records_the_route_template_not_the_raw_path(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Raw paths make every order id a distinct value: high cardinality."""
    configure_logging(environment="production", level="info", levels={})
    client = TestClient(build_app())

    client.get("/orders/8f3a-not-a-real-id")

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    access = next(r for r in records if r["event"] == "http.access")
    assert access["http.route"] == "/orders/{order_id}"
    assert access["http.request.method"] == "GET"
    assert access["http.response.status_code"] == 200
    assert isinstance(access["duration_ms"], float)
    assert "8f3a-not-a-real-id" not in json.dumps(access)


def test_health_endpoints_are_not_access_logged(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="production", level="info", levels={})
    client = TestClient(build_app())

    client.get("/healthz")

    out = capsys.readouterr().out
    assert "http.access" not in out


def test_context_does_not_leak_between_requests(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="production", level="info", levels={})
    client = TestClient(build_app())

    client.get("/orders/a", headers={CORRELATION_HEADER: "first"})
    capsys.readouterr()
    client.get("/orders/b", headers={CORRELATION_HEADER: "second"})

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records, "no log records captured, so this test proves nothing"

    # Assert the actual invariant rather than "every line carries the id".
    # Third-party libraries log through the standard-library bridge from
    # outside any request context — httpx emits a client-side INFO line for
    # every call — and those records legitimately have no correlation id.
    # Requiring one on every line tests the bridge, not the leak.
    seen = {record.get("correlation_id") for record in records}
    assert "first" not in seen, "the previous request's correlation id leaked"
    assert "second" in seen, "the current request's correlation id is missing"


def test_bound_context_does_not_leak_into_the_next_request(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """This is the test that makes `clear_contextvars` load-bearing.

    The correlation id alone cannot prove the cleanup works: it is re-bound
    on every request, so it overwrites rather than leaks, and the test above
    passes even with the cleanup removed. The real risk is any OTHER key a
    handler binds — a `user_id` surviving into the next request attributes
    one person's activity to another in the logs.
    """
    configure_logging(environment="production", level="info", levels={})

    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/binds")
    async def binds() -> dict[str, str]:
        structlog.contextvars.bind_contextvars(user_id="user-1")
        structlog.get_logger().info("handler.bound")
        return {"ok": "yes"}

    @app.get("/quiet")
    async def quiet() -> dict[str, str]:
        structlog.get_logger().info("handler.quiet")
        return {"ok": "yes"}

    client = TestClient(app)
    client.get("/binds")
    capsys.readouterr()
    client.get("/quiet")

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    assert records, "no log records captured, so this test proves nothing"
    assert all("user_id" not in record for record in records), (
        "a context variable bound during the previous request leaked"
    )
