"""Pure functions between database rows and the Order aggregate.

No session, no I/O, no SQLAlchemy execution — which is why these are tested
in the unit tier with no container.
"""

from __future__ import annotations

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from reference_service.infrastructure.db.models import OrderLineRow, OrderRow


def order_values(order: Order) -> dict[str, object]:
    """The `orders` row for this order, as a plain dict of column values.

    A dict rather than an OrderRow instance because Task 4 feeds it straight
    into an INSERT ... ON CONFLICT statement, which takes values, not mapped
    instances.
    """
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        # Money is one value object; the database stores it as two columns.
        "total_amount": order.total.amount,
        "total_currency": order.total.currency,
        "internal_note": order.internal_note,
    }


def line_values(order: Order) -> list[dict[str, object]]:
    """The `order_lines` rows for this order, numbered in tuple order."""
    return [
        {
            "order_id": order.id,
            "line_number": line_number,
            "sku": line.sku,
            "quantity": line.quantity,
            "unit_amount": line.unit_price.amount,
            "unit_currency": line.unit_price.currency,
        }
        for line_number, line in enumerate(order.lines)
    ]


def to_domain(row: OrderRow, lines: list[OrderLineRow]) -> Order:
    """Rebuild the aggregate. `lines` must already be ordered by line_number.

    Construction runs every Pydantic validator, including
    Order.total_must_match_lines, so an inconsistent set of rows fails here
    rather than producing a nonsense response.
    """
    return Order(
        id=OrderId(row.id),
        customer_id=CustomerId(row.customer_id),
        lines=tuple(
            OrderLine(
                sku=line.sku,
                quantity=line.quantity,
                unit_price=Money(amount=line.unit_amount, currency=line.unit_currency),
            )
            for line in lines
        ),
        total=Money(amount=row.total_amount, currency=row.total_currency),
        internal_note=row.internal_note,
    )
