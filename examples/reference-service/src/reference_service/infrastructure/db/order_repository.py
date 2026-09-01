"""The PostgreSQL order repository — the only module that knows SQL.

It satisfies domain.repositories.OrderRepository structurally: the Protocol is
never imported here, and no base class is inherited. Swap this for another
adapter and nothing above the infrastructure layer changes.
"""

from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reference_service.domain.order import Order, OrderId
from reference_service.infrastructure.db.mappers import (
    line_values,
    order_values,
    to_domain,
)
from reference_service.infrastructure.db.models import OrderLineRow, OrderRow


class PostgresOrderRepository:
    """One transaction per call — the aggregate is the consistency boundary.

    A team that later needs two aggregates written atomically should introduce
    a unit of work at that point and move the `async with` upward. Nothing in
    this service needs it: `save()` already writes both tables inside a single
    transaction, which is the guarantee an Order actually requires.
    """

    def __init__(self, sessionmaker: async_sessionmaker[AsyncSession]) -> None:
        self._sessionmaker = sessionmaker

    async def get(self, order_id: OrderId) -> Order | None:
        async with self._sessionmaker() as session:
            row = await session.scalar(select(OrderRow).where(OrderRow.id == order_id))
            if row is None:
                return None

            # A second explicit query rather than a relationship(). Lazy
            # loading an unloaded attribute under asyncio raises
            # MissingGreenlet at the point of access, which is a failure at a
            # distance; ORDER BY line_number here is also what restores
            # Order.lines to the tuple order it was saved in. Row order is
            # never guaranteed without an explicit ORDER BY.
            lines = list(
                (
                    await session.scalars(
                        select(OrderLineRow)
                        .where(OrderLineRow.order_id == order_id)
                        .order_by(OrderLineRow.line_number)
                    )
                ).all()
            )
            return to_domain(row, lines)

    async def save(self, order: Order) -> None:
        """Create or replace, in one transaction covering both tables."""
        values = order_values(order)
        async with self._sessionmaker() as session, session.begin():
            statement = postgres_insert(OrderRow).values(**values)
            await session.execute(
                statement.on_conflict_do_update(
                    index_elements=[OrderRow.id],
                    set_={
                        column: value
                        for column, value in values.items()
                        if column != "id"
                    },
                )
            )
            # Replace the whole line set rather than diffing it. The lines have
            # no identity of their own — they are part of the aggregate — so
            # "which line changed" is not a question worth answering, and
            # delete-then-insert is correct for both a new order and a changed
            # one. Both statements are inside the transaction above, so no
            # reader ever sees an order with its lines missing.
            await session.execute(
                delete(OrderLineRow).where(OrderLineRow.order_id == order.id)
            )
            await session.execute(postgres_insert(OrderLineRow), line_values(order))
