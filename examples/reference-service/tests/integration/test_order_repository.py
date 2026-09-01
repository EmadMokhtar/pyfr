"""The PostgreSQL adapter against a real database and the real schema."""

from __future__ import annotations

import traceback
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import Connection, event, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
    total_of,
)
from reference_service.infrastructure.db.order_repository import (
    READ_ISOLATION_LEVEL,
    PostgresOrderRepository,
)
from reference_service.infrastructure.errors import (
    StorageConstraintViolatedError,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def make_order(internal_note: str | None = None) -> Order:
    lines = (
        OrderLine(
            sku="apple",
            quantity=3,
            unit_price=Money(amount=Decimal("1.50"), currency="EUR"),
        ),
        OrderLine(
            sku="bread",
            quantity=1,
            unit_price=Money(amount=Decimal("2.25"), currency="EUR"),
        ),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=lines,
        total=total_of(lines),
        internal_note=internal_note,
    )


async def test_an_order_survives_a_round_trip_unchanged(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    repository = PostgresOrderRepository(sessionmaker)
    order = make_order(internal_note="staff pick")

    await repository.save(order)
    loaded = await repository.get(order.id)

    # Equality on the whole aggregate, not field by field: Order is a frozen
    # Pydantic model, so this compares the id, the customer, every line, the
    # total and the note in one assertion.
    assert loaded == order


async def test_decimals_come_back_exact(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """NUMERIC(14, 2), not a float. 1.50 must not return as 1.4999999."""
    repository = PostgresOrderRepository(sessionmaker)
    order = make_order()

    await repository.save(order)
    loaded = await repository.get(order.id)

    assert loaded is not None
    assert loaded.total.amount == Decimal("6.75")
    assert loaded.lines[0].unit_price.amount == Decimal("1.50")


async def test_line_order_is_preserved(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Without ORDER BY line_number this fails, deterministically.

    Going through save() alone cannot exercise this: mappers.line_values()
    assigns each row's line_number via enumerate() of the very tuple being
    inserted, so insertion order and line_number order are IDENTICAL by
    construction for anything reachable through save()/get() alone —
    confirmed the hard way. An earlier version of this test did exactly
    that (save(), then get()), and passed 10 times out of 10 with
    `.order_by(OrderLineRow.line_number)` removed from get(): PostgreSQL
    chose a Bitmap Heap Scan for the order_lines lookup, which returns rows
    in physical heap order, and a freshly inserted, never-updated set of
    rows has physical order equal to insertion order — so the old test
    could not fail for the reason it existed.

    This version reaches around save() and inserts the two rows directly,
    in the REVERSE of their line_number order: line_number=1 ("bread")
    physically first, line_number=0 ("apple") physically second. Physical/
    insertion order and logical (line_number) order now deliberately
    disagree. With ORDER BY line_number, get() returns ["apple", "bread"]
    regardless of insertion order. Without it, a scan returning physical
    order returns ["bread", "apple"] instead, and the assertion below
    fails — verified both ways; see the Task 7 report for both
    transcripts.
    """
    from sqlalchemy import delete, insert

    from reference_service.infrastructure.db.models import OrderLineRow

    repository = PostgresOrderRepository(sessionmaker)
    order = make_order()
    # save() first, only to create the `orders` row order_lines' foreign
    # key needs. Its own insert of the lines is undone immediately below.
    await repository.save(order)

    async with sessionmaker() as session, session.begin():
        await session.execute(
            delete(OrderLineRow).where(OrderLineRow.order_id == order.id)
        )
        await session.execute(
            insert(OrderLineRow),
            [
                {
                    "order_id": order.id,
                    "line_number": 1,
                    "sku": "bread",
                    "quantity": 1,
                    "unit_amount": Decimal("2.25"),
                    "unit_currency": "EUR",
                },
                {
                    "order_id": order.id,
                    "line_number": 0,
                    "sku": "apple",
                    "quantity": 3,
                    "unit_amount": Decimal("1.50"),
                    "unit_currency": "EUR",
                },
            ],
        )

    loaded = await repository.get(order.id)

    assert loaded is not None
    assert [line.sku for line in loaded.lines] == ["apple", "bread"]


async def test_an_unknown_id_returns_none(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """The port says None, not an exception. GetOrder turns it into the
    domain's OrderNotFoundError, and api/errors.py turns that into a 404."""
    repository = PostgresOrderRepository(sessionmaker)

    assert await repository.get(OrderId(uuid4())) is None


async def test_saving_the_same_id_twice_replaces_the_order(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """The port's contract is "creating or replacing"."""
    repository = PostgresOrderRepository(sessionmaker)
    order = make_order()
    await repository.save(order)

    replacement_lines = (
        OrderLine(
            sku="cheese",
            quantity=2,
            unit_price=Money(amount=Decimal("4.00"), currency="EUR"),
        ),
    )
    replacement = Order(
        id=order.id,
        customer_id=order.customer_id,
        lines=replacement_lines,
        total=total_of(replacement_lines),
    )

    await repository.save(replacement)
    loaded = await repository.get(order.id)

    assert loaded is not None
    assert [line.sku for line in loaded.lines] == ["cheese"]
    assert loaded.total.amount == Decimal("8.00")
    # The replaced lines are gone, not merely superseded.
    assert len(loaded.lines) == 1


async def test_internal_note_persists_even_though_it_is_never_served(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """internal_note is deliberately absent from every HTTP response.

    tests/api/test_orders.py asserts it never leaks. This asserts the other
    half: it is genuinely stored, so the api schema is what withholds it
    rather than the database quietly dropping it.
    """
    repository = PostgresOrderRepository(sessionmaker)
    order = make_order(internal_note="fraud review")

    await repository.save(order)
    loaded = await repository.get(order.id)

    assert loaded is not None
    assert loaded.internal_note == "fraud review"


async def test_each_test_starts_from_an_empty_database(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Proves the clean_database fixture actually truncates.

    Without this, a test that passed only because of a previous test's rows
    would look like a real pass.
    """
    from sqlalchemy import func, select

    from reference_service.infrastructure.db.models import OrderRow

    async with sessionmaker() as session:
        count = await session.scalar(select(func.count()).select_from(OrderRow))

    assert count == 0


async def test_repeatable_read_is_transmitted_to_postgresql(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """The isolation_level execution option must actually reach the server.

    Task 4's review found get() could tear an aggregate under the default
    READ COMMITTED isolation: PostgreSQL gives each of get()'s two SELECTs
    its own snapshot, so a save() committing in between could hand back a
    header from one version and lines from another, and
    Order.total_must_match_lines would turn that healthy read into a 500.
    The fix pins the read transaction to REPEATABLE READ via
    READ_ISOLATION_LEVEL, applied through
    `session.connection(execution_options={"isolation_level": ...})`.

    That mechanism was unverified against a real database until now.
    Testing the race itself would be timing-dependent and flaky; what is
    deterministic, and what this asserts, is that PostgreSQL itself reports
    the isolation level took effect — queried with `SHOW
    transaction_isolation`, the same session variable PostgreSQL uses to
    answer `current_setting('transaction_isolation')`.

    What this test does NOT prove: that get() is the one actually setting
    this option. It opens its own session and applies the option directly,
    never constructing a PostgresOrderRepository or calling get() at all —
    a later review caught that a deleted isolation call inside get() itself
    would leave this test passing regardless. See
    test_get_pins_the_read_transaction_to_repeatable_read below for the
    call-site coverage this test does not provide.
    """
    async with sessionmaker() as session:
        await session.connection(
            execution_options={"isolation_level": READ_ISOLATION_LEVEL}
        )
        reported = await session.scalar(text("SHOW transaction_isolation"))

    # PostgreSQL reports the setting lowercased ("repeatable read"), while
    # the SQLAlchemy/asyncpg execution option spells it the standard SQL way
    # ("REPEATABLE READ") — asserted against READ_ISOLATION_LEVEL itself,
    # not a second hardcoded string, so this follows the constant if it
    # ever changes.
    assert reported == READ_ISOLATION_LEVEL.lower()


async def test_get_pins_the_read_transaction_to_repeatable_read(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """get() itself must be the one requesting REPEATABLE READ.

    The test above proves the mechanism works end to end; it does not
    prove get() is what invokes it. This test observes the REAL get() call
    instead, deterministically and with no timing dependence: a
    sqlalchemy.event listener on `set_connection_execution_options` (fired
    whenever `Connection.execution_options(...)` runs, which is what
    `session.connection(execution_options=...)` does under the hood)
    records every isolation_level any connection this engine hands out is
    given. `sessionmaker.kw["bind"]` recovers the underlying AsyncEngine
    that `async_sessionmaker` was built from — SQLAlchemy's event API
    operates on the sync layer even for an async engine, hence
    `engine.sync_engine` rather than `engine` itself.

    save() runs first only to create a row get() can find; the recording is
    cleared immediately afterward because save() sets no isolation_level of
    its own (confirmed: the list is empty at that point) and this test
    asserts on what get() alone contributes. The listener is removed in a
    `finally` because the engine — and the event registration on it — is
    session-scoped and shared with every other test in this file; leaving
    it attached would keep recording (and leaking state into) tests that
    run afterward.
    """
    engine = sessionmaker.kw["bind"]
    recorded_isolation_levels: list[str] = []

    def _record(conn: Connection, opts: dict[str, object]) -> None:
        if "isolation_level" in opts:
            recorded_isolation_levels.append(str(opts["isolation_level"]))

    event.listen(engine.sync_engine, "set_connection_execution_options", _record)
    try:
        repository = PostgresOrderRepository(sessionmaker)
        order = make_order()
        await repository.save(order)
        recorded_isolation_levels.clear()

        loaded = await repository.get(order.id)

        assert loaded is not None
        assert recorded_isolation_levels == [READ_ISOLATION_LEVEL]
    finally:
        event.remove(engine.sync_engine, "set_connection_execution_options", _record)


# A value distinctive enough that finding it in any message or traceback is
# unambiguous evidence of a leak, rather than a coincidental substring.
LEAK_CANARY = "FRAUD-REVIEW-CANARY-do-not-ship"


def order_the_database_will_refuse() -> Order:
    """A structurally valid Order carrying a total the CHECK constraint rejects.

    Built with model_construct/model_copy, which skip validation, because the
    domain will not produce this object: Money.amount is `ge=0` and
    Order.total_must_match_lines cross-checks the sum. That is the point — the
    row can only arrive from a path that bypassed the domain, which is exactly
    the bug class migration 000002's constraints exist to stop, and exactly
    when PostgreSQL composes the DETAIL text this test is about.
    """
    valid = make_order(internal_note=LEAK_CANARY)
    return valid.model_copy(
        update={"total": Money.model_construct(amount=Decimal("-5.00"), currency="EUR")}
    )


async def test_a_rejected_write_becomes_a_storage_constraint_error(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """A CHECK violation must not escape as a raw driver error."""
    repository = PostgresOrderRepository(sessionmaker)

    with pytest.raises(StorageConstraintViolatedError):
        await repository.save(order_the_database_will_refuse())


async def test_a_rejected_write_still_names_the_constraint(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """Scrubbing must not cost an operator the diagnosis.

    sqlstate 23514 is check_violation; the constraint and relation names come
    from migration 000002. Together they say precisely what failed without
    quoting anything from the row.
    """
    repository = PostgresOrderRepository(sessionmaker)

    with pytest.raises(StorageConstraintViolatedError) as caught:
        await repository.save(order_the_database_will_refuse())

    message = str(caught.value)
    assert "orders_total_amount_non_negative" in message
    assert "table_name=orders" in message
    assert "sqlstate=23514" in message


async def test_a_rejected_write_leaks_no_row_data_anywhere(
    sessionmaker: async_sessionmaker[AsyncSession],
) -> None:
    """The regression guard for `from None`, and the reason this file imports
    traceback.

    PostgreSQL puts the offending VALUES in its own error DETAIL — `Failing
    row contains (...)`, internal_note included — and asyncpg carries that
    into the exception text. `hide_parameters=True` on the engine cannot
    reach it, because that setting governs only the parameters the client
    sent. So the exception this adapter raises must not carry the original
    as __cause__ either: the catch-all handler in api/errors.py logs a full
    traceback, and a rendered traceback includes the cause.

    Asserting on the RENDERED TRACEBACK rather than on str(exc) is what makes
    this a real guard. A scrubbed message with `from exc` would pass a
    message-only assertion and still put the row in every log line.
    """
    repository = PostgresOrderRepository(sessionmaker)

    with pytest.raises(StorageConstraintViolatedError) as caught:
        await repository.save(order_the_database_will_refuse())

    rendered = "".join(
        traceback.format_exception(
            type(caught.value), caught.value, caught.value.__traceback__
        )
    )
    assert LEAK_CANARY not in rendered
    assert "Failing row contains" not in rendered
    assert caught.value.__cause__ is None
