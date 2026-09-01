"""Gate 4 of four: the SQLAlchemy models against the real migrated schema.

ALEMBIC IS NOT A MIGRATION TOOL IN THIS PROJECT. golang-migrate owns the
schema (spec D12): there is no alembic/ directory, no alembic.ini and no
alembic_version table, and nothing here generates a migration. Alembic is
installed as a development dependency for exactly one function —
compare_metadata — which is the only readily available engine that can diff a
set of SQLAlchemy models against a live database. This test asserts the
difference list is EMPTY. That restores the "you changed a model and forgot
the migration" protection that adopting golang-migrate would otherwise have
given up. See the comment beside alembic in pyproject.toml.
"""

from __future__ import annotations

from typing import Any

from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from sqlalchemy import Connection
from sqlalchemy.ext.asyncio import create_async_engine

from reference_service.infrastructure.db.models import Base


def _include_name(name: str | None, type_: str, parent_names: dict[str, Any]) -> bool:
    """Hide golang-migrate's bookkeeping table from the comparison.

    schema_migrations is created and owned by golang-migrate, is genuinely
    present in every migrated database, and is deliberately absent from
    Base.metadata — modelling another tool's private table would be wrong.
    Without this filter the gate reports a permanent, unfixable difference.

    Note gate 1 does the opposite and asserts the table IS in schema.sql: the
    snapshot describes the real database, while these models describe only
    the tables this application owns.
    """
    return not (type_ == "table" and name == "schema_migrations")


def _differences(connection: Connection) -> list[Any]:
    context = MigrationContext.configure(
        connection, opts={"include_name": _include_name}
    )
    return list(compare_metadata(context, Base.metadata))


async def test_gate_4_the_models_match_the_migrated_schema(
    database_url: str,
) -> None:
    """Every column, type, nullability, key and constraint must agree.

    A failure here means the models and the migrations disagree. Fix
    whichever is wrong — usually it is a model changed without its
    migration, which is precisely the mistake this gate exists to catch.
    """
    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            # compare_metadata is synchronous and wants a real DBAPI
            # connection. run_sync hands it one from inside the async
            # context, which is the supported way to use synchronous
            # SQLAlchemy tooling on an async engine.
            differences = await connection.run_sync(_differences)
    finally:
        await engine.dispose()

    assert differences == [], (
        f"the SQLAlchemy models and the migrated schema disagree:\n"
        f"{differences}\n"
        f"Either a model changed without a migration, or a migration changed "
        f"without the model."
    )


async def test_gate_4_would_notice_a_missing_migration(database_url: str) -> None:
    """Prove the gate has teeth, without leaving a fake model behind.

    A gate nobody has watched fail is a gate nobody knows works. This adds a
    table to a THROWAWAY MetaData — never to Base.metadata — so the check
    above is unaffected no matter how this test ends.
    """
    from sqlalchemy import Column, Integer, MetaData, Table

    pretend = MetaData()
    Table(
        "a_table_no_migration_creates", pretend, Column("id", Integer, primary_key=True)
    )

    def compare(connection: Connection) -> list[Any]:
        context = MigrationContext.configure(
            connection, opts={"include_name": _include_name}
        )
        return list(compare_metadata(context, pretend))

    engine = create_async_engine(database_url)
    try:
        async with engine.connect() as connection:
            differences = await connection.run_sync(compare)
    finally:
        await engine.dispose()

    kinds = {
        difference[0] for difference in differences if isinstance(difference, tuple)
    }
    assert "add_table" in kinds, (
        f"expected the comparison to demand the missing table; got {differences}"
    )
