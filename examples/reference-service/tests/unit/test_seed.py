"""The seeder goes through the HTTP API, so the existing `client` fixture
(a TestClient, which IS an httpx.Client) exercises it against the
in-memory adapters with no server and no Docker."""

import json
from pathlib import Path
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from reference_service.api.deps import get_payments
from reference_service.main import create_app
from reference_service.seed import SEED_ORDERS, SeedError, main, seed
from reference_service.settings import Settings
from tests.fakes import DecliningPaymentGateway


def test_the_first_run_creates_every_order_and_records_it(
    client: TestClient, tmp_path: Path
) -> None:
    state = tmp_path / "state.json"

    seeded = seed(client, state)

    assert [order.key for order in seeded] == list(SEED_ORDERS)
    assert all(order.created for order in seeded)
    recorded = json.loads(state.read_text())["orders"]
    assert set(recorded) == set(SEED_ORDERS)
    for order in seeded:
        assert client.get(f"/api/v1/orders/{order.order_id}").status_code == 200
        assert client.get(f"/api/v1/orders/{order.order_id}/receipt").status_code == 200


def test_a_second_run_creates_nothing(client: TestClient, tmp_path: Path) -> None:
    state = tmp_path / "state.json"
    first = seed(client, state)

    second = seed(client, state)

    assert [order.order_id for order in second] == [order.order_id for order in first]
    assert not any(order.created for order in second)


def test_a_recorded_order_that_is_gone_is_recreated(
    client: TestClient, tmp_path: Path
) -> None:
    """After `just down` wipes the database, the state file still names
    ids the service has never heard of. Each one is a 404 and is re-made."""
    state = tmp_path / "state.json"
    seed(client, state)
    recorded = json.loads(state.read_text())
    stale_id = str(uuid4())
    recorded["orders"]["grinder"] = stale_id
    state.write_text(json.dumps(recorded))

    second = seed(client, state)

    by_key = {order.key: order for order in second}
    assert by_key["grinder"].created is True
    assert by_key["grinder"].order_id != stale_id
    assert sum(order.created for order in second) == 1
    assert json.loads(state.read_text())["orders"]["grinder"] == (
        by_key["grinder"].order_id
    )


def test_totals_are_what_the_service_computed(
    client: TestClient, tmp_path: Path
) -> None:
    totals = {order.key: order.total for order in seed(client, tmp_path / "s.json")}

    assert totals["espresso-beans"] == "37.00 EUR"
    assert totals["mixed-basket"] == "52.00 EUR"
    assert totals["bulk-order"] == "462.50 USD"


def test_no_seed_order_totals_the_stub_decline_amount() -> None:
    """ops/payment-stub/mappings/decline.json declines amount == 999.99."""
    for key, payload in SEED_ORDERS.items():
        total = sum(
            float(line["unit_amount"]) * int(line["quantity"])
            for line in payload["lines"]
        )
        assert round(total, 2) != 999.99, key


def test_a_declined_order_fails_loudly(settings: Settings, tmp_path: Path) -> None:
    app = create_app(settings)
    app.dependency_overrides[get_payments] = DecliningPaymentGateway
    with TestClient(app) as client:
        with pytest.raises(SeedError):
            seed(client, tmp_path / "s.json")


def test_main_returns_one_when_the_service_is_unreachable(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    # Port 9 is the discard service; nothing listens on it here.
    status = main(
        ["--base-url", "http://127.0.0.1:9", "--state", str(tmp_path / "s.json")]
    )

    assert status == 1
    assert "seed failed" in capsys.readouterr().err
