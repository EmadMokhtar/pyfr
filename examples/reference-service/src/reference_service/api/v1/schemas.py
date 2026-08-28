"""HTTP request and response schemas.

These are deliberately separate from the domain models. The wire contract can
then change independently of the business model: a domain field can be
renamed without breaking clients, and an internal field cannot leak simply
because someone added it to the entity.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, Field, StringConstraints, model_validator


class MoneyOut(BaseModel):
    amount: Decimal
    currency: str


class OrderLineIn(BaseModel):
    sku: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    quantity: Annotated[int, Field(gt=0)]
    # Mirrors domain.order.Money.amount: without these bounds, a value the
    # domain rejects (e.g. "10.123", three decimal places) passes this
    # schema and blows up as an unhandled ValidationError deep inside the
    # use case instead of a 422 at the edge.
    unit_amount: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class OrderLineOut(BaseModel):
    sku: str
    quantity: int
    unit_price: MoneyOut
    subtotal: MoneyOut


class PlaceOrderRequest(BaseModel):
    customer_id: UUID
    lines: Annotated[list[OrderLineIn], Field(min_length=1)]

    @model_validator(mode="after")
    def lines_must_share_one_currency(self) -> Self:
        # A relationship BETWEEN lines, not a property of one, so no
        # per-field constraint can express it. Without this, two
        # individually valid lines in different currencies reach
        # `domain.order.total_of`, whose `Money.__add__` raises a plain
        # `ValueError` — neither a `DomainError` nor a pydantic
        # `ValidationError` — and fall through to the catch-all 500
        # handler for ordinary, schema-valid client input.
        currencies = {line.currency for line in self.lines}
        if len(currencies) > 1:
            raise ValueError(
                f"all lines must share one currency, got {sorted(currencies)}"
            )
        return self


class OrderResponse(BaseModel):
    id: UUID
    customer_id: UUID
    lines: list[OrderLineOut]
    total: MoneyOut
