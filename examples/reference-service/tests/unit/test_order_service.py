from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from reference_service.domain.errors import OrderNotFoundError
from reference_service.domain.order import OrderId
from reference_service.services.order import (
    GetOrder,
    PlaceOrder,
    PlaceOrderCommand,
    PlaceOrderLine,
)
from tests.fakes import FakeOrderRepository


def a_command(quantity: int = 2, amount: str = "10.00") -> PlaceOrderCommand:
    return PlaceOrderCommand(
        customer_id=uuid4(),
        lines=[
            PlaceOrderLine(
                sku="sku-1",
                quantity=quantity,
                unit_amount=Decimal(amount),
                currency="EUR",
            )
        ],
    )


async def test_placing_an_order_computes_the_total() -> None:
    orders = FakeOrderRepository()

    order = await PlaceOrder(orders)(a_command(quantity=3, amount="10.00"))

    assert order.total.amount == Decimal("30.00")
    assert order.total.currency == "EUR"


async def test_placing_an_order_persists_it() -> None:
    orders = FakeOrderRepository()

    order = await PlaceOrder(orders)(a_command())

    assert orders.saved == [order]


async def test_each_order_gets_a_distinct_identity() -> None:
    orders = FakeOrderRepository()
    place = PlaceOrder(orders)

    first = await place(a_command())
    second = await place(a_command())

    assert first.id != second.id


async def test_a_command_with_no_lines_is_refused() -> None:
    with pytest.raises(ValueError):
        PlaceOrderCommand(customer_id=uuid4(), lines=[])


def test_a_command_with_mixed_currency_lines_is_refused() -> None:
    """A command must stand on its own for a non-HTTP caller.

    The api layer's PlaceOrderRequest rejects this first over HTTP, so a
    non-HTTP caller (a background job, a later milestone's consumer) is
    the only path that ever reaches this validator directly — it must not
    rely on the api schema having already filtered the input.
    """
    with pytest.raises(ValidationError, match="currency"):
        PlaceOrderCommand(
            customer_id=uuid4(),
            lines=[
                PlaceOrderLine(
                    sku="sku-1",
                    quantity=1,
                    unit_amount=Decimal("10.00"),
                    currency="EUR",
                ),
                PlaceOrderLine(
                    sku="sku-2",
                    quantity=1,
                    unit_amount=Decimal("5.00"),
                    currency="USD",
                ),
            ],
        )


async def test_returns_a_stored_order() -> None:
    orders = FakeOrderRepository()
    placed = await PlaceOrder(orders)(
        PlaceOrderCommand(
            customer_id=uuid4(),
            lines=[
                PlaceOrderLine(
                    sku="sku-1",
                    quantity=1,
                    unit_amount=Decimal("5.00"),
                    currency="EUR",
                )
            ],
        )
    )

    found = await GetOrder(orders)(placed.id)

    assert found == placed


async def test_raises_a_domain_error_when_missing() -> None:
    orders = FakeOrderRepository()
    missing = OrderId(uuid4())

    with pytest.raises(OrderNotFoundError) as exc_info:
        await GetOrder(orders)(missing)

    assert exc_info.value.order_id == missing
