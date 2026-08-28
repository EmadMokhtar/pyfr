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
    """
    for error_class in (DomainError, OrderNotFoundError):
        assert not hasattr(error_class, "status")
        assert not hasattr(error_class, "status_code")
        assert not hasattr(error_class, "http_status")


def test_repository_is_a_runtime_checkable_protocol() -> None:
    class Fake:
        async def get(self, order_id: OrderId) -> None:
            return None

        async def save(self, order: object) -> None:
            return None

    assert isinstance(Fake(), OrderRepository)
