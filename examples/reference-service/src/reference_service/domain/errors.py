"""Domain errors.

Deliberately no HTTP status codes here. A domain error says what business
rule was broken; deciding that "not found" means 404 is a decision about a
transport protocol, and it lives in api/errors.py.
"""

from __future__ import annotations

from reference_service.domain.order import OrderId


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
