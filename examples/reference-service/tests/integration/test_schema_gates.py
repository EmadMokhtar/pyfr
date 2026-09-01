"""Gates 1 and 2 of four: the schema snapshot, and reversibility.

Gate 3 (version collisions) is pure filename inspection and lives in
tests/unit/test_migration_files.py. Gate 4 (model drift) is in
test_schema_drift.py.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
from testcontainers.community.postgres import PostgresContainer

from tests.integration.conftest import MigrateRunner

SCHEMA_FILE = Path(__file__).resolve().parents[2] / "schema.sql"

# pg_dump (PostgreSQL 16.13 and later) brackets its output with
#     \restrict <random token>
#     \unrestrict <random token>
# and generates a FRESH token every run, so two dumps of an identical schema
# are not byte-identical. Verified: the only difference between two dumps of
# one unchanged database was these two lines. Strip them, or this gate fails
# on every run and reads as drift that is not there.
_DUMP_NONCE = re.compile(r"^\\(?:un)?restrict .*$", re.MULTILINE)

# pg_dump also stamps its header with the exact versions it ran as:
#     -- Dumped from database version 16.13
#     -- Dumped by pg_dump version 16.13
# conftest.py pins POSTGRES_IMAGE to the floating tag "postgres:16-alpine",
# so the next routine point release (16.13 -> 16.14) moves this line on
# whichever machine or CI runner next repulls the image, with no migration
# having changed. The same class of problem as the nonce above -- a false
# drift signal that looks exactly like a real one -- gets the same
# treatment: stripped, rather than worked around by pinning an exact patch
# version. A schema snapshot should describe the schema, not the tool that
# dumped it.
_DUMP_VERSION_BANNER = re.compile(
    r"^-- Dumped (?:from database|by pg_dump) version .*\n?", re.MULTILINE
)


def normalise_dump(dump: str) -> str:
    dump = _DUMP_NONCE.sub("", dump)
    dump = _DUMP_VERSION_BANNER.sub("", dump)
    return dump.strip() + "\n"


def dump_schema(container: PostgresContainer) -> str:
    """Structure only — no rows, no ownership, no grants.

    --no-owner and --no-privileges keep the snapshot free of the role names
    a particular environment happens to use, so the file describes the
    schema rather than the machine it was dumped from.
    """
    result = container.exec(
        [
            "pg_dump",
            "--schema-only",
            "--no-owner",
            "--no-privileges",
            "-U",
            "app",
            "-d",
            "app",
        ]
    )
    assert result.exit_code == 0, result.output.decode()
    return normalise_dump(result.output.decode())


def test_gate_1_the_committed_schema_matches_the_migrations(
    migrated_database: PostgresContainer,
) -> None:
    """The real schema is a reviewable artifact in every pull request.

    Without this file, seeing what the schema actually is means replaying
    every migration in your head. With it, a schema change shows up in the
    diff as a schema change.

    Regenerate after any migration change:  just schema-snapshot
    """
    actual = dump_schema(migrated_database)

    if os.environ.get("UPDATE_SCHEMA_SNAPSHOT") == "1":
        if os.environ.get("CI"):
            pytest.fail(
                "UPDATE_SCHEMA_SNAPSHOT must not be set in CI: it rewrites the "
                "committed snapshot instead of checking it, which turns this "
                "gate into a no-op that always passes. Regenerate locally with "
                "`just schema-snapshot` and commit the result."
            )
        SCHEMA_FILE.write_text(actual)
        return

    assert SCHEMA_FILE.exists(), (
        f"{SCHEMA_FILE.name} is missing. Generate it with: just schema-snapshot"
    )
    assert actual == SCHEMA_FILE.read_text(), (
        "the migrations no longer produce the committed schema.sql. If the "
        "change is intended, regenerate it with `just schema-snapshot` and "
        "commit the result; if it is not, the migrations are wrong."
    )


def test_gate_1_includes_migrate_s_own_bookkeeping_table(
    migrated_database: PostgresContainer,
) -> None:
    """schema_migrations belongs in the snapshot.

    A freshly migrated database genuinely has it, so a snapshot without it
    would not describe any real database. Note that gate 4 must EXCLUDE the
    same table for the opposite reason — it is not, and must not be, in the
    SQLAlchemy models. See test_schema_drift.py.
    """
    assert "schema_migrations" in dump_schema(migrated_database)


def test_gate_2_migrations_are_reversible(
    migrated_database: PostgresContainer,
    run_migrate: MigrateRunner,
) -> None:
    """All up, all down, all up again — and the schema is unchanged.

    A broken down.sql is otherwise discovered during an incident, at the
    worst possible moment, by the person trying to roll back.

    `down -all` rather than `down`: with no argument the command prompts for
    confirmation on standard input, and a container with no terminal
    attached would hang rather than fail.
    """
    before = dump_schema(migrated_database)

    down_code, down_logs = run_migrate("down -all")
    assert down_code == 0, f"migrate down -all failed:\n{down_logs}"

    up_code, up_logs = run_migrate("up")
    assert up_code == 0, f"re-applying migrations failed:\n{up_logs}"

    after = dump_schema(migrated_database)
    assert after == before, (
        "the schema after down-then-up differs from the schema before it: at "
        "least one down.sql does not fully reverse its up.sql"
    )


def test_gate_2_leaves_the_database_migrated_for_later_tests(
    migrated_database: PostgresContainer,
) -> None:
    """A guard on the test above, not on the migrations.

    The reversibility gate empties and rebuilds the schema in a session-scoped
    database that later tests share. If it ever returns early, this fails
    loudly here rather than as a confusing "relation does not exist" somewhere
    else.
    """
    assert "CREATE TABLE public.orders" in dump_schema(migrated_database)
