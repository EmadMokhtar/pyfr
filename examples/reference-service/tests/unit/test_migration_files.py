"""Gate 3 of four: version collisions and malformed migration filenames.

golang-migrate applies every migration whose version is greater than the
database's current one. A migration merged later but numbered LOWER than an
environment's current version is silently skipped there, with no error and no
warning — spec section 6.4. Sequential numbering turns that into a git
conflict at merge time instead, and this test is what keeps the numbering
sequential.

No container and no database: this reads filenames.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# 000001_create_orders_tables.up.sql
FILENAME = re.compile(
    r"^(?P<version>\d{6})_(?P<name>[a-z0-9_]+)\.(?P<direction>up|down)\.sql$"
)


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def test_the_migrations_directory_is_not_empty() -> None:
    """Guards the three tests below, which all pass vacuously on an empty list."""
    assert migration_files(), f"no .sql files found in {MIGRATIONS_DIR}"


def test_every_migration_filename_is_well_formed() -> None:
    malformed = [
        path.name for path in migration_files() if not FILENAME.match(path.name)
    ]
    assert malformed == [], (
        f"malformed migration filenames: {malformed}. Expected six digits, an "
        f"underscore, a lowercase name, then .up.sql or .down.sql — for example "
        f"000003_add_orders_placed_at.up.sql"
    )


def test_every_version_has_exactly_one_up_and_one_down() -> None:
    """A missing down.sql is only discovered during an incident otherwise."""
    pairs: dict[str, set[str]] = {}
    for path in migration_files():
        match = FILENAME.match(path.name)
        assert match is not None, path.name
        pairs.setdefault(match["version"], set()).add(match["direction"])

    incomplete = {
        version: sorted(directions)
        for version, directions in pairs.items()
        if directions != {"up", "down"}
    }
    assert incomplete == {}, f"versions missing an up or a down file: {incomplete}"


def test_versions_are_sequential_from_one_with_no_gaps_or_duplicates() -> None:
    """Sequential numbering is what makes a collision a git conflict.

    Two branches that both add 000003 conflict on the filename at merge time.
    Timestamp-based numbering would let both land, and whichever sorted lower
    would then be skipped forever in any environment already past it.
    """
    versions = sorted(
        {
            match["version"]
            for path in migration_files()
            if (match := FILENAME.match(path.name)) is not None
        }
    )
    expected = [f"{index:06d}" for index in range(1, len(versions) + 1)]
    assert versions == expected, (
        f"migration versions must run 000001, 000002, ... with no gaps and no "
        f"duplicates. Found {versions}, expected {expected}"
    )


@pytest.mark.parametrize("direction", ["up", "down"])
def test_no_migration_file_is_empty(direction: str) -> None:
    """An empty down.sql passes the pairing test and still is not reversible."""
    empty = [
        path.name
        for path in MIGRATIONS_DIR.glob(f"*.{direction}.sql")
        if not path.read_text().strip()
    ]
    assert empty == [], f"empty {direction} migrations: {empty}"
