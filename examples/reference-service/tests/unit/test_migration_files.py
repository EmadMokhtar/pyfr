"""Gate 3, and a fifth gate: filenames, and an edit to an already-recorded file.

Gate 3 (below): golang-migrate applies every migration whose version is
greater than the database's current one. A migration merged later but
numbered LOWER than an environment's current version is silently skipped
there, with no error and no warning — spec section 6.4. Sequential numbering
turns that into a git conflict at merge time instead, and the tests in the
first half of this file are what keep the numbering sequential.

Gate 5 (the second half of this file, below the filename checks): every
other gate — this file's own filename checks included — rebuilds the
database from scratch, so none of them can see that an EXISTING migration
file's CONTENT changed. golang-migrate keeps no per-file checksum either, so
a developer who edits 000001_create_orders_tables.up.sql instead of adding a
new migration passes gates 1-4 cleanly: gate 3 sees an unchanged filename,
and gates 1, 2 and 4 all see a freshly built database that matches whatever
the edited file now says. Everywhere that migration has already been
applied — staging, production, every other developer's database — `migrate
up` reports "no change" and the edit never takes effect there. manifest.sha256
records each migration file's hash at the time it was last regenerated, and
the checks below recompute those hashes and fail the moment a RECORDED one no
longer matches — see spec section 6.4 for the write-up of the trap.

No container and no database anywhere in this file: it reads filenames and
file contents, nothing else.
"""

from __future__ import annotations

import hashlib
import re
from collections.abc import Iterable
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"
MANIFEST_FILE = MIGRATIONS_DIR / "manifest.sha256"

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


# --- Gate 5: an edit to an already-recorded migration file -----------------


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read_manifest(path: Path) -> dict[str, str]:
    """Parse `<sha256>  <filename>` lines into {filename: sha256}.

    Blank lines are skipped so a trailing newline in the file is not an
    entry. `split(maxsplit=1)`, not a fixed two-space split: sha256sum's own
    format uses a two-space separator too, but splitting on any run of
    whitespace is both compatible with it and does not depend on exactly
    reproducing that spacing.
    """
    entries: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        digest, filename = stripped.split(maxsplit=1)
        entries[filename] = digest
    return entries


def changed_manifest_entries(manifest: dict[str, str], directory: Path) -> list[str]:
    """Filenames `manifest` records whose on-disk hash no longer matches.

    A file with NO entry in `manifest` is not reported here — that is a
    brand-new migration, and adding one must never be obstructed by this
    check; `just migrate-manifest` is what adds its entry, not this
    function. A `manifest` entry naming a file that no longer exists on disk
    is likewise not reported: a deleted, already-committed migration file is
    a different mistake, one gate 3's pairing check is positioned to catch
    for a live migrations/ directory, and this function's only job is
    comparing bytes for files that exist in both places. Only a file the
    manifest already vouches for, and whose current bytes disagree with the
    hash recorded for it, is reported — the out-of-band edit to an
    already-recorded (and, in any real environment, quite possibly already
    APPLIED) migration that spec 6.4 warns about.
    """
    return sorted(
        filename
        for filename, recorded_hash in manifest.items()
        if (directory / filename).is_file()
        and file_sha256(directory / filename) != recorded_hash
    )


def write_manifest(
    directory: Path = MIGRATIONS_DIR, manifest_path: Path = MANIFEST_FILE
) -> None:
    """Regenerate the manifest from every .sql file currently in `directory`.

    Invoked by `just migrate-manifest`, never by a test: a test that wrote
    the file it then checks could never fail for the reason it exists. Do
    NOT run this after editing an already-committed migration to make gate 5
    pass again — that is precisely the edit this gate exists to catch, and
    regenerating the manifest to silence it defeats the entire point. It
    exists for the one legitimate case that changes what is on disk here: a
    brand-new migration pair.
    """
    lines = [
        f"{file_sha256(file)}  {file.name}" for file in sorted(directory.glob("*.sql"))
    ]
    manifest_path.write_text("\n".join(lines) + "\n")


def test_the_manifest_file_exists() -> None:
    """Guards the test below, which passes vacuously if the file is missing."""
    assert MANIFEST_FILE.exists(), (
        f"{MANIFEST_FILE.name} is missing. Generate it with: just migrate-manifest"
    )


def test_no_recorded_migration_file_has_changed_since_it_was_recorded() -> None:
    """Gate 5: catches an edit to an already-committed migration.

    See this file's module docstring for why none of gates 1-4 can see this,
    and spec section 6.4 for the write-up of the trap. A failure here means
    one of the files manifest.sha256 already vouches for no longer matches
    what was recorded — regenerate the manifest ONLY if this file is
    genuinely new, or if the edit is intentional and has not been applied
    anywhere yet; otherwise add a new migration instead of editing this one.
    """
    manifest = read_manifest(MANIFEST_FILE)
    changed = changed_manifest_entries(manifest, MIGRATIONS_DIR)
    assert changed == [], (
        f"these migration files have changed since manifest.sha256 recorded "
        f"their hash: {changed}. An already-committed migration must never be "
        f"edited: every environment that already applied it will never see "
        f'the change (`migrate up` reports "no change" there, silently). Add '
        f"a new migration instead. If this file is genuinely new, or its "
        f"content change is intentional and has not been applied anywhere "
        f"yet, regenerate the manifest with: just migrate-manifest"
    )


def test_editing_a_recorded_migration_is_detected(tmp_path: Path) -> None:
    """Regression test: gate 5 must reject an edit to a recorded file.

    Reproduced here in `tmp_path`, never against the real migrations/
    directory, which a test must never mutate — same discipline as
    test_two_migrations_sharing_a_version_number_are_detected above.
    """
    path = tmp_path / "000001_create_orders_tables.up.sql"
    path.write_text("CREATE TABLE orders (id UUID PRIMARY KEY);\n")
    manifest = {path.name: file_sha256(path)}

    # Recorded, unedited: nothing to report.
    assert changed_manifest_entries(manifest, tmp_path) == []

    # Edited after being recorded — exactly the trap: a developer needing a
    # new column edits the existing file instead of adding 000002.
    path.write_text("CREATE TABLE orders (id UUID PRIMARY KEY, shipping_note TEXT);\n")

    assert changed_manifest_entries(manifest, tmp_path) == [path.name]


def test_a_brand_new_unrecorded_migration_file_is_not_obstructed(
    tmp_path: Path,
) -> None:
    """Regression test: adding a migration must never be flagged by gate 5.

    A new file has no entry in `manifest` yet — nothing to compare against —
    so it must not be reported. `just migrate-manifest` is what gives it an
    entry; forgetting to run that is not the mistake this gate exists to
    catch.
    """
    manifest = read_manifest(MANIFEST_FILE)  # the real, committed manifest
    new_file = tmp_path / "000003_add_shipping_note.up.sql"
    new_file.write_text("ALTER TABLE orders ADD COLUMN shipping_note TEXT;\n")

    assert changed_manifest_entries(manifest, tmp_path) == []
