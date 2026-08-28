"""The Order aggregate.

This module imports nothing but Pydantic and the standard library. It knows
nothing about HTTP, about SQL, or about the application layer. Pydantic is
used here as a validation library, not as a web framework: it is what makes
the invariants declarative and impossible to bypass.
"""

from __future__ import annotations

from collections.abc import Sequence
from decimal import Decimal
from typing import Annotated, NewType, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    model_validator,
)

OrderId = NewType("OrderId", UUID)
CustomerId = NewType("CustomerId", UUID)

Currency = Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
Sku = Annotated[str, StringConstraints(min_length=1, max_length=64)]


class Money(BaseModel):
    """A value object: no identity, immutable, equal by value."""

    model_config = ConfigDict(frozen=True)

    amount: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
    currency: Currency

    def __add__(self, other: Money) -> Money:
        if other.currency != self.currency:
            raise ValueError(
                f"cannot add {other.currency} to {self.currency}: currency mismatch"
            )
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __mul__(self, factor: int) -> Money:
        return Money(amount=self.amount * factor, currency=self.currency)


class OrderLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: Sku
    quantity: Annotated[int, Field(gt=0)]
    unit_price: Money

    @property
    def subtotal(self) -> Money:
        return self.unit_price * self.quantity


def total_of(lines: Sequence[OrderLine]) -> Money:
    """Sum the lines. Raises ValueError if the currencies disagree."""
    if not lines:
        raise ValueError("cannot total an empty list of lines")
    running = lines[0].subtotal
    for item in lines[1:]:
        running = running + item.subtotal
    return running


class Order(BaseModel):
    """An entity: it has an identity and protects its own invariants.

    `validate_assignment=True` is the part that matters. Without it an Order
    could be made invalid after construction by reassigning a field; with it,
    an invalid Order cannot exist at any point in its life — including via
    `lines`: a mutable `list` would let `order.lines.append(bad_line)`
    bypass `validate_assignment` entirely (append mutates the existing list
    in place; it never reassigns the field, so no validator runs). `tuple`
    closes that gap: it has no `append`, and Pydantic still coerces an
    ordinary list at construction time, so call sites are unaffected.
    """

    model_config = ConfigDict(validate_assignment=True)

    id: OrderId
    customer_id: CustomerId
    lines: Annotated[tuple[OrderLine, ...], Field(min_length=1)]
    total: Money
    # Deliberately never exposed over HTTP. Task 12 asserts that the API
    # response omits it — the demonstration of why api schemas are separate.
    internal_note: str | None = None

    @model_validator(mode="after")
    def total_must_match_lines(self) -> Self:
        computed = total_of(self.lines)
        if computed != self.total:
            raise ValueError(
                f"total {self.total.amount} {self.total.currency} does not "
                f"match the sum of lines {computed.amount} {computed.currency}"
            )
        return self
