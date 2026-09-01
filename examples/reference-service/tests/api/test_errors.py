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
from reference_service.main import create_app
from reference_service.observability.logging import configure_logging
from reference_service.settings import Settings


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
    async def deep_validation(value: int) -> None:
        # `value` already passed FastAPI's own edge validation — it is a
        # well-formed int, the only thing the edge schema checks. The
        # deeper validator behind it enforces a rule the edge schema never
        # captured, the way a use case validates a domain value object
        # after its own request schema has already let the input through.
        # This is deliberately NOT a hardcoded bad literal: a value that
        # never came from the client is a server defect, not client input,
        # and is exactly the case this handler was never meant to catch —
        # see the comment on _pydantic_validation_error in api/errors.py.
        _StrictlyPositive(value=value)

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

    `value=-1` passes FastAPI's own edge validation (it is a well-formed
    int) and is rejected by `_StrictlyPositive`, the deeper validator
    behind it — real client input reaching a cross-layer validation gap,
    not a hardcoded server defect. Without a handler for this, it is
    neither a DomainError nor a RequestValidationError, so it falls
    through to the catch-all and answers 500 for input that was, from the
    client's point of view, perfectly ordinary.
    """
    client = TestClient(build_app())

    response = client.get("/deep-validation?value=-1")

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
    async def deep_validation(value: int) -> None:
        _StrictlyPositive(value=value)

    client = TestClient(app)
    response = client.get(
        "/deep-validation?value=-1", headers={CORRELATION_HEADER: "warn-1"}
    )

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


def test_a_service_defect_is_a_500_not_a_422(settings: Settings) -> None:
    """The end-to-end statement of what Task 10 fixed.

    Before this, a ValidationError raised inside a use case reached
    _pydantic_validation_error and became a 422 telling the caller their
    request was invalid. It is now a 500 that says the fault is ours.

    Built on the real `create_app`, not `build_app()` above: this must
    exercise the real /api/v1/orders route and its real dependency wiring
    (api/deps.py -> services/order.py), which is what actually raises the
    use-case defect in the first place - the error handlers alone have
    nothing to catch here. The shared `client` fixture in tests/conftest.py
    is deliberately NOT used: it takes `raise_server_exceptions` at its
    default `True`, under which Starlette's ServerErrorMiddleware re-raises
    the exception into the test after sending the response (it always
    does, whether or not a handler is registered - see
    `ServerErrorMiddleware.__call__`), so the test would error instead of
    getting a response back. Same pattern as
    `test_an_unexpected_error_does_not_leak_internals` and
    `test_an_unhandled_error_still_carries_the_correlation_id` above, both
    of which build their own client for the same reason.
    """
    from decimal import Decimal

    from reference_service.domain.order import Money
    from reference_service.services import order as order_module

    with TestClient(create_app(settings), raise_server_exceptions=False) as client:
        with pytest.MonkeyPatch.context() as patch:
            patch.setattr(
                order_module,
                "total_of",
                lambda lines: Money(amount=Decimal("999.99"), currency="EUR"),
            )
            response = client.post(
                "/api/v1/orders",
                json={
                    "customer_id": "11111111-1111-1111-1111-111111111111",
                    "lines": [
                        {
                            "sku": "apple",
                            "quantity": 1,
                            "unit_amount": "1.50",
                            "currency": "EUR",
                        }
                    ],
                },
            )

    assert response.status_code == 500
    # And it still describes none of our internals.
    body = response.json()
    assert body["title"] == "Internal server error"
    assert "detail" not in body or body["detail"] is None


class _FakeCorruptScalarResult:
    def __init__(self, rows: list[object]) -> None:
        self._rows = rows

    def all(self) -> list[object]:
        return self._rows


class _FakeCorruptSession:
    """Answers get()'s three calls with a row that fails domain validation.

    Same shape as tests/unit/test_order_repository.py's fake — duplicated
    rather than imported across test tiers, matching this suite's existing
    style of a locally-defined make_order per file (see tests/fakes.py,
    tests/unit/test_db_mappers.py, tests/integration/test_order_repository.py).
    """

    def __init__(self, row: object, lines: list[object]) -> None:
        self._row = row
        self._lines = lines

    async def __aenter__(self) -> "_FakeCorruptSession":
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def connection(self, **kwargs: object) -> None:
        return None

    async def scalar(self, *args: object, **kwargs: object) -> object:
        return self._row

    async def scalars(self, *args: object, **kwargs: object) -> _FakeCorruptScalarResult:
        return _FakeCorruptScalarResult(self._lines)


class _FakeCorruptSessionmaker:
    def __init__(self, row: object, lines: list[object]) -> None:
        self._row = row
        self._lines = lines

    def __call__(self) -> _FakeCorruptSession:
        return _FakeCorruptSession(self._row, self._lines)


def test_a_corrupted_persisted_order_is_a_500_not_a_422_and_does_not_leak(
    settings: Settings,
) -> None:
    """The live reproduction from the M1 whole-branch review, without a database.

    A row whose stored total disagrees with its lines used to reach
    _pydantic_validation_error as a raw pydantic.ValidationError, which
    interpolated the row's own field values — including internal_note, the
    one field api/v1/mappers.py exists specifically to keep off the wire —
    into a 422 body. Confirmed against the unpatched code: GET returned 422
    with `'internal_note': 'FRAUD REVIEW: customer flagged, do not ship'`
    inside the response body, verbatim.

    infrastructure/db/order_repository.py's get() now catches that case
    itself and raises CorruptPersistedDataError, which has no registered
    handler; this proves the full stack — the real route, the real
    dependency wiring, the real PostgresOrderRepository.get() and mappers.py
    — actually behaves that way end to end. _FakeCorruptSessionmaker fakes
    out only the database I/O boundary; get() itself runs unmodified,
    production code.

    Built on the real create_app, like test_a_service_defect_is_a_500_not_a_422
    above and for the same reason: this must exercise the real
    /api/v1/orders/{id} route and its real dependency wiring, which is what
    actually raises the defect. The shared `client` fixture is deliberately
    NOT used, for the same raise_server_exceptions reason documented on
    that test.
    """
    from decimal import Decimal

    from reference_service.api.deps import get_orders
    from reference_service.domain.order import (
        CustomerId,
        Money,
        Order,
        OrderLine,
        total_of,
    )
    from reference_service.infrastructure.db.mappers import line_values, order_values
    from reference_service.infrastructure.db.models import OrderLineRow, OrderRow
    from reference_service.infrastructure.db.order_repository import (
        PostgresOrderRepository,
    )

    secret = "FRAUD REVIEW: customer flagged, do not ship"
    lines = (
        OrderLine(
            sku="apple",
            quantity=3,
            unit_price=Money(amount=Decimal("1.50"), currency="EUR"),
        ),
    )
    order = Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=lines,
        total=total_of(lines),
        internal_note=secret,
    )
    # The stored total disagrees with the lines — the exact corruption
    # to_domain()'s revalidation exists to catch on the way back out.
    row = OrderRow(**{**order_values(order), "total_amount": Decimal("999.99")})
    line_rows = [OrderLineRow(**values) for values in line_values(order)]
    repository = PostgresOrderRepository(
        _FakeCorruptSessionmaker(row, line_rows)  # type: ignore[arg-type]
    )

    app = create_app(settings)
    app.dependency_overrides[get_orders] = lambda: repository
    client = TestClient(app, raise_server_exceptions=False)

    response = client.get(f"/api/v1/orders/{order.id}")

    assert response.status_code == 500
    assert secret not in response.text
    assert "internal_note" not in response.text
    body = response.json()
    assert body["title"] == "Internal server error"
    assert "detail" not in body or body["detail"] is None


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
