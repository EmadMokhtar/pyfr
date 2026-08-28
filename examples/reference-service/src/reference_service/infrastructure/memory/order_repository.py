"""In-memory order repository.

M0 has no database. This adapter exists so the walking skeleton is a real,
runnable service, and so Task 12's API tests exercise the whole flow. M1
adds the PostgreSQL adapter behind the same port; nothing above this layer
changes when it does.
"""

from __future__ import annotations

from reference_service.domain.order import Order, OrderId


class InMemoryOrderRepository:
    def __init__(self) -> None:
        self._orders: dict[OrderId, Order] = {}

    async def get(self, order_id: OrderId) -> Order | None:
        return self._orders.get(order_id)

    async def save(self, order: Order) -> None:
        self._orders[order.id] = order

    def clear(self) -> None:
        self._orders.clear()
