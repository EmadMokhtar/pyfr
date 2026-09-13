"""The render-on-miss use case."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from {{ cookiecutter.package_name }}.domain.errors import OrderNotFoundError
from {{ cookiecutter.package_name }}.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from {{ cookiecutter.package_name }}.domain.receipt_render import render_receipt
from {{ cookiecutter.package_name }}.domain.receipts import ReceiptStore
from {{ cookiecutter.package_name }}.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from {{ cookiecutter.package_name }}.infrastructure.memory.receipt_store import (
    InMemoryReceiptStore,
)
from {{ cookiecutter.package_name }}.services.receipt import GetReceipt

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


async def test_it_satisfies_the_port_at_runtime() -> None:
    """Catches a renamed or missing method — nothing more.

    `runtime_checkable` makes isinstance check that attributes with these
    NAMES exist. It does not check parameter types, return types, or
    async-ness. See test_memory_repository.py for the same caveat against
    OrderRepository, and for the mypy-backed static check that does cover
    signatures — no equivalent static assertion is added here.
    """
    assert isinstance(InMemoryReceiptStore(), ReceiptStore)


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


async def test_a_stored_receipt_for_an_unknown_order_is_not_served() -> None:
    """The only test that would catch a regression to store-first order.

    The module docstring on GetReceipt states that the order is looked up
    BEFORE the store, and explains why: a store-first service would return
    a receipt for an order that no longer resolves. Every other test above
    that exercises an unknown order pairs it with an EMPTY store, so it
    cannot tell the two orderings apart — an empty store returns None
    whether it is consulted first or second, and a store-first
    implementation would pass all four of them.

    Here the store is seeded with bytes for an order id the repository does
    not have. An order-first implementation still raises
    OrderNotFoundError, because it never gets as far as the store. A
    service that checked the store first would find the seeded bytes and
    return them — silently serving a receipt for an order that, as far as
    the rest of the system is concerned, does not exist.
    """
    orders = InMemoryOrderRepository()
    receipts = InMemoryReceiptStore()
    unknown = OrderId(uuid4())
    await receipts.put(unknown, b"a receipt for an order nobody can find")

    with pytest.raises(OrderNotFoundError):
        await GetReceipt(orders, receipts)(unknown)
