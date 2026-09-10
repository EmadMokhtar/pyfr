"""GetReceipt: serve a stored receipt, rendering it the first time.

An application service. It orchestrates — repository, renderer, store — and
holds no business rules of its own; what a receipt CONTAINS is
domain/receipt_render.py's decision.

Why the order is looked up FIRST, before the store:

  1. It gives the right answer for an unknown identifier. A store-first
     service would return a receipt for an order that no longer resolves,
     and would reach object storage for every bogus id a caller cared to
     invent.
  2. It costs almost nothing. When a cache is configured that read is a
     Redis hit, not a database query — the two halves of M4 pay for each
     other here.

Why the store is not written by PlaceOrder: an object-store outage must
never be able to fail a payment. Rendering on demand keeps storage entirely
out of the write path, at the cost of one slower first request per order.
"""

from __future__ import annotations

from reference_service.domain.errors import OrderNotFoundError
from reference_service.domain.order import OrderId
from reference_service.domain.receipt_render import render_receipt
from reference_service.domain.receipts import ReceiptStore
from reference_service.domain.repositories import OrderRepository


class GetReceipt:
    def __init__(self, orders: OrderRepository, receipts: ReceiptStore) -> None:
        self._orders = orders
        self._receipts = receipts

    async def __call__(self, order_id: OrderId) -> bytes:
        order = await self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)

        stored = await self._receipts.get(order_id)
        if stored is not None:
            return stored

        content = render_receipt(order)
        # Not wrapped in a try. A store that cannot be written is a store
        # that cannot be read either, and its own adapter already raises
        # StorageUnavailableError, which api/errors.py maps to 503. Catching
        # it here to return the freshly rendered bytes anyway would hide a
        # broken dependency behind responses that look perfectly healthy,
        # and every request would re-render forever.
        await self._receipts.put(order_id, content)
        return content
