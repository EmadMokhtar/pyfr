"""Seed a running service with a fixed set of orders.

    just seed                      # against localhost; state in .seed-state.json
    docker compose run --rm seed   # what `just up` runs once `app` is healthy

Goes through the HTTP API on purpose: it works against every backend
combination the same way, it exercises the real request path (payment
authorisation included), and it depends on nothing but the published
contract. Plain dicts rather than the API's Pydantic schemas for the same
reason -- this is a client.

Idempotent through a state file rather than through the API, because
order ids are server-generated and there is no list endpoint (adding one
for a development tool would be a contract change). The file maps each
seed key to the id the service assigned. On every run each recorded id
is checked with a GET and re-created only when it is gone -- which is
what happens after `just down` wipes the database but not the file.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

import httpx

ORDERS_PATH = "/api/v1/orders"

# Deterministic on purpose: the same customers and lines every time, so
# the documentation can name them. No order totals 999.99 -- that amount
# is what the WireMock payment stub (ops/payment-stub/mappings/decline.json)
# declines, and a seed that fails on `just up` is worse than none.
SEED_ORDERS: dict[str, dict[str, Any]] = {
    "espresso-beans": {
        "customer_id": "0f1d2c3b-4a59-4e6f-8a7b-9c0d1e2f3a4b",
        "lines": [
            {
                "sku": "beans-1kg",
                "quantity": 2,
                "unit_amount": "18.50",
                "currency": "EUR",
            }
        ],
    },
    "filter-papers": {
        "customer_id": "0f1d2c3b-4a59-4e6f-8a7b-9c0d1e2f3a4b",
        "lines": [
            {
                "sku": "filter-100",
                "quantity": 3,
                "unit_amount": "4.25",
                "currency": "EUR",
            }
        ],
    },
    "grinder": {
        "customer_id": "7e6d5c4b-3a29-4180-9f8e-7d6c5b4a3928",
        "lines": [
            {
                "sku": "grinder-pro",
                "quantity": 1,
                "unit_amount": "249.00",
                "currency": "EUR",
            }
        ],
    },
    "mixed-basket": {
        "customer_id": "7e6d5c4b-3a29-4180-9f8e-7d6c5b4a3928",
        "lines": [
            {
                "sku": "mug-ceramic",
                "quantity": 4,
                "unit_amount": "9.90",
                "currency": "EUR",
            },
            {
                "sku": "spoon-set",
                "quantity": 1,
                "unit_amount": "12.40",
                "currency": "EUR",
            },
        ],
    },
    "bulk-order": {
        "customer_id": "c1b2a394-8576-4e6f-a0b1-c2d3e4f5a6b7",
        "lines": [
            {
                "sku": "beans-1kg",
                "quantity": 25,
                "unit_amount": "18.50",
                "currency": "USD",
            }
        ],
    },
}


class SeededOrder(NamedTuple):
    key: str
    order_id: str
    total: str
    created: bool


class SeedError(RuntimeError):
    """The service rejected a request. Orders already created stay created."""


def _load_state(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    return {str(key): str(value) for key, value in data.get("orders", {}).items()}


def _save_state(path: Path, orders: dict[str, str]) -> None:
    path.write_text(
        json.dumps({"orders": orders}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _money(total: dict[str, Any]) -> str:
    return f"{total['amount']} {total['currency']}"


def seed(client: httpx.Client, state_path: Path) -> list[SeededOrder]:
    """Create every seed order that does not already exist; report them all."""
    known = _load_state(state_path)
    result: list[SeededOrder] = []
    for key, payload in SEED_ORDERS.items():
        order_id = known.get(key)
        if order_id is not None:
            existing = client.get(f"{ORDERS_PATH}/{order_id}")
            if existing.status_code == 200:
                _ensure_receipt(client, order_id)
                total = _money(existing.json()["total"])
                result.append(SeededOrder(key, order_id, total, created=False))
                continue
            if existing.status_code != 404:
                raise SeedError(
                    f"GET {ORDERS_PATH}/{order_id} returned {existing.status_code}"
                )

        created = client.post(ORDERS_PATH, json=payload)
        if created.status_code != 201:
            raise SeedError(
                f"POST {ORDERS_PATH} for {key!r} returned "
                f"{created.status_code}: {created.text}"
            )
        body = created.json()
        order_id = str(body["id"])

        # Saved IMMEDIATELY after the POST, before anything else can fail:
        # the order exists on the server from this moment, and an id that
        # is not in the file is an order the next run cannot see and will
        # create again. Per order rather than at the end, for the same
        # reason -- a failure on the fourth order must not lose the three
        # ids already issued.
        known[key] = order_id
        _save_state(state_path, known)

        _ensure_receipt(client, order_id)
        result.append(SeededOrder(key, order_id, _money(body["total"]), created=True))
    return result


def _ensure_receipt(client: httpx.Client, order_id: str) -> None:
    """Ask for the order's receipt, so the receipt store holds one per order.

    The endpoint renders and stores the receipt on the first request and
    serves the stored bytes afterwards, so asking on every run is
    idempotent -- and it is what lets a run that failed here last time
    (the order recorded, the receipt never fetched) finish the job.
    """
    receipt = client.get(f"{ORDERS_PATH}/{order_id}/receipt")
    if receipt.status_code != 200:
        raise SeedError(
            f"GET {ORDERS_PATH}/{order_id}/receipt returned {receipt.status_code}"
        )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Seed a running reference service with a fixed set of orders."
    )
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--state", type=Path, default=Path(".seed-state.json"))
    args = parser.parse_args(argv)

    with httpx.Client(base_url=args.base_url, timeout=10.0) as client:
        try:
            seeded = seed(client, args.state)
        except (SeedError, httpx.HTTPError) as exc:
            print(f"seed failed: {exc}", file=sys.stderr)
            return 1

    width = max(len(order.key) for order in seeded)
    for order in seeded:
        state = "created" if order.created else "exists"
        print(f"{order.key:<{width}}  {order.order_id}  {order.total:>12}  {state}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
