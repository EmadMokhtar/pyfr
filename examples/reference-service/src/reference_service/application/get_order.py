"""The 'fetch an order' use case."""

from __future__ import annotations

from reference_service.domain.errors import OrderNotFoundError
from reference_service.domain.order import Order, OrderId
from reference_service.domain.repositories import OrderRepository


class GetOrder:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def __call__(self, order_id: OrderId) -> Order:
        order = await self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        return order
