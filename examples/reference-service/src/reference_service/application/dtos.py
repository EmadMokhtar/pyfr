"""Command objects.

A command is the application layer's own input type. It is deliberately not
an HTTP schema and not a domain entity: the api layer maps into it, and the
use case maps out of it into the domain.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator


class PlaceOrderLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    # These mirror the api schema's and the domain's constraints. A command
    # is the application layer's own input type — it must stand on its own
    # for a non-HTTP caller, not rely on api/v1/schemas.py having already
    # filtered bad input.
    sku: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    quantity: Annotated[int, Field(gt=0)]
    unit_amount: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class PlaceOrderCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    customer_id: UUID
    lines: Annotated[list[PlaceOrderLine], Field(min_length=1)]

    @model_validator(mode="after")
    def lines_must_share_one_currency(self) -> Self:
        # Mirrors api/v1/schemas.py's PlaceOrderRequest validator, for the
        # same reason the rest of this module's constraints mirror the api
        # schema's: a command must stand on its own for a non-HTTP caller,
        # not rely on the api layer having already filtered bad input.
        currencies = {line.currency for line in self.lines}
        if len(currencies) > 1:
            raise ValueError(
                f"all lines must share one currency, got {sorted(currencies)}"
            )
        return self
