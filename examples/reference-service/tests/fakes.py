"""Test doubles shared across the suite."""

from __future__ import annotations

from reference_service.domain.errors import PaymentDeclinedError
from reference_service.domain.order import AuthorisationId, Money, Order, OrderId
from reference_service.domain.payments import Authorisation
from reference_service.infrastructure.errors import PaymentUnavailableError


class FakeOrderRepository:
    """An in-memory stand-in satisfying the OrderRepository port.

    Hand-written rather than reusing the real adapter, so the service
    tests demonstrate that a use case needs no infrastructure whatsoever.
    """

    def __init__(self) -> None:
        self.saved: list[Order] = []

    async def get(self, order_id: OrderId) -> Order | None:
        return next((order for order in self.saved if order.id == order_id), None)

    async def save(self, order: Order) -> None:
        self.saved.append(order)


class FakePaymentGateway:
    """Authorises everything, and remembers what it was asked."""

    def __init__(self) -> None:
        self.calls: list[tuple[OrderId, Money]] = []

    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        self.calls.append((order_id, total))
        return Authorisation(id=AuthorisationId("auth_fake_0001"))


class DecliningPaymentGateway:
    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        raise PaymentDeclinedError(order_id, "insufficient_funds")


class UnavailablePaymentGateway:
    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        raise PaymentUnavailableError("payment provider did not answer")
