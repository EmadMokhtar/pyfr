"""The Order aggregate.

This module imports nothing but Pydantic and the standard library. It knows
nothing about HTTP, about SQL, or about the service layer. Pydantic is
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
AuthorisationId = NewType("AuthorisationId", str)

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
    # le=2_147_483_647 mirrors order_lines.quantity's storage type, INTEGER
    # (PostgreSQL int4, max 2_147_483_647), in
    # migrations/000001_create_orders_tables.up.sql — the same reason
    # Money.amount below is bounded to mirror NUMERIC(14, 2). Without this
    # bound, a quantity the column cannot hold would pass construction
    # here and fail only once the adapter sent it to PostgreSQL, as
    # `DataError: value out of int32 range` — a storage failure raised
    # from infrastructure, mid-write, for a value this model had already
    # declared valid. Rejecting it here keeps the failure where the rule
    # is: an OrderLine that cannot be stored is not a valid OrderLine.
    # What that means for a caller over HTTP is api/errors.py's decision,
    # not this module's.
    #
    # strict=True closes a second, independent gap: `bool` is an `int`
    # subclass in Python, so pydantic's default LAX int validation accepts
    # `True`/`False` as `1`/`0`. This is the domain layer, so there is no
    # published JSON Schema to compare against here — but a non-HTTP
    # caller can construct this model directly, and the coercion would
    # silently turn a caller's mistake into a valid order line. Mirrored
    # in services/order.py's PlaceOrderLine and api/v1/schemas.py's
    # OrderLineIn (which documents the same gap, found live by
    # Schemathesis, in full); keep all three in step.
    quantity: Annotated[int, Field(gt=0, le=2_147_483_647, strict=True)]
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

    `frozen=True` is the part that matters, not `validate_assignment=True`.
    Pydantic's `validate_assignment` assigns the new value to the field
    FIRST and only then runs the `after` model validator; when the
    validator raises, the assignment has already happened, so the object is
    left corrupt with the invalid value in place — the validator's
    exception tells the caller "rejected" while `self.__dict__` says
    otherwise. `frozen=True` sidesteps that ordering problem entirely: it
    refuses the assignment itself, before any mutation, so there is no
    window in which a bad value has landed. An invalid Order still cannot
    be constructed — that guarantee comes from the constructor already
    running every validator — and now an existing Order cannot be
    corrupted after construction either. This also covers `lines`: a
    mutable `list` would let `order.lines.append(bad_line)` corrupt the
    entity without ever going through assignment at all (append mutates
    the existing list in place). `tuple` closes that gap independently of
    `frozen`: it has no `append`, and Pydantic still coerces an ordinary
    list at construction time, so call sites are unaffected.
    """

    model_config = ConfigDict(frozen=True)

    id: OrderId
    customer_id: CustomerId
    lines: Annotated[tuple[OrderLine, ...], Field(min_length=1)]
    total: Money
    # Deliberately never exposed over HTTP. Task 12 asserts that the API
    # response omits it — the demonstration of why api schemas are separate.
    internal_note: str | None = None
    # Set once the payment provider has authorised the total, and never
    # after. `None` is not "unpaid": every order placed today is
    # authorised before it is saved, even under the in-memory gateway,
    # whose authorisation id is never absent. The only orders carrying
    # `None` are ones saved before this column existed — it was added
    # nullable, with no backfill, so an old row says `None` because what
    # its authorisation was, if any, is genuinely unknown, not because
    # none took place.
    authorisation_id: AuthorisationId | None = None

    @model_validator(mode="after")
    def total_must_match_lines(self) -> Self:
        computed = total_of(self.lines)
        if computed != self.total:
            raise ValueError(
                f"total {self.total.amount} {self.total.currency} does not "
                f"match the sum of lines {computed.amount} {computed.currency}"
            )
        return self
