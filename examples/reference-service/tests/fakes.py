"""Test doubles shared across the suite."""

from __future__ import annotations

from reference_service.domain.order import Order, OrderId


class FakeOrderRepository:
    """An in-memory stand-in satisfying the OrderRepository port.

    Hand-written rather than reusing the real adapter, so the service
    tests demonstrate that a use case needs no infrastructure whatsoever.
    """

    def __init__(self) -> None:
        self.saved: list[Order] = []

    async def get(self, order_id: OrderId) -> Order | None:
        return next((order for order in self.saved if order.id == order_id), None)

    async def save(self, order: Order) -> None:
        self.saved.append(order)
