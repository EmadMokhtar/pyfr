import json
from collections.abc import Iterator
from typing import Any

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.types import Message, Receive, Scope, Send

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


def test_an_unmatched_path_is_not_logged_verbatim(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """404s are mostly bots probing URLs; their paths must not become labels.

    `scope["route"]` is unset when nothing matched, and falling back to the
    raw path would put one distinct value in the log per probed URL — the
    exact unbounded cardinality this field exists to avoid.
    """
    configure_logging(environment="production", level="info", levels={})
    client = TestClient(build_app())

    client.get("/definitely-not-a-real-endpoint-8f3a")

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    access = next(r for r in records if r["event"] == "http.access")
    assert access["http.route"] == "<unmatched>"
    assert access["http.response.status_code"] == 404
    assert "definitely-not-a-real-endpoint" not in json.dumps(access)


def test_the_access_record_itself_carries_the_correlation_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """This is what pins the middleware registration order.

    `add_middleware` inserts at the front, so the last registered ends up
    outermost. Correlation must wrap the access log, or the access record is
    emitted outside the bound context and silently loses its id. Reverse the
    two `add_middleware` lines and only this test fails.
    """
    configure_logging(environment="production", level="info", levels={})
    client = TestClient(build_app())

    client.get("/orders/abc", headers={CORRELATION_HEADER: "order-lookup-1"})

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    access = next(r for r in records if r["event"] == "http.access")
    assert access["correlation_id"] == "order-lookup-1"


def test_the_access_log_still_records_when_the_handler_raises(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The record is emitted from a `finally`, so a failure cannot skip it."""
    configure_logging(environment="production", level="info", levels={})

    app = FastAPI()
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)

    @app.get("/explodes")
    async def explodes() -> None:
        raise RuntimeError("boom")

    client = TestClient(app, raise_server_exceptions=False)
    client.get("/explodes", headers={CORRELATION_HEADER: "failing-1"})

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    access = next(r for r in records if r["event"] == "http.access")
    assert access["http.response.status_code"] == 500
    assert access["correlation_id"] == "failing-1"


def test_health_endpoints_are_not_access_logged(
    capsys: pytest.CaptureFixture[str],
) -> None:
    configure_logging(environment="production", level="info", levels={})
    client = TestClient(build_app())

    client.get("/healthz")

    out = capsys.readouterr().out
    assert "http.access" not in out


def test_each_request_is_tagged_with_its_own_correlation_id(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Named for what it proves.

    It does NOT prove context is cleared between requests: the correlation
    id is re-bound every request, so it overwrites rather than leaks, and
    `TestClient` gives each request a fresh context anyway. See
    `test_bound_context_is_cleared_within_a_shared_context` for the cleanup.
    """
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


async def test_bound_context_is_cleared_within_a_shared_context() -> None:
    """The only test here that makes `clear_contextvars` load-bearing.

    Two things had to be understood to write it. First, the correlation id
    cannot prove the cleanup works: it is re-bound on every request, so it
    overwrites rather than leaks. Second, `TestClient` runs each request in
    a fresh `contextvars.Context`, so NO test built on it can exercise this
    cleanup at all — a TestClient-based version of this test passes with
    `clear_contextvars` deleted entirely.

    Driving the ASGI callable directly puts both requests in one task, and
    therefore one context, which is the situation the cleanup exists for.
    The risk it guards is real: a `user_id` bound by one handler and
    surviving into the next request attributes one person's activity to
    another in the logs.
    """
    seen_on_second_request: dict[str, Any] = {}

    async def inner(scope: Scope, receive: Receive, send: Send) -> None:
        if scope["path"] == "/binds":
            structlog.contextvars.bind_contextvars(user_id="user-1")
        else:
            seen_on_second_request.update(structlog.contextvars.get_contextvars())
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b""})

    app = CorrelationIdMiddleware(inner)

    async def receive() -> Message:
        return {"type": "http.request", "body": b"", "more_body": False}

    async def send(message: Message) -> None:
        return None

    # Intentionally minimal — only what CorrelationIdMiddleware reads — not a
    # representative Starlette scope.
    def scope_for(path: str) -> Scope:
        return {"type": "http", "method": "GET", "path": path, "headers": []}

    await app(scope_for("/binds"), receive, send)
    await app(scope_for("/quiet"), receive, send)

    assert "user_id" not in seen_on_second_request, (
        "a context variable bound during the previous request leaked"
    )
