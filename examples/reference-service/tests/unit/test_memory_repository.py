from decimal import Decimal
from uuid import uuid4

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
    total_of,
)
from reference_service.domain.repositories import OrderRepository
from reference_service.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)


def an_order() -> Order:
    lines = [
        OrderLine(
            sku="sku-1",
            quantity=1,
            unit_price=Money(amount=Decimal("7.00"), currency="EUR"),
        )
    ]
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=lines,
        total=total_of(lines),
    )


def test_it_satisfies_the_port_at_runtime() -> None:
    """Catches a renamed or missing method — nothing more.

    `runtime_checkable` makes isinstance check that attributes with these
    NAMES exist. It does not check parameter types, return types, or
    async-ness. See the next test for the guarantee that does.
    """
    assert isinstance(InMemoryOrderRepository(), OrderRepository)


def test_it_satisfies_the_port_statically() -> None:
    """The real conformance check — enforced by mypy, not at runtime.

    The annotation on this assignment is the point of the test. mypy
    verifies the concrete adapter against the Protocol's full signatures:
    parameter types, return types and async-ness, none of which the
    isinstance check above can see. If `get` took the wrong argument type or
    stopped being async, `just typecheck` would fail here even though every
    runtime assertion still passed.
    """
    repository: OrderRepository = InMemoryOrderRepository()

    assert isinstance(repository, InMemoryOrderRepository)


async def test_saving_then_getting_returns_the_order() -> None:
    repo = InMemoryOrderRepository()
    order = an_order()

    await repo.save(order)

    assert await repo.get(order.id) == order


async def test_getting_an_unknown_id_returns_none() -> None:
    repo = InMemoryOrderRepository()

    assert await repo.get(OrderId(uuid4())) is None


async def test_saving_the_same_id_replaces_it() -> None:
    repo = InMemoryOrderRepository()
    order = an_order()
    await repo.save(order)

    updated = order.model_copy(update={"internal_note": "checked"})
    await repo.save(updated)

    found = await repo.get(order.id)
    assert found is not None
    assert found.internal_note == "checked"


async def test_clear_empties_the_store() -> None:
    repo = InMemoryOrderRepository()
    order = an_order()
    await repo.save(order)

    repo.clear()

    assert await repo.get(order.id) is None
