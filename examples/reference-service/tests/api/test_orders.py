import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from reference_service.api.v1.schemas import OrderResponse
from reference_service.domain.order import Order
from reference_service.main import create_app
from reference_service.settings import Settings


def a_payload(quantity: int = 2, amount: str = "10.00") -> dict[str, object]:
    return {
        "customer_id": str(uuid4()),
        "lines": [
            {
                "sku": "sku-1",
                "quantity": quantity,
                "unit_amount": amount,
                "currency": "EUR",
            }
        ],
    }


def test_placing_an_order_returns_201_with_a_location(client: TestClient) -> None:
    response = client.post("/api/v1/orders", json=a_payload())

    assert response.status_code == 201
    body = response.json()
    assert response.headers["location"] == f"/api/v1/orders/{body['id']}"


def test_the_response_carries_the_computed_total(client: TestClient) -> None:
    response = client.post("/api/v1/orders", json=a_payload(quantity=3, amount="10.00"))

    total = response.json()["total"]
    assert total == {"amount": "30.00", "currency": "EUR"}


def test_a_placed_order_can_be_fetched(client: TestClient) -> None:
    created = client.post("/api/v1/orders", json=a_payload()).json()

    fetched = client.get(f"/api/v1/orders/{created['id']}")

    assert fetched.status_code == 200
    assert fetched.json() == created


def test_fetching_an_unknown_order_is_problem_details_404(
    client: TestClient,
) -> None:
    response = client.get(f"/api/v1/orders/{uuid4()}")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["title"] == "Order not found"


def test_internal_domain_fields_are_never_exposed(client: TestClient) -> None:
    """The outcome: an internal field must not reach a client.

    This asserts the result, not the mechanism. See
    `test_the_response_schema_never_declares_internal_fields` for where the
    guarantee actually comes from — it is NOT the mapper.
    """
    created = client.post("/api/v1/orders", json=a_payload()).json()

    assert "internal_note" not in created
    assert "internal_note" not in client.get(f"/api/v1/orders/{created['id']}").text


def test_a_negative_quantity_is_refused_with_problem_details(
    client: TestClient,
) -> None:
    response = client.post("/api/v1/orders", json=a_payload(quantity=-1))

    assert response.status_code == 422
    assert response.headers["content-type"].startswith("application/problem+json")


def test_an_order_with_no_lines_is_refused(client: TestClient) -> None:
    payload = a_payload()
    payload["lines"] = []

    assert client.post("/api/v1/orders", json=payload).status_code == 422


def test_the_real_application_pins_its_middleware_order(
    settings: Settings,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Pins the ordering in `create_app`, not in a test helper.

    Task 11's equivalent test builds its own app locally, so reversing the
    two `add_middleware` lines in `main.py` itself goes undetected there.
    This is the earliest point the production ordering can be pinned at
    all: until this task, every route the real application served was a
    health endpoint, and those are excluded from the access log.

    If this fails while Task 11's version passes, the two `add_middleware`
    lines in `main.py` are the wrong way round — correlation must wrap the
    access log, or the record is emitted outside the bound context.
    """
    # Built here rather than via the shared `client` fixture: that fixture
    # calls `create_app` — and therefore `configure_logging` — during
    # pytest's setup phase, binding the log handler to a stream `capsys`
    # cannot read back during the call phase. Building it inside the test
    # body puts both on the same captured stdout.
    with TestClient(create_app(settings)) as client:
        client.post(
            "/api/v1/orders",
            json=a_payload(),
            headers={"X-Request-ID": "real-app-1"},
        )

    records = [json.loads(line) for line in capsys.readouterr().out.splitlines()]
    access = next(record for record in records if record.get("event") == "http.access")
    assert access["correlation_id"] == "real-app-1"
    assert access["http.route"] == "/api/v1/orders"


def test_the_openapi_document_describes_the_endpoints(client: TestClient) -> None:
    schema = client.get("/openapi.json").json()

    assert "/api/v1/orders" in schema["paths"]
    assert "/api/v1/orders/{order_id}" in schema["paths"]


def test_the_response_schema_never_declares_internal_fields() -> None:
    """Where the guarantee actually comes from, stated honestly.

    Note what does NOT provide it: calling the mapper. FastAPI validates
    every return value against `response_model=OrderResponse`, and that
    drops any field the schema does not declare — so a route returning the
    domain entity directly would also hide `internal_note`. The real
    guarantee is that `OrderResponse` is a separate type which never
    declares the field in the first place.

    The mapper earns its place for a different reason: it lets the domain
    model be renamed or restructured without touching the wire contract.
    """
    assert "internal_note" in Order.model_fields
    assert "internal_note" not in OrderResponse.model_fields
