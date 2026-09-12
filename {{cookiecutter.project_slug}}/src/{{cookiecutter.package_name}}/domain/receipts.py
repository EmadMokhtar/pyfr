"""The receipt store port: what the domain needs, not how it is done.

Imports nothing but the standard library and the Order aggregate's
identifier type, exactly as the rest of this layer does. `aioboto3` lives on
the far side of this file, in infrastructure/storage/receipt_store.py — the
domain names the operation and never learns that it travels to S3.

The port speaks in `bytes` rather than a Receipt model on purpose. The
document's SHAPE is receipt_render.py's business; a store's business is
holding an opaque blob under a key and giving it back unchanged. Putting a
typed model here would make every future document format a change to this
port, which is precisely the coupling a port exists to prevent.

One error can come out of an implementation:

  - StorageUnavailableError (infrastructure/errors.py) — the store could
    not be reached. A statement about our dependency: not the caller's
    fault, and the same request may well succeed later. It lives in
    infrastructure for the same reason PaymentUnavailableError does — it is
    raised by the adapter, and infrastructure must not import services.

A missing object is NOT an error. It is a `None` return, because "no
receipt has been rendered yet" is the ordinary state of every order that
nobody has asked about, not a failure.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reference_service.domain.order import OrderId


@runtime_checkable
class ReceiptStore(Protocol):
    async def get(self, order_id: OrderId) -> bytes | None:
        """Return the stored receipt, or None when none has been stored.

        Raises `StorageUnavailableError` when the store cannot be reached.
        The distinction matters: None means "render it", and the error
        means "come back later". Collapsing them would make an outage look
        like an empty bucket and silently re-render on every request.
        """
        ...

    async def put(self, order_id: OrderId, content: bytes) -> None:
        """Store the receipt, creating or replacing it."""
        ...
