"""Command objects.

A command is the application layer's own input type. It is deliberately not
an HTTP schema and not a domain entity: the api layer maps into it, and the
use case maps out of it into the domain.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlaceOrderLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    sku: str
    quantity: Annotated[int, Field(gt=0)]
    unit_amount: Decimal
    currency: str


class PlaceOrderCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    customer_id: UUID
    lines: Annotated[list[PlaceOrderLine], Field(min_length=1)]
