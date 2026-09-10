"""Rendering a receipt.

Two properties carry this module. The document must be DETERMINISTIC, or
the store's "write once, serve the same bytes forever" behaviour is
untestable and a re-render silently produces a different object. And it
must never contain `internal_note`, which the Order aggregate documents as
never leaving the service.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID

from reference_service.domain.order import (
    AuthorisationId,
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from reference_service.domain.receipt_render import (
    RECEIPT_SCHEMA_VERSION,
    render_receipt,
)


def build_order(internal_note: str | None = None) -> Order:
    lines = (
        OrderLine(
            sku="SKU-B",
            quantity=1,
            unit_price=Money(amount=Decimal("5.00"), currency="EUR"),
        ),
        OrderLine(
            sku="SKU-A",
            quantity=2,
            unit_price=Money(amount=Decimal("10.50"), currency="EUR"),
        ),
    )
    return Order(
        id=OrderId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        customer_id=CustomerId(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
        lines=lines,
        total=Money(amount=Decimal("26.00"), currency="EUR"),
        internal_note=internal_note,
        authorisation_id=AuthorisationId("auth-123"),
    )


def test_rendering_the_same_order_twice_produces_identical_bytes() -> None:
    """The property the whole store depends on. If this ever fails, a
    re-render after an eviction writes a DIFFERENT object under the same
    key, and 'the receipt' stops being one thing."""
    order = build_order()
    assert render_receipt(order) == render_receipt(order)


def test_the_internal_note_never_appears_in_a_receipt() -> None:
    """Order.internal_note is documented as never exposed over HTTP, and a
    receipt is served over HTTP. A renderer written as
    `order.model_dump_json()` would publish it, which is why the document
    below is built field by field."""
    order = build_order(internal_note="customer disputed a previous order")

    rendered = render_receipt(order)

    assert b"internal_note" not in rendered
    assert b"disputed" not in rendered


def test_the_receipt_carries_the_fields_a_customer_needs() -> None:
    document = json.loads(render_receipt(build_order()))

    assert document["order_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert document["customer_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    assert document["authorisation_id"] == "auth-123"
    assert document["currency"] == "EUR"
    assert document["total"] == "26.00"
    assert len(document["lines"]) == 2


def test_money_is_rendered_as_a_string_not_a_float() -> None:
    """A receipt is a financial document. Serialising 10.50 as a JSON number
    hands the reader an IEEE 754 double and the rounding that comes with it;
    a string preserves the exact decimal the order was priced in."""
    document = json.loads(render_receipt(build_order()))

    assert document["total"] == "26.00"
    assert isinstance(document["total"], str)
    assert all(isinstance(line["unit_price"], str) for line in document["lines"])


def test_line_order_follows_the_order_not_the_alphabet() -> None:
    """Keys are sorted for determinism; the lines array must NOT be, or the
    receipt stops matching the order it describes."""
    document = json.loads(render_receipt(build_order()))

    assert [line["sku"] for line in document["lines"]] == ["SKU-B", "SKU-A"]


def test_the_document_records_its_schema_version() -> None:
    """A stored receipt outlives the code that wrote it. Without a version
    in the document, a reader years from now has to guess which shape it
    is."""
    document = json.loads(render_receipt(build_order()))

    assert document["schema_version"] == RECEIPT_SCHEMA_VERSION


def test_a_subtotal_is_computed_per_line() -> None:
    document = json.loads(render_receipt(build_order()))
    by_sku = {line["sku"]: line for line in document["lines"]}

    assert by_sku["SKU-A"]["quantity"] == 2
    assert by_sku["SKU-A"]["unit_price"] == "10.50"
    assert by_sku["SKU-A"]["subtotal"] == "21.00"
