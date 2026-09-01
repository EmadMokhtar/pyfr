"""The mapping between rows and the Order aggregate. No database involved."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
    total_of,
)
from reference_service.infrastructure.db.mappers import (
    line_values,
    order_values,
    to_domain,
)
from reference_service.infrastructure.db.models import OrderLineRow, OrderRow


def make_order(internal_note: str | None = None) -> Order:
    lines = (
        OrderLine(
            sku="apple",
            quantity=3,
            unit_price=Money(amount=Decimal("1.50"), currency="EUR"),
        ),
        OrderLine(
            sku="bread",
            quantity=1,
            unit_price=Money(amount=Decimal("2.25"), currency="EUR"),
        ),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=lines,
        total=total_of(lines),
        internal_note=internal_note,
    )


def test_order_values_flattens_money_into_two_columns() -> None:
    order = make_order(internal_note="staff pick")

    values = order_values(order)

    assert values == {
        "id": order.id,
        "customer_id": order.customer_id,
        "total_amount": Decimal("6.75"),
        "total_currency": "EUR",
        "internal_note": "staff pick",
    }


def test_line_values_numbers_the_lines_from_zero_in_order() -> None:
    """The line number is what makes `Order.lines` an ordered tuple again.

    Without it, a reloaded order's lines come back in whatever order
    PostgreSQL felt like returning them, which is not an error and not
    detectable by the total — reordered lines sum to the same money.
    """
    order = make_order()

    values = line_values(order)

    assert [value["line_number"] for value in values] == [0, 1]
    assert [value["sku"] for value in values] == ["apple", "bread"]
    assert values[0]["unit_amount"] == Decimal("1.50")
    assert values[0]["unit_currency"] == "EUR"
    assert all(value["order_id"] == order.id for value in values)


def test_to_domain_rebuilds_an_equal_order() -> None:
    order = make_order(internal_note="staff pick")

    row = OrderRow(**order_values(order))
    line_rows = [OrderLineRow(**values) for values in line_values(order)]

    assert to_domain(row, line_rows) == order


def test_to_domain_revalidates_the_invariants() -> None:
    """A row whose total disagrees with its lines must not load silently.

    Rows can be edited by hand, restored from a backup taken mid-migration,
    or written by another service. Rebuilding through the Pydantic model
    means Order.total_must_match_lines runs on the way OUT of the database
    too, so corruption surfaces at load with a readable error instead of
    flowing into a response.
    """
    order = make_order()
    row = OrderRow(**{**order_values(order), "total_amount": Decimal("999.99")})
    line_rows = [OrderLineRow(**values) for values in line_values(order)]

    with pytest.raises(ValidationError):
        to_domain(row, line_rows)
