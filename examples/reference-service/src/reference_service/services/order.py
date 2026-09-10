"""Order application services: PlaceOrder and GetOrder.

An application service orchestrates a use case: it turns a command into
domain objects, lets the Order aggregate enforce its own rules, and hands
the result to a repository. It holds no business rules of its own — those
live in the domain layer, in the Order aggregate. (This is not a domain
service — a domain service holds business logic that belongs to no single
entity and lives in the domain layer; these hold no business logic at all.)
This single property, no business rules here, is exactly what the import
contracts and `test_layer_purity.py` verify.

This module also defines PlaceOrder's command objects, PlaceOrderCommand and
PlaceOrderLine — the service layer's own input type. A command is
deliberately not an HTTP schema and not a domain entity: the api layer maps
into it, and PlaceOrder maps out of it into the domain.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator
from pydantic import ValidationError as PydanticValidationError

from reference_service.domain.errors import OrderNotFoundError
from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
    total_of,
)
from reference_service.domain.payments import PaymentGateway
from reference_service.domain.repositories import OrderRepository
from reference_service.services.errors import ServiceDefectError

# NUMERIC(14, 2) in migrations/000001, mirroring api/v1/schemas.py's
# MAX_MONEY. The service layer must not import from api, so the constant
# is repeated rather than shared, exactly as the field constraints below
# already are.
MAX_ORDER_TOTAL = Decimal("999999999999.99")


class PlaceOrderLine(BaseModel):
    model_config = ConfigDict(frozen=True)

    # These mirror the api schema's and the domain's constraints. A command
    # is the service layer's own input type — it must stand on its own for
    # a non-HTTP caller, not rely on api/v1/schemas.py having already
    # filtered bad input.
    sku: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    # le=2_147_483_647 mirrors order_lines.quantity's storage type, INTEGER
    # (PostgreSQL int4, max 2_147_483_647) — same reasoning as
    # domain.order.OrderLine.quantity and api/v1/schemas.py's OrderLineIn.
    #
    # strict=True mirrors the same two: `bool` is an `int` subclass in
    # Python, so without it pydantic's default LAX int validation would
    # accept quantity=True as quantity=1. A command is the service
    # layer's own input type (see the class-level comment above) — it
    # must refuse that on its own, not rely on api/v1/schemas.py having
    # already filtered it out for HTTP callers.
    quantity: Annotated[int, Field(gt=0, le=2_147_483_647, strict=True)]
    unit_amount: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class PlaceOrderCommand(BaseModel):
    model_config = ConfigDict(frozen=True)

    customer_id: UUID
    # `tuple`, not `list`: `frozen=True` is shallow, so a `list` field could
    # still be appended to or cleared after validation — a non-HTTP caller
    # could turn a valid command into an empty or mixed-currency one,
    # bypassing both `min_length` and `lines_must_share_one_currency` below.
    # Matches domain.order.Order.lines, which closes the identical gap the
    # same way. Pydantic still coerces an incoming list at construction
    # time, so call sites are unaffected.
    lines: Annotated[tuple[PlaceOrderLine, ...], Field(min_length=1)]

    @model_validator(mode="after")
    def lines_must_share_one_currency(self) -> Self:
        # Mirrors api/v1/schemas.py's PlaceOrderRequest validator, for the
        # same reason the rest of this module's constraints mirror the api
        # schema's: a command must stand on its own for a non-HTTP caller,
        # not rely on the api layer having already filtered bad input.
        currencies = {line.currency for line in self.lines}
        if len(currencies) > 1:
            raise ValueError(
                f"all lines must share one currency, got {sorted(currencies)}"
            )
        return self

    @model_validator(mode="after")
    def total_must_fit_in_money(self) -> Self:
        # Mirrors api/v1/schemas.py's validator of the same name, for the
        # reason the rest of this module's constraints mirror that
        # module's: a command must stand on its own for a non-HTTP caller.
        total = sum(
            (line.unit_amount * line.quantity for line in self.lines), Decimal(0)
        )
        if total > MAX_ORDER_TOTAL:
            raise ValueError(
                f"order total {total} exceeds the maximum representable "
                f"amount {MAX_ORDER_TOTAL}"
            )
        return self


class PlaceOrder:
    def __init__(self, orders: OrderRepository, payments: PaymentGateway) -> None:
        self._orders = orders
        self._payments = payments

    async def __call__(self, command: PlaceOrderCommand) -> Order:
        # Generated BEFORE the try below, not inside it: the payment
        # gateway's idempotency key (infrastructure/http/payment_gateway.py)
        # is this same id, so it must exist even if line assembly below
        # were ever to fail before reaching the gateway.
        order_id = OrderId(uuid4())

        # The boundary. Everything below this point works from a command that
        # has ALREADY validated, so any validation failure here means this use
        # case assembled the aggregate wrongly — a server defect. Letting the
        # raw pydantic.ValidationError escape would reach the 422 handler in
        # api/errors.py and blame the caller for our bug.
        try:
            lines = tuple(
                OrderLine(
                    sku=item.sku,
                    quantity=item.quantity,
                    unit_price=Money(amount=item.unit_amount, currency=item.currency),
                )
                for item in command.lines
            )
            total = total_of(lines)
        except (PydanticValidationError, ValueError) as exc:
            # ValueError as well as ValidationError: total_of raises a plain
            # ValueError on mixed currencies. PlaceOrderCommand already rejects
            # those, so reaching it here means the command validator and this
            # assembly disagree — again our defect, not the caller's.
            raise ServiceDefectError(
                "failed to build a valid Order from a valid PlaceOrderCommand"
            ) from exc

        # Authorise BEFORE saving. The other order — save, then authorise —
        # persists an order for every declined card and leaves someone to
        # clean them up later.
        #
        # Neither error is caught here. PaymentDeclinedError is a
        # DomainError and api/errors.py turns it into a 402;
        # PaymentUnavailableError has its own handler and becomes a 503.
        # Wrapping either in ServiceDefectError would relabel a working
        # gateway's "no" as a bug in this service.
        authorisation = await self._payments.authorise(order_id=order_id, total=total)

        try:
            order = Order(
                id=order_id,
                customer_id=CustomerId(command.customer_id),
                lines=lines,
                total=total,
                authorisation_id=authorisation.id,
            )
        except (PydanticValidationError, ValueError) as exc:
            # Same defect class as the try above (see its comment): a
            # command that validated but produced an Order whose total
            # disagrees with its lines is this use case's bug, not the
            # caller's — even though it is only reachable here because the
            # payment has, by this point, already been authorised.
            raise ServiceDefectError(
                "failed to build a valid Order from a valid PlaceOrderCommand"
            ) from exc

        # Outside any try: a repository failure is not a validation problem,
        # and wrapping it here would relabel a database outage as a defect in
        # this use case. It propagates to the catch-all handler as itself.
        #
        # The window: if this raises, the payment above is authorised and no
        # order exists. Deliberately not "cleaned up" here with a call that
        # voids the authorisation — that call can fail too, and then there
        # are two windows instead of one.
        #
        # This gap stays open past M3 — it is not scheduled to close. What
        # it looks like when it happens: an authorisation the payment
        # provider holds with no order row to match it. Closing it properly
        # needs an outbox or a reconciliation job, and either is its own
        # design round: message queues are excluded from this project
        # entirely (see the roadmap's excluded-features table). Task 15
        # records this gap in the project documentation — writing it down
        # is not the same as closing it.
        await self._orders.save(order)
        return order


class GetOrder:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def __call__(self, order_id: OrderId) -> Order:
        order = await self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)
        return order
