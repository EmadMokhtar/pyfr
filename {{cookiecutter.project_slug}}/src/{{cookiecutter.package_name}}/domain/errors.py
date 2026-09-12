"""Domain errors.

Deliberately no HTTP status codes here. A domain error says what business
rule was broken; deciding that "not found" means 404 is a decision about a
transport protocol, and it lives in api/errors.py.
"""

from __future__ import annotations

from {{ cookiecutter.package_name }}.domain.order import OrderId


class DomainError(Exception):
    """Base class for every business rule violation."""

    code: str = "domain_error"
    title: str = "Domain rule violated"


class OrderNotFoundError(DomainError):
    code = "order_not_found"
    title = "Order not found"

    def __init__(self, order_id: OrderId) -> None:
        self.order_id = order_id
        super().__init__(f"no order with id {order_id}")


class PaymentDeclinedError(DomainError):
    """The provider answered, and the answer was no.

    A business outcome, not a failure: the call succeeded. It must never
    be retried (that re-submits a payment) and must never trip the circuit
    breaker (the dependency is healthy — it just said no).
    """

    code = "payment_declined"
    title = "Payment declined"

    def __init__(self, order_id: OrderId, reason: str) -> None:
        self.order_id = order_id
        self.reason = reason
        super().__init__(f"payment for order {order_id} was declined: {reason}")
