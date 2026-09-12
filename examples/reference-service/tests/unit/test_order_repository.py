"""PostgresOrderRepository's own logic, with the database faked out.

No container, no real session: _FakeSessionmaker stands in for
async_sessionmaker so these tests exercise what get() itself does with the
rows it is handed — not SQL, not a real connection. The real adapter against
real PostgreSQL is covered by tests/integration/test_order_repository.py.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError as PydanticValidationError

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
    total_of,
)
from reference_service.infrastructure.db.mappers import line_values, order_values
from reference_service.infrastructure.db.models import OrderLineRow, OrderRow
from reference_service.infrastructure.db.order_repository import (
    PostgresOrderRepository,
)
from reference_service.infrastructure.errors import CorruptPersistedDataError


class _FakeScalarResult:
    """Stands in for the object `await session.scalars(...)` resolves to."""

    def __init__(self, rows: list[OrderLineRow]) -> None:
        self._rows = rows

    def all(self) -> list[OrderLineRow]:
        return self._rows


class _FakeSession:
    """Answers exactly the three calls get() makes: connection, scalar, scalars.

    No real SQL is built or run — `row` and `lines` are returned regardless
    of what statement was passed in, which is fine: these tests are about
    what get() does with the rows it receives, not about query-building.
    """

    def __init__(self, row: OrderRow | None, lines: list[OrderLineRow]) -> None:
        self._row = row
        self._lines = lines

    async def __aenter__(self) -> _FakeSession:
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        return None

    async def connection(self, **kwargs: object) -> None:
        return None

    async def scalar(self, *args: object, **kwargs: object) -> OrderRow | None:
        return self._row

    async def scalars(self, *args: object, **kwargs: object) -> _FakeScalarResult:
        return _FakeScalarResult(self._lines)


class _FakeSessionmaker:
    """Callable returning a _FakeSession — stands in for async_sessionmaker.

    PostgresOrderRepository only ever calls `self._sessionmaker()` with no
    arguments, so matching that one call is enough to substitute for
    async_sessionmaker[AsyncSession] without any SQLAlchemy engine at all.
    """

    def __init__(self, row: OrderRow | None, lines: list[OrderLineRow]) -> None:
        self._row = row
        self._lines = lines

    def __call__(self) -> _FakeSession:
        return _FakeSession(self._row, self._lines)


def make_order(internal_note: str | None = None) -> Order:
    lines = (
        OrderLine(
            sku="apple",
            quantity=3,
            unit_price=Money(amount=Decimal("1.50"), currency="EUR"),
        ),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=lines,
        total=total_of(lines),
        internal_note=internal_note,
    )


async def test_get_raises_corrupt_persisted_data_error_not_validation_error() -> None:
    """A row whose stored total disagrees with its lines must not surface as a 422.

    Before this fix, to_domain()'s pydantic.ValidationError propagated out
    of get() unchanged, reached api/errors.py's _pydantic_validation_error,
    and became a 422 blaming the caller for a server-side data problem —
    see tests/api/test_errors.py's
    test_a_corrupted_persisted_order_is_a_500_not_a_422_and_does_not_leak
    for the response-shape half of this same defect.
    """
    order = make_order(internal_note="FRAUD REVIEW: customer flagged, do not ship")
    row = OrderRow(**{**order_values(order), "total_amount": Decimal("999.99")})
    line_rows = [OrderLineRow(**values) for values in line_values(order)]
    repository = PostgresOrderRepository(
        _FakeSessionmaker(row, line_rows)  # type: ignore[arg-type]
    )

    with pytest.raises(CorruptPersistedDataError) as exc_info:
        await repository.get(order.id)

    # And the original pydantic.ValidationError is not lost — an operator
    # reading the log's traceback still sees exactly what disagreed.
    assert isinstance(exc_info.value.__cause__, PydanticValidationError)


async def test_get_returns_none_for_a_missing_row_unaffected_by_the_fix() -> None:
    """The ordinary "not found" path must not be caught up in the fix."""
    repository = PostgresOrderRepository(
        _FakeSessionmaker(None, [])  # type: ignore[arg-type]
    )

    assert await repository.get(OrderId(uuid4())) is None


async def test_get_returns_a_consistent_order_unaffected_by_the_fix() -> None:
    """The ordinary, healthy path must not be caught up in the fix either."""
    order = make_order(internal_note="staff pick")
    row = OrderRow(**order_values(order))
    line_rows = [OrderLineRow(**values) for values in line_values(order)]
    repository = PostgresOrderRepository(
        _FakeSessionmaker(row, line_rows)  # type: ignore[arg-type]
    )

    loaded = await repository.get(order.id)

    assert loaded == order
