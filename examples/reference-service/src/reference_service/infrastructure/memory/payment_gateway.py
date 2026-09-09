"""A payment gateway that authorises everything.

The counterpart to InMemoryOrderRepository, and there for the same
reason: with no APP_PAYMENT__BASE_URL set, `just dev` starts a service
that works end to end with no upstream anywhere. It is also what the api
tests use, which keeps them free of HTTP mocking entirely.
"""

from __future__ import annotations

from uuid import uuid4

from reference_service.domain.order import AuthorisationId, Money, OrderId
from reference_service.domain.payments import Authorisation


class InMemoryPaymentGateway:
    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        return Authorisation(id=AuthorisationId(f"auth_{uuid4().hex}"))
