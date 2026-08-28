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
    items = lines or (line(),)
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
        # `unused-ignore` is required because this project does not enable the
        # pydantic.mypy plugin, so mypy does not know the model is frozen and
        # reports `misc` as unused. Keeping `misc` means the line still works
        # if the plugin is ever enabled. Same pattern as test_settings.py.
        amount.amount = Decimal("2.00")  # type: ignore[misc, unused-ignore]


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
            lines=(),
            total=money("0.00"),
        )


def test_order_rejects_a_total_that_disagrees_with_its_lines() -> None:
    with pytest.raises(ValidationError, match="total"):
        Order(
            id=OrderId(uuid4()),
            customer_id=CustomerId(uuid4()),
            lines=(line(price="10.00"),),
            total=money("99.00"),
        )


def test_invariant_is_rechecked_when_a_field_is_reassigned() -> None:
    """`frozen=True` is what stops an entity being corrupted later.

    Asserting only that the assignment raises is not enough: Pydantic's
    `validate_assignment` (the mechanism this used to rely on) assigns the
    new value FIRST and runs the `after` validator second, so a raised
    ValidationError does not mean the object was left alone — confirmed by
    probing the unpatched code, where `order.total` read back as 99.00
    after this exact assignment raised. `frozen=True` refuses the
    assignment before any mutation happens, so the second assertion below
    is the one that actually catches the corruption.
    """
    order = build_order(line(price="10.00"))

    with pytest.raises(ValidationError):
        order.total = money("99.00")
    assert order.total == money("10.00")


def test_lines_cannot_be_mutated_in_place() -> None:
    """`lines` is a `tuple`, not a `list`, precisely so this cannot happen.

    A mutable list would let `order.lines.append(bad_line)` corrupt the
    entity without ever going through assignment at all — bypassing
    `frozen` entirely, since `frozen` only refuses assignment, not mutation
    of an already-assigned value's contents.
    """
    order = build_order(line(price="10.00"))

    with pytest.raises(AttributeError):
        order.lines.append(line(price="5.00"))  # type: ignore[attr-defined]


@given(
    # One price PER LINE, not one price shared by every line. Drawing a single
    # price and reusing it makes the assertion little more than a restatement
    # of decimal distributivity; varying the price per line is what actually
    # exercises aggregation across different Money values.
    drawn_lines=st.lists(
        st.tuples(
            st.integers(min_value=1, max_value=50),
            st.decimals(
                min_value=Decimal("0.01"),
                max_value=Decimal("999.99"),
                places=2,
                allow_nan=False,
                allow_infinity=False,
            ),
        ),
        min_size=1,
        max_size=8,
    )
)
def test_total_always_equals_the_sum_of_lines(
    drawn_lines: list[tuple[int, Decimal]],
) -> None:
    """No combination of valid lines can produce a disagreeing total."""
    lines = tuple(
        OrderLine(
            sku=f"sku-{index}",
            quantity=quantity,
            unit_price=Money(amount=unit, currency="EUR"),
        )
        for index, (quantity, unit) in enumerate(drawn_lines)
    )
    order = Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=lines,
        total=total_of(lines),
    )

    expected = sum((quantity * unit for quantity, unit in drawn_lines), Decimal("0"))
    assert order.total.amount == expected


def test_order_id_is_a_uuid() -> None:
    order = build_order()
    assert isinstance(order.id, UUID)
