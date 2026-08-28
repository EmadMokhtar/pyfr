"""Mapping between the wire contract and the service layer.

Explicit functions, not automatic derivation. Deriving the schema from the
domain model would remove the very decoupling the separation exists to
create.
"""

from __future__ import annotations

from reference_service.api.v1.schemas import (
    MoneyOut,
    OrderLineOut,
    OrderResponse,
    PlaceOrderRequest,
)
from reference_service.domain.order import Money, Order
from reference_service.services.order import PlaceOrderCommand, PlaceOrderLine


def to_command(request: PlaceOrderRequest) -> PlaceOrderCommand:
    return PlaceOrderCommand(
        customer_id=request.customer_id,
        lines=[
            PlaceOrderLine(
                sku=item.sku,
                quantity=item.quantity,
                unit_amount=item.unit_amount,
                currency=item.currency,
            )
            for item in request.lines
        ],
    )


def _money_out(money: Money) -> MoneyOut:
    return MoneyOut(amount=money.amount, currency=money.currency)


def to_response(order: Order) -> OrderResponse:
    # `internal_note` is deliberately absent: it exists on the entity and
    # must never reach a client.
    return OrderResponse(
        id=order.id,
        customer_id=order.customer_id,
        lines=[
            OrderLineOut(
                sku=line.sku,
                quantity=line.quantity,
                unit_price=_money_out(line.unit_price),
                subtotal=_money_out(line.subtotal),
            )
            for line in order.lines
        ],
        total=_money_out(order.total),
    )
