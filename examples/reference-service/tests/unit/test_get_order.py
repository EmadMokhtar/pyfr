from decimal import Decimal
from uuid import uuid4

import pytest

from reference_service.application.dtos import PlaceOrderCommand, PlaceOrderLine
from reference_service.application.get_order import GetOrder
from reference_service.application.place_order import PlaceOrder
from reference_service.domain.errors import OrderNotFoundError
from reference_service.domain.order import OrderId
from tests.fakes import FakeOrderRepository


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
