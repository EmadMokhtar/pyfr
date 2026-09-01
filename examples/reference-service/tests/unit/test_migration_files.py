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
from collections.abc import Iterable
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# 000001_create_orders_tables.up.sql
FILENAME = re.compile(
    r"^(?P<version>\d{6})_(?P<name>[a-z0-9_]+)\.(?P<direction>up|down)\.sql$"
)


def migration_files() -> list[Path]:
    return sorted(MIGRATIONS_DIR.glob("*.sql"))


def incomplete_or_duplicate_versions(paths: Iterable[Path]) -> dict[str, list[str]]:
    """Versions among `paths` that do not have exactly one up and one down.

    Directions are collected into a list, not a set. Two migrations sharing a
    version number under different names both contribute "up" (or both
    "down"); a set would silently collapse that pair into a single entry,
    hiding exactly the collision spec 6.5 gate 3 exists to reject. Such a
    version surfaces here as more than two entries, not as a false pass.

    Shared by `test_every_version_has_exactly_one_up_and_one_down` (against
    the real migrations/ directory) and its regression test below (against a
    synthetic one), so the two checks cannot silently drift apart.
    """
    pairs: dict[str, list[str]] = {}
    for path in paths:
        match = FILENAME.match(path.name)
        assert match is not None, path.name
        pairs.setdefault(match["version"], []).append(match["direction"])

    return {
        version: sorted(directions)
        for version, directions in pairs.items()
        if sorted(directions) != ["down", "up"]
    }


def test_the_migrations_directory_is_not_empty() -> None:
    """Guards the four tests below, which all pass vacuously on an empty list."""
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
    """A missing down.sql is only discovered during an incident otherwise.

    Also catches two migrations sharing a version number under different
    names — the collision spec 6.5 gate 3 exists to reject. That surfaces
    here as a version with more than two files, because
    `incomplete_or_duplicate_versions` tracks directions in a list rather
    than a set.
    """
    incomplete = incomplete_or_duplicate_versions(migration_files())
    assert incomplete == {}, (
        f"each version must have exactly one .up.sql and one .down.sql. "
        f"Versions that do not: {incomplete}. A version appearing more than "
        f"twice means two migrations share a number — the collision spec 6.5 "
        f"gate 3 exists to reject."
    )


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
        f"migration versions must run 000001, 000002, ... with no gaps. Found "
        f"{versions}, expected {expected}. (A duplicated version number is "
        f"rejected by test_every_version_has_exactly_one_up_and_one_down, not "
        f"here — the set comprehension above has already deduplicated by the "
        f"time this comparison runs.)"
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


def test_two_migrations_sharing_a_version_number_are_detected(
    tmp_path: Path,
) -> None:
    """Regression test: gate 3 must reject a version collision.

    Before this fix, the pairing check tracked directions in a `set`. Two
    independently-named migrations sharing version 000001 both added "up"
    once and both added "down" once, so the set held exactly {"up", "down"}
    and the check passed — silently accepting the exact scenario spec 6.5
    gate 3 exists to reject. Reproduced here in `tmp_path`, never in the real
    migrations/ directory, which a test must never mutate.
    """
    names = [
        "000001_first_migration.up.sql",
        "000001_first_migration.down.sql",
        "000001_second_migration.up.sql",
        "000001_second_migration.down.sql",
        "000002_third_migration.up.sql",
        "000002_third_migration.down.sql",
    ]
    for name in names:
        (tmp_path / name).write_text("-- not empty\n")

    incomplete = incomplete_or_duplicate_versions(sorted(tmp_path.glob("*.sql")))

    assert incomplete == {"000001": ["down", "down", "up", "up"]}
