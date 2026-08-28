"""The 'place an order' use case.

A use case orchestrates: it turns a command into domain objects, asks the
domain to enforce its rules, and hands the result to a repository. It holds
no business rules of its own — those live in the Order aggregate.
"""

from __future__ import annotations

from uuid import uuid4

from reference_service.application.dtos import PlaceOrderCommand
from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
    total_of,
)
from reference_service.domain.repositories import OrderRepository


class PlaceOrder:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def __call__(self, command: PlaceOrderCommand) -> Order:
        lines = [
            OrderLine(
                sku=item.sku,
                quantity=item.quantity,
                unit_price=Money(amount=item.unit_amount, currency=item.currency),
            )
            for item in command.lines
        ]
        order = Order(
            id=OrderId(uuid4()),
            customer_id=CustomerId(command.customer_id),
            lines=lines,
            total=total_of(lines),
        )
        await self._orders.save(order)
        return order
