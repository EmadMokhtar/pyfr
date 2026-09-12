"""The PostgreSQL order repository — the only module that knows SQL.

It satisfies domain.repositories.OrderRepository structurally: the Protocol is
never imported here, and no base class is inherited. Swap this for another
adapter and nothing above the infrastructure layer changes.
"""

from __future__ import annotations

from pydantic import ValidationError as PydanticValidationError
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reference_service.domain.order import Order, OrderId
from reference_service.infrastructure.db.mappers import (
    line_values,
    order_values,
    to_domain,
)
from reference_service.infrastructure.db.models import OrderLineRow, OrderRow
from reference_service.infrastructure.errors import (
    CorruptPersistedDataError,
    StorageConstraintViolatedError,
)

# The two SELECTs in get() below must see ONE version of the aggregate.
# PostgreSQL's default READ COMMITTED gives each STATEMENT its own snapshot,
# so a save() committing between them would return this order's header from
# one version and its lines from another — and Order.total_must_match_lines
# would then reject the mismatch, turning a healthy read into a 500.
# REPEATABLE READ takes one snapshot for the whole transaction. This is
# read-only, so it cannot raise the serialization failures a writing
# transaction could. Kept as a named constant, not inlined, because Task 7
# imports it to assert the level actually took effect against a real
# database.
READ_ISOLATION_LEVEL = "REPEATABLE READ"

# The only fields of PostgreSQL's error we are willing to repeat. Each is an
# identifier — a state code, a relation name, a constraint name — so none can
# contain a value from the rejected row.
#
# This is an allowlist rather than a denylist on purpose. The obvious
# alternative, stripping the one field known to carry data (`detail`), assumes
# we can enumerate every field PostgreSQL might put a value in, for every error
# class, in every future version. Naming the three we want inverts that: a
# field we have not considered is excluded by default rather than included by
# default. `message` is left out under the same rule — its wording is
# server-composed prose, and while every integrity error we have seen keeps
# values out of it and in DETAIL, "we have not seen a counterexample" is a
# weaker guarantee than "this is an identifier".
_SAFE_ERROR_FIELDS = ("sqlstate", "table_name", "constraint_name")


def _constraint_summary(exc: IntegrityError) -> str:
    """Describe an integrity failure using no data from the rejected row.

    The structured fields live on asyncpg's own exception, two links down the
    chain: SQLAlchemy's IntegrityError wraps the dialect's, which wraps
    asyncpg's. Reached defensively — a different driver, or a failure raised
    before asyncpg got involved, leaves us with nothing to report, and saying
    so plainly beats an AttributeError inside an error path.
    """
    driver_error = getattr(exc.orig, "__cause__", None)
    described = [
        f"{field}={value}"
        for field in _SAFE_ERROR_FIELDS
        if (value := getattr(driver_error, field, None))
    ]
    return ", ".join(described) or "no constraint metadata available"


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
            # Pin the transaction to REPEATABLE READ before the first
            # statement runs — see READ_ISOLATION_LEVEL's comment above for
            # why the two SELECTs below need one shared snapshot.
            await session.connection(
                execution_options={"isolation_level": READ_ISOLATION_LEVEL}
            )
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
            try:
                return to_domain(row, lines)
            except PydanticValidationError as exc:
                # to_domain() reruns every domain validator on the way OUT
                # of storage, so a row that disagrees with itself (see
                # mappers.py's to_domain docstring) fails HERE, as a raw
                # pydantic.ValidationError — the caller asked for an order
                # that exists but is corrupt, which is our fault, not
                # theirs. Left uncaught, that ValidationError would reach
                # api/errors.py's _pydantic_validation_error handler, which
                # exists for genuine client faults: it would answer 422 for
                # a server-side data problem AND, via exc.errors(), quote
                # the row's own field values — including internal_note —
                # into the response body. Re-raising as
                # CorruptPersistedDataError, which has no registered
                # handler, sends it to the catch-all instead: a 500 that
                # describes none of our internals, the way a storage fault
                # should be reported. See infrastructure/errors.py.
                # The message deliberately does not interpolate `exc` (or
                # any row value): `from exc` already chains the original
                # ValidationError — with its full, unfiltered field values —
                # into this exception's traceback for the catch-all's
                # _logger.exception to log; nothing about the response
                # depends on what this message says, so it says the least
                # it can.
                raise CorruptPersistedDataError(
                    f"order {order_id} failed domain validation on load"
                ) from exc

    async def save(self, order: Order) -> None:
        """Create or replace, in one transaction covering both tables."""
        values = order_values(order)
        try:
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
                # get()'s freedom from torn reads is not this method's atomicity
                # alone. This transaction either commits both statements above or
                # neither, but a reader using the default isolation level could
                # still take its two SELECTs from either side of that commit.
                # READ_ISOLATION_LEVEL on the read side is the other half of the
                # guarantee — see its comment near the top of this module.
        except IntegrityError as exc:
            # `from None`, NOT `from exc` — and that is the whole point of this
            # clause, not a slip. Chaining would attach the original exception
            # as __cause__, and the catch-all handler's traceback renders the
            # cause in full, so PostgreSQL's DETAIL line — the failing row,
            # internal_note included — would still reach the log despite the
            # scrubbed message above it. Verified both ways against PostgreSQL
            # 16.13: with `from exc` the row appears in the rendered traceback;
            # with `from None` it does not. The cost is the driver's own
            # frames, which is a fair trade for a message that already names
            # the state code, the relation and the constraint.
            raise StorageConstraintViolatedError(
                f"the database rejected this write ({_constraint_summary(exc)})"
            ) from None
