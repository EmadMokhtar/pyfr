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
        lines=(
            PlaceOrderLine(
                sku="sku-1",
                quantity=quantity,
                unit_amount=Decimal(amount),
                currency="EUR",
            ),
        ),
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
        PlaceOrderCommand(customer_id=uuid4(), lines=())


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
            lines=(
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
            ),
        )


def test_place_order_line_rejects_a_quantity_above_int4_max() -> None:
    """Mirrors domain.order.OrderLine's bound — see that test's docstring.

    A command must stand on its own for a non-HTTP caller, so this
    constraint is checked here independently of api/v1/schemas.py having
    already filtered the input.
    """
    with pytest.raises(ValidationError):
        PlaceOrderLine(
            sku="sku-1",
            quantity=2_147_483_648,
            unit_amount=Decimal("1.00"),
            currency="EUR",
        )


async def test_returns_a_stored_order() -> None:
    orders = FakeOrderRepository()
    placed = await PlaceOrder(orders)(
        PlaceOrderCommand(
            customer_id=uuid4(),
            lines=(
                PlaceOrderLine(
                    sku="sku-1",
                    quantity=1,
                    unit_amount=Decimal("5.00"),
                    currency="EUR",
                ),
            ),
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


async def test_a_use_case_defect_is_not_reported_as_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid command that produces an invalid Order is OUR bug, not theirs.

    Simulated by making total_of return the wrong total, which is exactly
    the shape of the real defect: the command validated, and the use case
    then assembled the aggregate incorrectly. The resulting
    pydantic.ValidationError must NOT escape as a ValidationError, because
    api/errors.py turns those into 422s that blame the caller.
    """
    from decimal import Decimal

    from reference_service.domain.order import Money
    from reference_service.services import order as order_module
    from reference_service.services.errors import ServiceDefectError

    monkeypatch.setattr(
        order_module,
        "total_of",
        lambda lines: Money(amount=Decimal("999.99"), currency="EUR"),
    )

    place_order = PlaceOrder(FakeOrderRepository())
    command = PlaceOrderCommand(
        customer_id=uuid4(),
        lines=(
            PlaceOrderLine(
                sku="apple",
                quantity=1,
                unit_amount=Decimal("1.50"),
                currency="EUR",
            ),
        ),
    )

    with pytest.raises(ServiceDefectError):
        await place_order(command)


async def test_a_use_case_defect_does_not_reach_the_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is written when the aggregate could not be built."""
    from decimal import Decimal

    from reference_service.domain.order import Money
    from reference_service.services import order as order_module
    from reference_service.services.errors import ServiceDefectError

    monkeypatch.setattr(
        order_module,
        "total_of",
        lambda lines: Money(amount=Decimal("999.99"), currency="EUR"),
    )

    repository = FakeOrderRepository()
    place_order = PlaceOrder(repository)
    command = PlaceOrderCommand(
        customer_id=uuid4(),
        lines=(
            PlaceOrderLine(
                sku="apple",
                quantity=1,
                unit_amount=Decimal("1.50"),
                currency="EUR",
            ),
        ),
    )

    with pytest.raises(ServiceDefectError):
        await place_order(command)

    assert repository.saved == []
