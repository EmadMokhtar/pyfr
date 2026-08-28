"""Order application services: PlaceOrder and GetOrder.

An application service orchestrates a use case: it turns a command into
domain objects, lets the Order aggregate enforce its own rules, and hands
the result to a repository. It holds no business rules of its own — those
live in the domain layer, in the Order aggregate. (This is not a domain
service — a domain service holds business logic that belongs to no single
entity and lives in the domain layer; these hold no business logic at all.)
This single property, no business rules here, is exactly what the import
contracts and `test_layer_purity.py` verify.

This module also defines PlaceOrder's command objects, PlaceOrderCommand and
PlaceOrderLine — the service layer's own input type. A command is
deliberately not an HTTP schema and not a domain entity: the api layer maps
into it, and PlaceOrder maps out of it into the domain.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from reference_service.domain.errors import OrderNotFoundError
from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
    total_of,
)
from reference_service.domain.repositories import OrderRepository


class PlaceOrderLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    # These mirror the api schema's and the domain's constraints. A command
    # is the service layer's own input type — it must stand on its own for
    # a non-HTTP caller, not rely on api/v1/schemas.py having already
    # filtered bad input.
    sku: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    quantity: Annotated[int, Field(gt=0)]
    unit_amount: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class PlaceOrderCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    customer_id: UUID
    # `tuple`, not `list`: `frozen=True` is shallow, so a `list` field could
    # still be appended to or cleared after validation — a non-HTTP caller
    # could turn a valid command into an empty or mixed-currency one,
    # bypassing both `min_length` and `lines_must_share_one_currency` below.
    # Matches domain.order.Order.lines, which closes the identical gap the
    # same way. Pydantic still coerces an incoming list at construction
    # time, so call sites are unaffected.
    lines: Annotated[tuple[PlaceOrderLine, ...], Field(min_length=1)]

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


class PlaceOrder:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def __call__(self, command: PlaceOrderCommand) -> Order:
        lines = tuple(
            OrderLine(
                sku=item.sku,
                quantity=item.quantity,
                unit_price=Money(amount=item.unit_amount, currency=item.currency),
            )
            for item in command.lines
        )
        order = Order(
            id=OrderId(uuid4()),
            customer_id=CustomerId(command.customer_id),
            lines=lines,
            total=total_of(lines),
        )
        await self._orders.save(order)
        return order


class GetOrder:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def __call__(self, order_id: OrderId) -> Order:
        order = await self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        return order
