"""Repository ports.

A Protocol is Python's structural interface: a class satisfies it by having
the right method signatures, with no inheritance and no import of the
Protocol itself. That is what keeps the dependency arrow pointing inward —
infrastructure imports domain, never the reverse.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reference_service.domain.order import Order, OrderId


@runtime_checkable
class OrderRepository(Protocol):
    async def get(self, order_id: OrderId) -> Order | None:
        """Return the order, or None when it does not exist."""
        ...

    async def save(self, order: Order) -> None:
        """Persist the order, creating or replacing it."""
        ...
