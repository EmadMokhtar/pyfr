"""Rendering an Order into a receipt document.

A pure function: same order in, same bytes out, no I/O and no clock. That
is not incidental — it is what lets GetReceipt store the result once and
serve it forever, and what lets a test assert that a re-render matches what
was stored.

Deliberately NO `generated_at` timestamp. It is the obvious field to add
and it would destroy determinism: every re-render after an eviction would
produce different bytes under the same key, so "the receipt for order X"
would depend on when it happened to be regenerated. The order carries the
facts a receipt needs; when the document was serialised is not one of them.
"""

from __future__ import annotations

import json
from typing import Any

from {{ cookiecutter.package_name }}.domain.order import Order

RECEIPT_MEDIA_TYPE = "application/json"

# Bumped whenever the document below gains, loses or renames a field. A
# stored receipt outlives the code that wrote it, so a reader needs to know
# which shape it is holding without guessing from which keys are present.
RECEIPT_SCHEMA_VERSION = 1


def render_receipt(order: Order) -> bytes:
    """Render `order` as a receipt document.

    Built field by field rather than from `order.model_dump()`. That is the
    whole defence for `internal_note`, which the Order aggregate documents
    as never exposed over HTTP: a dump-everything renderer would publish it
    the moment someone set it, and would silently publish every future
    internal field too. An allowlist cannot be forgotten the way a denylist
    can.
    """
    document: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "order_id": str(order.id),
        "customer_id": str(order.customer_id),
        "authorisation_id": order.authorisation_id,
        "currency": order.total.currency,
        # Every amount is a STRING. A receipt is a financial document, and
        # JSON numbers are IEEE 754 doubles in most readers — 10.50 parses
        # back as 10.5 and 0.1 + 0.2 stops being 0.3. The Decimal the order
        # was priced in survives only as text.
        "total": str(order.total.amount),
        "lines": [
            {
                "sku": line.sku,
                "quantity": line.quantity,
                "unit_price": str(line.unit_price.amount),
                "subtotal": str(line.subtotal.amount),
            }
            for line in order.lines
        ],
    }
    # sort_keys for determinism, and a separator pair with no spaces so the
    # bytes do not depend on json's default formatting. The LINES list is
    # untouched by sort_keys — it keeps the order's own sequence, which is
    # what the receipt is describing.
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
