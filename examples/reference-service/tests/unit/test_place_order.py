from decimal import Decimal
from uuid import uuid4

import pytest

from reference_service.application.dtos import PlaceOrderCommand, PlaceOrderLine
from reference_service.application.place_order import PlaceOrder
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
