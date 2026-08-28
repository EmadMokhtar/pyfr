from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from hypothesis import given
from hypothesis import strategies as st
from pydantic import ValidationError

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
    total_of,
)


def money(amount: str, currency: str = "EUR") -> Money:
    return Money(amount=Decimal(amount), currency=currency)


def line(sku: str = "sku-1", quantity: int = 1, price: str = "10.00") -> OrderLine:
    return OrderLine(sku=sku, quantity=quantity, unit_price=money(price))


def build_order(*lines: OrderLine) -> Order:
    items = list(lines) or [line()]
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=items,
        total=total_of(items),
    )


def test_money_rejects_a_negative_amount() -> None:
    with pytest.raises(ValidationError):
        Money(amount=Decimal("-1.00"), currency="EUR")


def test_money_rejects_a_malformed_currency() -> None:
    with pytest.raises(ValidationError):
        Money(amount=Decimal("1.00"), currency="euro")


def test_money_is_immutable() -> None:
    amount = money("1.00")
    with pytest.raises(ValidationError):
        amount.amount = Decimal("2.00")


def test_money_of_equal_value_is_equal() -> None:
    assert money("1.00") == money("1.00")


def test_adding_different_currencies_is_refused() -> None:
    with pytest.raises(ValueError, match="currency"):
        money("1.00", "EUR") + money("1.00", "USD")


def test_line_subtotal_multiplies_price_by_quantity() -> None:
    assert line(quantity=3, price="2.50").subtotal == money("7.50")


def test_line_rejects_a_non_positive_quantity() -> None:
    with pytest.raises(ValidationError):
        line(quantity=0)


def test_order_requires_at_least_one_line() -> None:
    with pytest.raises(ValidationError):
        Order(
            id=OrderId(uuid4()),
            customer_id=CustomerId(uuid4()),
            lines=[],
            total=money("0.00"),
        )


def test_order_rejects_a_total_that_disagrees_with_its_lines() -> None:
    with pytest.raises(ValidationError, match="total"):
        Order(
            id=OrderId(uuid4()),
            customer_id=CustomerId(uuid4()),
            lines=[line(price="10.00")],
            total=money("99.00"),
        )


def test_invariant_is_rechecked_when_a_field_is_reassigned() -> None:
    """validate_assignment is what stops an entity being corrupted later."""
    order = build_order(line(price="10.00"))

    with pytest.raises(ValidationError):
        order.total = money("99.00")


@given(
    quantities=st.lists(st.integers(min_value=1, max_value=50), min_size=1, max_size=8),
    unit=st.decimals(
        min_value=Decimal("0.01"),
        max_value=Decimal("999.99"),
        places=2,
        allow_nan=False,
        allow_infinity=False,
    ),
)
def test_total_always_equals_the_sum_of_lines(
    quantities: list[int], unit: Decimal
) -> None:
    """No combination of valid lines can produce a disagreeing total."""
    lines = [
        OrderLine(
            sku=f"sku-{i}", quantity=q, unit_price=Money(amount=unit, currency="EUR")
        )
        for i, q in enumerate(quantities)
    ]
    order = Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=lines,
        total=total_of(lines),
    )

    expected = sum(q for q in quantities) * unit
    assert order.total.amount == expected


def test_order_id_is_a_uuid() -> None:
    order = build_order()
    assert isinstance(order.id, UUID)
