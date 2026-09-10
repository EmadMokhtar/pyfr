"""The render-on-miss use case."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from reference_service.domain.errors import OrderNotFoundError
from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from reference_service.domain.receipt_render import render_receipt
from reference_service.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from reference_service.infrastructure.memory.receipt_store import (
    InMemoryReceiptStore,
)
from reference_service.services.receipt import GetReceipt

pytestmark = pytest.mark.asyncio


def build_order() -> Order:
    line = OrderLine(
        sku="SKU-1",
        quantity=2,
        unit_price=Money(amount=Decimal("10.50"), currency="EUR"),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=(line,),
        total=Money(amount=Decimal("21.00"), currency="EUR"),
    )


async def test_a_first_request_renders_and_stores() -> None:
    orders = InMemoryOrderRepository()
    receipts = InMemoryReceiptStore()
    order = build_order()
    await orders.save(order)

    content = await GetReceipt(orders, receipts)(order.id)

    assert content == render_receipt(order)
    assert await receipts.get(order.id) == content


async def test_a_second_request_serves_the_stored_bytes() -> None:
    """Not merely 'equal bytes' — the STORED object. A service that
    re-rendered every time would pass an equality check against the
    renderer and never touch storage at all."""
    orders = InMemoryOrderRepository()
    receipts = InMemoryReceiptStore()
    order = build_order()
    await orders.save(order)
    await GetReceipt(orders, receipts)(order.id)

    # Replace what is stored. A re-render would overwrite this; serving the
    # stored object returns it.
    await receipts.put(order.id, b"stored-earlier")

    assert await GetReceipt(orders, receipts)(order.id) == b"stored-earlier"


async def test_an_unknown_order_raises_rather_than_rendering_nothing() -> None:
    orders = InMemoryOrderRepository()
    receipts = InMemoryReceiptStore()

    with pytest.raises(OrderNotFoundError):
        await GetReceipt(orders, receipts)(OrderId(uuid4()))


async def test_an_unknown_order_writes_nothing_to_the_store() -> None:
    orders = InMemoryOrderRepository()
    receipts = InMemoryReceiptStore()
    missing = OrderId(uuid4())

    with pytest.raises(OrderNotFoundError):
        await GetReceipt(orders, receipts)(missing)

    assert await receipts.get(missing) is None
