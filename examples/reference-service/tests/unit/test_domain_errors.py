from uuid import uuid4

from reference_service.domain.errors import DomainError, OrderNotFoundError
from reference_service.domain.order import OrderId
from reference_service.domain.repositories import OrderRepository


def test_order_not_found_carries_the_id_and_a_stable_code() -> None:
    order_id = OrderId(uuid4())

    error = OrderNotFoundError(order_id)

    assert isinstance(error, DomainError)
    assert error.order_id == order_id
    assert error.code == "order_not_found"
    assert error.title == "Order not found"
    assert str(order_id) in str(error)


def test_domain_errors_carry_no_http_status() -> None:
    """Mapping an error to a status code belongs in api/errors.py only.

    Checked on the runtime surface rather than the source text, so a
    docstring explaining the rule cannot fail the test that enforces it.

    Checked on INSTANCES rather than classes, because `hasattr` on a class
    cannot see an attribute assigned to `self` inside `__init__` — which is
    exactly how `OrderNotFoundError` sets `order_id`. A class-level check
    would miss the most natural way to break this rule. Checking instances
    subsumes the class-level check, since attribute lookup falls back to
    the class.
    """
    for error in (DomainError("boom"), OrderNotFoundError(OrderId(uuid4()))):
        assert not hasattr(error, "status")
        assert not hasattr(error, "status_code")
        assert not hasattr(error, "http_status")


def test_repository_is_a_runtime_checkable_protocol() -> None:
    """Guard the decorator and the method names — nothing more.

    `runtime_checkable` makes `isinstance` check only that attributes with
    these NAMES exist. It does not check parameter types, return types, or
    even that the methods are async: `Fake.save` below takes `object` while
    the Protocol declares `Order`, and this still passes. That is deliberate
    here — the real signature conformance check is static, performed by mypy
    when the in-memory adapter is assigned to an `OrderRepository`-typed
    field on the container. What this test does catch is a missing
    `@runtime_checkable` decorator (isinstance would raise TypeError) and a
    renamed or misspelled method.
    """

    class Fake:
        async def get(self, order_id: OrderId) -> None:
            return None

        async def save(self, order: object) -> None:
            return None

    assert isinstance(Fake(), OrderRepository)
