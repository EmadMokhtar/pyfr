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
        # Deliberately realistic: names a provider and a URL, the same
        # shape a real gateway's failure message would take (see
        # infrastructure/http/payment_gateway.py). The old message,
        # "payment provider did not answer", contained no "http" either
        # way, so a test asserting "http" is absent from the response
        # could not tell the fixed public `detail` apart from a
        # regression that echoes `str(exc)` straight to the client. This
        # message can — see tests/api/test_orders.py's 503 test.
        raise PaymentUnavailableError(
            "acme-pay at https://pay.acme.example did not answer"
        )


class FakeRedis:
    """The three commands CachedOrderRepository uses, plus a fault switch.

    `fail_with` makes every command raise, which is how the fail-open tests
    simulate a Redis outage without a container. `calls` records command
    names so a test can assert the cache was CONSULTED, not merely that the
    right value came back — a decorator that silently stopped calling Redis
    would still pass a value-only assertion.
    """

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.calls: list[str] = []
        self.fail_with: Exception | None = None
        self.last_ttl_seconds: int | None = None

    def _maybe_fail(self, command: str) -> None:
        self.calls.append(command)
        if self.fail_with is not None:
            raise self.fail_with

    async def get(self, key: str) -> bytes | None:
        self._maybe_fail("get")
        return self.store.get(key)

    async def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self._maybe_fail("set")
        self.store[key] = value
        self.last_ttl_seconds = ex

    async def delete(self, key: str) -> None:
        self._maybe_fail("delete")
        self.store.pop(key, None)
