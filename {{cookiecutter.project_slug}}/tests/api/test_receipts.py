"""The receipt endpoint.

Seeding follows tests/api/test_orders.py. Two of these tests cannot use the
POST route, and the reason is worth stating: `internal_note` is not in the
request schema, so an order carrying one cannot be created through the API
at all. Those tests build the Order directly and swap the repository in with
`app.dependency_overrides`, the same mechanism test_orders.py already uses
to swap the payment gateway.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from {{ cookiecutter.package_name }}.api.deps import get_orders, get_receipts
from {{ cookiecutter.package_name }}.api.v1.schemas import ReceiptResponse
from {{ cookiecutter.package_name }}.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from {{ cookiecutter.package_name }}.domain.receipt_render import render_receipt
from {{ cookiecutter.package_name }}.infrastructure.errors import StorageUnavailableError
from {{ cookiecutter.package_name }}.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from {{ cookiecutter.package_name }}.infrastructure.memory.receipt_store import (
    InMemoryReceiptStore,
)
from {{ cookiecutter.package_name }}.main import create_app
from {{ cookiecutter.package_name }}.settings import Settings


def a_payload() -> dict[str, object]:
    """The same shape tests/api/test_orders.py posts."""
    return {
        "customer_id": str(uuid4()),
        "lines": [
            {
                "sku": "sku-1",
                "quantity": 2,
                "unit_amount": "10.50",
                "currency": "EUR",
            }
        ],
    }


def an_order(internal_note: str | None = None) -> Order:
    line = OrderLine(
        sku="sku-1",
        quantity=2,
        unit_price=Money(amount=Decimal("10.50"), currency="EUR"),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=(line,),
        total=Money(amount=Decimal("21.00"), currency="EUR"),
        internal_note=internal_note,
    )


@pytest.fixture
def stored_order() -> Order:
    return an_order(internal_note="customer disputed a previous order")


@pytest.fixture
def client_with_a_stored_order(
    settings: Settings, stored_order: Order
) -> Iterator[TestClient]:
    """A client whose repository already holds `stored_order`.

    `asyncio.run` for the seed, and it is safe here for a specific reason:
    InMemoryOrderRepository holds nothing bound to an event loop — its
    save() is a dict write behind an async signature — so running it on a
    throwaway loop that then closes leaves nothing dangling. The TestClient
    below runs the app on its own loop afterwards. Do NOT copy this pattern
    for a repository backed by a real connection pool, where a closed loop
    would take the pool's sockets with it.
    """
    orders = InMemoryOrderRepository()
    asyncio.run(orders.save(stored_order))

    app = create_app(settings)
    app.dependency_overrides[get_orders] = lambda: orders
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_with_a_broken_store(
    settings: Settings, stored_order: Order
) -> Iterator[TestClient]:
    orders = InMemoryOrderRepository()
    asyncio.run(orders.save(stored_order))

    class BrokenStore:
        async def get(self, order_id: OrderId) -> bytes | None:
            raise StorageUnavailableError("bucket unreachable")

        async def put(self, order_id: OrderId, content: bytes) -> None:
            raise StorageUnavailableError("bucket unreachable")

    app = create_app(settings)
    app.dependency_overrides[get_orders] = lambda: orders
    # The class itself, not an instance — FastAPI calls it to build the
    # dependency. Same form test_orders.py uses for DecliningPaymentGateway.
    app.dependency_overrides[get_receipts] = BrokenStore
    with TestClient(app) as test_client:
        yield test_client


def test_a_receipt_is_returned_as_json(client: TestClient) -> None:
    """The happy path needs no override at all: POST an order, ask for its
    receipt. This is the arrangement a real caller has."""
    created = client.post("/api/v1/orders", json=a_payload()).json()

    response = client.get(f"/api/v1/orders/{created['id']}/receipt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    document = response.json()
    assert document["order_id"] == created["id"]
    assert document["total"] == "21.00"


def test_the_receipt_matches_what_the_renderer_produces(
    client_with_a_stored_order: TestClient, stored_order: Order
) -> None:
    response = client_with_a_stored_order.get(
        f"/api/v1/orders/{stored_order.id}/receipt"
    )

    assert response.content == render_receipt(stored_order)


def test_the_receipt_never_carries_the_internal_note(
    client_with_a_stored_order: TestClient, stored_order: Order
) -> None:
    """Order.internal_note is documented as never exposed over HTTP, and a
    receipt is served over HTTP. It cannot be set through the API, which is
    exactly why this test seeds the repository directly — otherwise the
    field would never be populated and the test would pass vacuously."""
    assert stored_order.internal_note is not None

    response = client_with_a_stored_order.get(
        f"/api/v1/orders/{stored_order.id}/receipt"
    )

    assert b"internal_note" not in response.content
    assert b"disputed" not in response.content


def test_a_second_request_serves_the_stored_object(
    settings: Settings, stored_order: Order
) -> None:
    """Proves storage is actually load-bearing rather than decorative.

    The store is seeded with bytes the renderer would never produce, so a
    handler that re-rendered on every request would fail this. An equality
    check against render_receipt could not tell the two apart.
    """
    orders = InMemoryOrderRepository()
    asyncio.run(orders.save(stored_order))
    receipts = InMemoryReceiptStore()
    asyncio.run(receipts.put(stored_order.id, b'{"stored":"earlier"}'))

    app = create_app(settings)
    app.dependency_overrides[get_orders] = lambda: orders
    app.dependency_overrides[get_receipts] = lambda: receipts
    with TestClient(app) as test_client:
        response = test_client.get(f"/api/v1/orders/{stored_order.id}/receipt")

    assert response.content == b'{"stored":"earlier"}'


def test_an_unknown_order_is_a_problem_details_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/orders/{uuid4()}/receipt")

    assert response.status_code == 404
    assert response.headers["content-type"] == "application/problem+json"
    assert response.json()["type"].endswith("/order_not_found")


def test_a_malformed_identifier_is_a_422(client: TestClient) -> None:
    response = client.get("/api/v1/orders/not-a-uuid/receipt")

    assert response.status_code == 422


def test_an_unreachable_store_is_a_503_with_retry_after(
    client_with_a_broken_store: TestClient, stored_order: Order
) -> None:
    """503, not 500: the caller did nothing wrong and the same request may
    well succeed later — the same treatment PaymentUnavailableError gets."""
    response = client_with_a_broken_store.get(
        f"/api/v1/orders/{stored_order.id}/receipt"
    )

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    assert "Retry-After" in response.headers
    assert response.json()["type"].endswith("/storage_unavailable")
    # The adapter's own message must not reach the body: a real one carries
    # the bucket name, the endpoint URL and sometimes a credential fragment.
    assert "bucket unreachable" not in response.text


def test_the_documented_schema_matches_what_the_renderer_produces() -> None:
    """The drift gate for this endpoint.

    The 200 response is documented with ReceiptResponse but returned as raw
    bytes, so FastAPI never validates one against the other. Without this
    test the contract could describe a document the renderer stopped
    producing, and every client generated from it would be wrong.
    """
    order = an_order()

    document = json.loads(render_receipt(order))

    # Raises if the renderer's output does not satisfy the published schema.
    parsed = ReceiptResponse.model_validate(document)
    assert parsed.order_id == order.id
    assert parsed.total == "21.00"
    assert [line.sku for line in parsed.lines] == ["sku-1"]
