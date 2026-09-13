"""In-memory receipt store.

The adapter selected when no object storage is configured, so the receipt
endpoint works on a laptop with nothing running but the application — the
same job InMemoryOrderRepository does for the database. Receipts vanish on
restart, which is harmless: a receipt is derived from its order and is
re-rendered on the next request.
"""

from __future__ import annotations

from {{ cookiecutter.package_name }}.domain.order import OrderId


class InMemoryReceiptStore:
    def __init__(self) -> None:
        self._receipts: dict[OrderId, bytes] = {}

    async def get(self, order_id: OrderId) -> bytes | None:
        return self._receipts.get(order_id)

    async def put(self, order_id: OrderId, content: bytes) -> None:
        self._receipts[order_id] = content

    def clear(self) -> None:
        self._receipts.clear()
