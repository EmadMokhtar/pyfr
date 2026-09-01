# PyFr M1 — Persistence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `examples/reference-service/` a real PostgreSQL database — schema owned by golang-migrate, rows read and written through a SQLAlchemy 2.0 async adapter behind M0's existing `OrderRepository` port — with an integration test tier on Testcontainers and all four schema governance gates running from one command.

**Architecture:** The dependency arrow does not move. `domain/` still imports nothing but Pydantic, `services/` still talks to the `OrderRepository` Protocol, and the new adapter is the only code that knows SQL exists. The transaction boundary lives *inside* the adapter: each repository call opens a session from a shared pool, does its work, and commits before returning. The composition root picks the PostgreSQL adapter or M0's in-memory one from configuration, so a service with no database stays a working path.

**Tech Stack:** SQLAlchemy 2.0 async, asyncpg, golang-migrate (`migrate/migrate:v4.19.0`), PostgreSQL 16, Testcontainers, Alembic (as a comparison engine only — see Task 9), sqlfluff.

**Spec:** `docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md` — section 6 (migrations and schema governance), D12 and D13, section 8.1 (integration tests), section 5.1 (settings).

**Predecessor:** `docs/superpowers/plans/2026-08-28-pyfr-m0-walking-skeleton.md`. M0 is merged and green: 102 tests pass, mypy clean, both import contracts kept.

## Global Constraints

Every task's requirements implicitly include these. The first eleven are inherited
from M0 unchanged; the rest are new in M1.

- **Python `>=3.13`.** `.python-version` contains `3.13`.
- **uv for everything Python.** `uv sync`, `uv run`, `uv lock`. No `pip`, no `requirements.txt`, no `pipx`, no manually activated virtual environment.
- **Plain Python only.** M1 is still Phase A. No Jinja, no cookiecutter variables, no `{{ }}` templating in any file. Templatisation is M7.
- **Package name is `reference_service`;** distribution name is `reference-service`. All work happens under `examples/reference-service/`.
- **The domain layer imports nothing but `pydantic`.** Not FastAPI, not the service layer, not infrastructure, and — new in M1 — not SQLAlchemy and not asyncpg.
- **The domain layer never knows an HTTP status code exists.**
- **mypy is strict on `domain/` and `services/`,** lenient elsewhere.
- **All logging goes through structlog.** OTLP export is M2 and must not appear in M1.
- **`/healthz` never checks a dependency.** Only `/readyz` does.
- **Line length 88.**
- **Conventional Commits** for every commit: `<type>[scope]: <description>`, imperative, lowercase, no trailing period.
- **golang-migrate owns the schema.** No Alembic migrations directory, no Alembic version table, no `Base.metadata.create_all()` anywhere — not in application code, not in a test fixture. Every database in every environment, including a throwaway test container, gets its schema by running the same migration files.
- **Pinned images.** `migrate/migrate:v4.19.0` and `postgres:16-alpine`, written in exactly one place per concern and referenced from there.
- **Unit tests never need Docker.** `just test` runs `tests/unit` and `tests/api` only. Anything requiring a container lives in `tests/integration` and runs under `just test-integration`.
- **`filterwarnings = ["error"]` stays.** Any new dependency that emits a `DeprecationWarning` on import fails the suite; Task 7 depends on knowing this.

---

## What M1 deliberately does not include

| Left out | Owner |
|---|---|
| OpenTelemetry, database span instrumentation, dashboards | M2 |
| `openapi.json` drift gate, Schemathesis, mutmut | M3 |
| Redis and S3 adapters, MinIO in compose | M4 |
| `.github/workflows/*` — the gates run from `just`, not from CI | M5 (release), M7 (template CI) |
| Seed data, `just config-check`, log redaction | M6 |
| `docs/runbook.md` and `docs/how-to/handle-a-dirty-migration.md`, named in spec 6.4 | M5 — the docs milestone. M1 still explains the dirty state where someone hits it: the comment above `migrate-force` in the `justfile` (Task 6) |
| A second aggregate, and therefore any cross-aggregate transaction | not planned; see Task 4's note |

---

## File Structure

```
examples/reference-service/
  migrations/                                   NEW — the schema, as plain SQL
    000001_create_orders_tables.up.sql
    000001_create_orders_tables.down.sql
    000002_add_order_lines_order_id_index.up.sql
    000002_add_order_lines_order_id_index.down.sql
  schema.sql                                    NEW — committed pg_dump snapshot
  Dockerfile.migrations                         NEW — FROM migrate/migrate + COPY
  .sqlfluff                                     NEW — SQL lint config

  src/reference_service/
    settings.py                                 MODIFIED — DatabaseSettings
    container.py                                MODIFIED — engine, adapter choice,
                                                  readiness check, pool disposal
    domain/errors.py                            MODIFIED — OrderConflictError
    services/order.py                           MODIFIED — validation boundary
    api/errors.py                               MODIFIED — comment + mapping
    infrastructure/
      db/                                       NEW
        __init__.py
        engine.py            build_engine, build_sessionmaker, async_dsn
        models.py            Base, OrderRow, OrderLineRow
        mappers.py           to_rows / to_domain
        order_repository.py  PostgresOrderRepository — the only SQL in the tree

  tests/
    unit/test_settings.py                       MODIFIED — database settings
    unit/test_migration_files.py                NEW — gate 3, no container
    unit/test_engine.py                         NEW — DSN driver swap
    unit/test_db_mappers.py                     NEW — mapping round trip
    unit/test_order_service.py                  MODIFIED — validation boundary
    integration/                                NEW
      __init__.py
      conftest.py            postgres + migrate containers, session fixtures
      test_order_repository.py                  the adapter against real SQL
      test_schema_gates.py                      gates 1 and 2
      test_schema_drift.py                      gate 4

  pyproject.toml   justfile   compose.yaml   .env.example
  .importlinter    .pre-commit-config.yaml  README.md            all MODIFIED
```

**Why `infrastructure/db/` is four files rather than one.** `engine.py` is pure
configuration and is unit-testable with no database. `models.py` is the SQLAlchemy
table definitions and is what gate 4 compares against. `mappers.py` is pure
functions and is unit-testable with no database. Only `order_repository.py` needs a
live connection. Splitting on that line means three of the four files have fast
tests, and the one slow file is small.

---

## Task 1: Dependencies, database settings, and the import contract

Nothing here touches the database yet. This task makes the configuration exist and
proves the layer boundary still holds once SQLAlchemy is installed.

**Files:**
- Modify: `examples/reference-service/pyproject.toml`
- Modify: `examples/reference-service/src/reference_service/settings.py`
- Modify: `examples/reference-service/.env.example`
- Modify: `examples/reference-service/.importlinter`
- Test: `examples/reference-service/tests/unit/test_settings.py`

**Interfaces:**
- Consumes: M0's `Settings`, `load_settings`, `EXIT_CONFIG_ERROR`.
- Produces: `DatabaseSettings` with fields `dsn: PostgresDsn`, `pool_size: int`, `statement_timeout_ms: int`; and `Settings.database: DatabaseSettings | None`. Tasks 4, 5 and 6 read these.

- [ ] **Step 1: Add the dependencies**

Run from `examples/reference-service/`:

```bash
uv add 'sqlalchemy[asyncio]>=2.0.52' 'asyncpg>=0.31'
uv add --dev 'alembic>=1.19' 'testcontainers[postgres]>=4.15'
```

`sqlalchemy[asyncio]` pulls in `greenlet`, which SQLAlchemy's async layer requires;
installing bare `sqlalchemy` produces a confusing `greenlet` import error at first
connection rather than at install time.

Alembic is a **development dependency and a comparison engine only** — Task 9
explains this at length and adds the comment that must sit beside it in
`pyproject.toml`. Add that comment now, so nobody deletes the dependency in the
meantime as an obvious mistake:

```toml
[dependency-groups]
dev = [
    # Alembic is NOT a migration tool in this project — golang-migrate owns the
    # schema (spec D12), and there is deliberately no alembic/ directory and no
    # alembic_version table. It is installed for exactly one job: its
    # compare_metadata() function is the comparison engine behind the
    # model/schema drift gate in tests/integration/test_schema_drift.py. Deleting
    # this dependency silently removes that gate. See Task 9 of the M1 plan.
    "alembic>=1.19",
    ...
]
```

- [ ] **Step 2: Split the unit and integration tiers in pytest configuration**

In `pyproject.toml`, register the marker and exclude the tier by default:

```toml
[tool.pytest.ini_options]
addopts = "-q --strict-markers --strict-config -m 'not integration'"
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    # Anything needing a container. Excluded from the default run by the `-m`
    # in addopts above, so `just test` stays a few seconds and needs no Docker.
    # `just test-integration` selects them back in with `-m integration`.
    "integration: requires a running Docker daemon",
]
```

`--strict-markers` is already present and is what makes a typo in a marker name an
error rather than a silently skipped test.

- [ ] **Step 3: Write the failing settings tests**

Append to `tests/unit/test_settings.py`:

```python
def test_database_is_absent_by_default() -> None:
    """No DSN configured means the in-memory adapter, not a crash.

    A service generated with database=none must keep working, so the
    sub-model is optional rather than required. Task 5 turns this None
    into the choice of adapter.
    """
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database is None


def test_database_settings_are_read_from_a_nested_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "APP_DATABASE__DSN", "postgresql://app:secret@localhost:5432/app"
    )
    monkeypatch.setenv("APP_DATABASE__POOL_SIZE", "3")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.database is not None
    assert str(settings.database.dsn) == "postgresql://app:secret@localhost:5432/app"
    assert settings.database.pool_size == 3
    # Defaults from the spec's section 5.1, not silently zero.
    assert settings.database.statement_timeout_ms == 5_000


def test_database_settings_are_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same reasoning as LogSettings and OtelSettings.

    Settings.model_config's frozen=True governs Settings's own fields only.
    Without its own frozen=True, `settings.database.pool_size = 99` would
    succeed silently while Settings claims to be frozen.
    """
    monkeypatch.setenv("APP_DATABASE__DSN", "postgresql://app:secret@localhost:5432/app")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database is not None

    with pytest.raises(ValidationError):
        settings.database.pool_size = 99  # type: ignore[misc]


def test_a_malformed_dsn_stops_the_process_with_exit_78(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail fast and loudly, exactly as every other bad setting does."""
    monkeypatch.setenv("APP_DATABASE__DSN", "mysql://app@localhost/app")

    with pytest.raises(SystemExit) as exit_info:
        load_settings(env_file=None)

    assert exit_info.value.code == EXIT_CONFIG_ERROR
```

Check the existing imports at the top of the file cover `pytest`, `ValidationError`,
`Settings`, `load_settings` and `EXIT_CONFIG_ERROR`; add whichever are missing.

- [ ] **Step 4: Run the tests and watch them fail**

```bash
uv run pytest tests/unit/test_settings.py -v
```

Expected: the four new tests fail. The first three fail with
`AttributeError: 'Settings' object has no attribute 'database'`; the fourth fails
because `load_settings` accepts the unknown variable and never exits.

- [ ] **Step 5: Add `DatabaseSettings`**

In `settings.py`, add `PostgresDsn` to the `pydantic` import and insert this class
above `Settings`:

```python
class DatabaseSettings(BaseModel):
    # See LogSettings.model_config for why each sub-model needs its own
    # frozen=True independently of Settings's.
    model_config = ConfigDict(frozen=True)

    # Stored WITHOUT a driver suffix — `postgresql://`, never
    # `postgresql+asyncpg://`. One setting has to satisfy two tools that
    # disagree about the URL: golang-migrate registers the driver names
    # `postgres` and `postgresql` and uses this string verbatim, while
    # SQLAlchemy needs the `+asyncpg` suffix to pick its driver. Storing the
    # plain form and letting infrastructure/db/engine.py add the suffix keeps
    # ONE variable in the environment. Storing two would let them drift, and
    # a service pointing its migrations at one database and its queries at
    # another fails in a way that takes hours to see.
    dsn: PostgresDsn
    pool_size: int = Field(default=10, ge=1)
    # Applied per connection as PostgreSQL's `statement_timeout`. A query that
    # runs longer is cancelled by the server, so one pathological statement
    # cannot hold a pooled connection open indefinitely.
    statement_timeout_ms: int = Field(default=5_000, ge=0)
```

Then add the field to `Settings`, after `otel`:

```python
    # Optional on purpose: None selects the in-memory adapter, which is the
    # path a service generated with database=none takes. See container.py.
    database: DatabaseSettings | None = None
```

- [ ] **Step 6: Run the tests and watch them pass**

```bash
uv run pytest tests/unit/test_settings.py -v
```

Expected: all pass, including M0's existing settings tests.

- [ ] **Step 7: Document the variables**

Append to `.env.example`:

```bash
# PostgreSQL. Leave APP_DATABASE__DSN unset to run on the in-memory
# repository with no database at all — the service still starts and serves.
#
# No `+asyncpg` in this URL and no `?sslmode=` on it. golang-migrate uses this
# string verbatim; the application adds the asyncpg driver itself. See the
# comment on DatabaseSettings.dsn in settings.py.
APP_DATABASE__DSN=postgresql://app:secret@localhost:5432/app
APP_DATABASE__POOL_SIZE=10
APP_DATABASE__STATEMENT_TIMEOUT_MS=5000
```

- [ ] **Step 8: Extend the import contracts**

In `.importlinter`, add `sqlalchemy` and `asyncpg` to the `forbidden_modules` list
of **both** contracts, so `domain` and `services` may not reach a database driver:

```ini
[importlinter:contract:domain-independence]
name = Domain imports no other layer and no web or database framework
type = forbidden
source_modules =
    reference_service.domain
forbidden_modules =
    reference_service.api
    reference_service.services
    reference_service.infrastructure
    reference_service.container
    reference_service.main
    fastapi
    starlette
    sqlalchemy
    asyncpg
```

Repeat the two new entries in the `services-independence` contract. The contract
name in the `domain-independence` block already says "database framework"; M0 wrote
that name in advance of the modules existing, and this step is what makes it true.

- [ ] **Step 9: Verify the whole suite and the contracts**

```bash
uv run pytest && uv run mypy && uv run lint-imports
```

Expected: every test passes, mypy reports no issues, both contracts KEPT.

- [ ] **Step 10: Prove the new contract can actually fail**

Add `import sqlalchemy` temporarily to `src/reference_service/domain/order.py`, then:

```bash
uv run lint-imports
```

Expected: `domain-independence` BROKEN, naming `reference_service.domain.order ->
sqlalchemy`. **Delete the import you just added** and re-run to confirm it is KEPT
again. A contract nobody has ever seen fail is a contract nobody knows works.

- [ ] **Step 11: Commit**

```bash
git add examples/reference-service
git commit -m "feat(settings): add optional postgresql database settings"
```

---

## Task 2: The migration files, the migrations image, and gate 3

**Files:**
- Create: `examples/reference-service/migrations/000001_create_orders_tables.up.sql`
- Create: `examples/reference-service/migrations/000001_create_orders_tables.down.sql`
- Create: `examples/reference-service/migrations/000002_add_order_check_constraints.up.sql`
- Create: `examples/reference-service/migrations/000002_add_order_check_constraints.down.sql`
- Create: `examples/reference-service/Dockerfile.migrations`
- Create: `examples/reference-service/.sqlfluff`
- Modify: `examples/reference-service/.pre-commit-config.yaml`
- Modify: `examples/reference-service/.dockerignore`
- Test: `examples/reference-service/tests/unit/test_migration_files.py`

**Interfaces:**
- Produces: the tables `orders` and `order_lines` with the exact column names and types Task 3's models must mirror — `orders(id, customer_id, total_amount, total_currency, internal_note)` and `order_lines(order_id, line_number, sku, quantity, unit_amount, unit_currency)`.

**Why two migrations, and why these two.** One migration cannot demonstrate the
ordering trap in section 6.4, and gives the reversibility gate a single step to walk.
The second one had to be genuinely useful or it would teach a bad habit — an index on
`order_lines.order_id`, the obvious candidate, is **redundant**, because the composite
primary key `(order_id, line_number)` already indexes that column as its leading key,
and PostgreSQL will use it for `WHERE order_id = ?`. Check constraints mirroring the
domain's own invariants are the honest choice: `Money.amount` is `ge=0` and
`OrderLine.quantity` is `gt=0` in `domain/order.py`, and having the database enforce
the same two rules is defence in depth against any writer that is not this
application.

- [ ] **Step 1: Write the failing gate 3 test**

This is the version collision check from spec 6.5, gate 3. It is pure filename
inspection, so it belongs in the unit tier and needs no Docker.

Create `tests/unit/test_migration_files.py`:

```python
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
```

- [ ] **Step 2: Run the test and watch it fail**

```bash
uv run pytest tests/unit/test_migration_files.py -v
```

Expected: `test_the_migrations_directory_is_not_empty` fails — the directory does
not exist yet, so `glob` returns nothing.

- [ ] **Step 3: Write the first migration**

Create `migrations/000001_create_orders_tables.up.sql`:

```sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    total_currency CHAR(3) NOT NULL,
    internal_note TEXT
);

CREATE TABLE order_lines (
    order_id UUID NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    line_number INTEGER NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_amount NUMERIC(14, 2) NOT NULL,
    unit_currency CHAR(3) NOT NULL,
    PRIMARY KEY (order_id, line_number)
);
```

Four column choices are load-bearing, and Task 9's drift gate compares every one of
them against `models.py`:

- `NUMERIC(14, 2)` mirrors `Money.amount`'s `max_digits=14, decimal_places=2`
  exactly. `NUMERIC` is arbitrary-precision decimal arithmetic; `FLOAT`/`REAL` would
  be binary floating point, which cannot represent `0.10` exactly and is the
  standard way money code develops a one-cent error.
- `CHAR(3)` mirrors `Currency`'s `^[A-Z]{3}$`.
- `line_number`, **not** `position`. `POSITION` is a SQL keyword, so `pg_dump`
  emits it quoted as `"position"`, which makes `schema.sql` noisier for no gain.
  Verified against PostgreSQL 16.13 while writing this plan.
- The primary key is the composite `(order_id, line_number)`, with no surrogate
  key. It is the natural key, it makes the line order part of the schema rather
  than an accident of insertion, and it removes any question about sequence state
  surviving a down/up cycle. `Order.lines` is an ordered `tuple`, so an order
  reloaded from a database that did not record line order would come back with its
  lines rearranged.

Create `migrations/000001_create_orders_tables.down.sql`:

```sql
DROP TABLE order_lines;
DROP TABLE orders;
```

Child first. `ON DELETE CASCADE` governs deleting *rows*, not dropping *tables* —
dropping `orders` while `order_lines` still references it fails.

- [ ] **Step 4: Write the second migration**

Create `migrations/000002_add_order_check_constraints.up.sql`:

```sql
ALTER TABLE order_lines
ADD CONSTRAINT order_lines_quantity_positive CHECK (quantity > 0);

ALTER TABLE order_lines
ADD CONSTRAINT order_lines_unit_amount_non_negative CHECK (unit_amount >= 0);

ALTER TABLE orders
ADD CONSTRAINT orders_total_amount_non_negative CHECK (total_amount >= 0);
```

Create `migrations/000002_add_order_check_constraints.down.sql`:

```sql
ALTER TABLE orders
DROP CONSTRAINT orders_total_amount_non_negative;

ALTER TABLE order_lines
DROP CONSTRAINT order_lines_unit_amount_non_negative;

ALTER TABLE order_lines
DROP CONSTRAINT order_lines_quantity_positive;
```

Every constraint is named explicitly. An unnamed `CHECK` gets a generated name like
`order_lines_check1`, which differs between databases and is impossible to write a
reliable `DROP CONSTRAINT` for.

- [ ] **Step 5: Run the gate 3 test and watch it pass**

```bash
uv run pytest tests/unit/test_migration_files.py -v
```

Expected: all pass.

- [ ] **Step 6: Prove gate 3 can fail**

Create an empty file `migrations/3_bad_name.sql`, run the test, and confirm
`test_every_migration_filename_is_well_formed` fails naming that file. Then create
`migrations/000004_skips_a_number.up.sql` and `.down.sql` with a comment inside
each, run again, and confirm
`test_versions_are_sequential_from_one_with_no_gaps_or_duplicates` fails reporting
the gap. **Delete all three files** and re-run to confirm green.

- [ ] **Step 7: Add the SQL linter configuration**

Create `.sqlfluff`:

```ini
[sqlfluff]
dialect = postgres
# The migration files are plain SQL with no Jinja or dbt templating in them.
# The default templater would try to interpret {{ }} and {% %}; `raw` does not,
# which also keeps M7's templatisation pass from being fought by the linter.
templater = raw
max_line_length = 88

[sqlfluff:rules:capitalisation.keywords]
capitalisation_policy = upper
```

Verified: `uvx sqlfluff lint migrations/` reports `All Finished!` with no violations
on all four files above.

- [ ] **Step 8: Enable the sqlfluff pre-commit hook**

In `.pre-commit-config.yaml`, replace the placeholder comment
`# sqlfluff waits for M1's migrations — there is no SQL to lint yet.` with the hook:

```yaml
  - repo: https://github.com/sqlfluff/sqlfluff
    rev: 3.4.2
    hooks:
      - id: sqlfluff-lint
        files: ^examples/reference-service/migrations/.*\.sql$
```

- [ ] **Step 9: Write the migrations image**

Create `Dockerfile.migrations`:

```dockerfile
# The migrations image: the schema, and nothing else.
#
# Built and pushed alongside the application image with the same version tag,
# and run as a Kubernetes init container or a pre-deployment Job. It contains
# no Python interpreter and no service code, so applying the schema never
# depends on the application being importable — which is the reason spec D12
# chose golang-migrate over Alembic.
FROM migrate/migrate:v4.19.0

COPY migrations/ /migrations/

# The base image's entrypoint is `migrate` itself, so this supplies its
# arguments. -database is deliberately absent: it is supplied at run time from
# the environment of whatever cluster this runs in, and baking a database URL
# into an image would put credentials in a registry.
CMD ["-path=/migrations", "up"]
```

- [ ] **Step 10: Verify and commit**

**Do not add `migrations/` to `.dockerignore`.** That file applies to the whole
build context, which both Dockerfiles share, so ignoring the directory would make
`Dockerfile.migrations`' own `COPY migrations/ /migrations/` fail. It is also
unnecessary: the application `Dockerfile` copies `pyproject.toml`, `uv.lock`,
`README.md` and `src` by name and never the whole context, so the SQL cannot reach
the application image.

```bash
uv run pytest && uvx sqlfluff lint migrations/
docker build -f Dockerfile.migrations -t reference-service-migrations:dev .
```

Expected: tests pass, `All Finished!` from sqlfluff, and the image builds.

```bash
git add examples/reference-service
git commit -m "feat(migrations): add the orders schema and the version collision gate"
```

---

## Task 3: SQLAlchemy models and the mapping functions

**Files:**
- Create: `examples/reference-service/src/reference_service/infrastructure/db/__init__.py` (empty)
- Create: `examples/reference-service/src/reference_service/infrastructure/db/models.py`
- Create: `examples/reference-service/src/reference_service/infrastructure/db/mappers.py`
- Test: `examples/reference-service/tests/unit/test_db_mappers.py`

**Interfaces:**
- Consumes: Task 2's table and column names; M0's `Order`, `OrderLine`, `Money`, `OrderId`, `CustomerId`, `total_of` from `domain/order.py`.
- Produces: `Base`, `OrderRow`, `OrderLineRow` (Task 9's drift gate compares `Base.metadata`); `order_values(order) -> dict[str, object]`, `line_values(order) -> list[dict[str, object]]`, `to_domain(row, lines) -> Order` (Task 4 calls all three).

**Why these are separate from the domain models.** `domain/order.py` may import nothing
but Pydantic — the import contract from Task 1 now enforces that against SQLAlchemy by
name. So the tables are described by their own classes here, and two small functions
move data across the boundary. The cost is the mapping code below; the payoff is that
`Order`'s invariants are enforced by Pydantic on the way *out* of the database as much
as on the way in, so a row edited by hand into an invalid state fails loudly at load
rather than propagating.

- [ ] **Step 1: Write the failing mapper tests**

These need no database: a declarative class can be instantiated in memory.

Create `tests/unit/test_db_mappers.py`:

```python
"""The mapping between rows and the Order aggregate. No database involved."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from pydantic import ValidationError

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
    total_of,
)
from reference_service.infrastructure.db.mappers import (
    line_values,
    order_values,
    to_domain,
)
from reference_service.infrastructure.db.models import OrderLineRow, OrderRow


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


def test_order_values_flattens_money_into_two_columns() -> None:
    order = make_order(internal_note="staff pick")

    values = order_values(order)

    assert values == {
        "id": order.id,
        "customer_id": order.customer_id,
        "total_amount": Decimal("6.75"),
        "total_currency": "EUR",
        "internal_note": "staff pick",
    }


def test_line_values_numbers_the_lines_from_zero_in_order() -> None:
    """The line number is what makes `Order.lines` an ordered tuple again.

    Without it, a reloaded order's lines come back in whatever order
    PostgreSQL felt like returning them, which is not an error and not
    detectable by the total — reordered lines sum to the same money.
    """
    order = make_order()

    values = line_values(order)

    assert [value["line_number"] for value in values] == [0, 1]
    assert [value["sku"] for value in values] == ["apple", "bread"]
    assert values[0]["unit_amount"] == Decimal("1.50")
    assert values[0]["unit_currency"] == "EUR"
    assert all(value["order_id"] == order.id for value in values)


def test_to_domain_rebuilds_an_equal_order() -> None:
    order = make_order(internal_note="staff pick")

    row = OrderRow(**order_values(order))
    line_rows = [OrderLineRow(**values) for values in line_values(order)]

    assert to_domain(row, line_rows) == order


def test_to_domain_revalidates_the_invariants() -> None:
    """A row whose total disagrees with its lines must not load silently.

    Rows can be edited by hand, restored from a backup taken mid-migration,
    or written by another service. Rebuilding through the Pydantic model
    means Order.total_must_match_lines runs on the way OUT of the database
    too, so corruption surfaces at load with a readable error instead of
    flowing into a response.
    """
    order = make_order()
    row = OrderRow(**{**order_values(order), "total_amount": Decimal("999.99")})
    line_rows = [OrderLineRow(**values) for values in line_values(order)]

    with pytest.raises(ValidationError):
        to_domain(row, line_rows)
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/unit/test_db_mappers.py -v
```

Expected: collection fails with `ModuleNotFoundError: No module named
'reference_service.infrastructure.db'`.

- [ ] **Step 3: Write the models**

Create `infrastructure/db/__init__.py` as an empty file, then
`infrastructure/db/models.py`:

```python
"""SQLAlchemy table definitions.

These mirror `migrations/` exactly, and the drift gate in
tests/integration/test_schema_drift.py is what keeps them mirroring it. They
are deliberately NOT the domain models: `domain/order.py` imports nothing but
Pydantic, and `.importlinter` fails the build if SQLAlchemy ever appears
there. mappers.py moves data between the two.

golang-migrate owns the schema. Nothing here ever calls
`Base.metadata.create_all()` — two tools creating one schema is exactly the
situation spec section 6.1 rules out, and a test database built by
create_all() would be testing the models against themselves rather than
against the migrations production actually runs.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OrderRow(Base):
    __tablename__ = "orders"
    __table_args__ = (
        # Mirrors migration 000002. Declared here as well as in SQL because the
        # drift gate compares this metadata against the real database.
        CheckConstraint("total_amount >= 0", name="orders_total_amount_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # NUMERIC, never FLOAT: `Money.amount` is a Decimal with two places, and
    # binary floating point cannot represent 0.10 exactly. (14, 2) matches
    # Money's own max_digits=14, decimal_places=2.
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class OrderLineRow(Base):
    __tablename__ = "order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="order_lines_quantity_positive"),
        CheckConstraint(
            "unit_amount >= 0", name="order_lines_unit_amount_non_negative"
        ),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    # Part of the primary key, so line order is recorded in the schema rather
    # than left to insertion order. `Order.lines` is an ordered tuple.
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
```

There is deliberately **no `relationship()`** between the two classes. SQLAlchemy's
lazy loading raises `MissingGreenlet` when an unloaded attribute is touched outside
an awaited context, which is the single most common way async SQLAlchemy code breaks
in production and not in tests. Task 4 loads the lines with an explicit ordered
query instead: two obvious statements beat one clever one that fails at a distance.

- [ ] **Step 4: Write the mappers**

Create `infrastructure/db/mappers.py`:

```python
"""Pure functions between database rows and the Order aggregate.

No session, no I/O, no SQLAlchemy execution — which is why these are tested
in the unit tier with no container.
"""

from __future__ import annotations

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from reference_service.infrastructure.db.models import OrderLineRow, OrderRow


def order_values(order: Order) -> dict[str, object]:
    """The `orders` row for this order, as a plain dict of column values.

    A dict rather than an OrderRow instance because Task 4 feeds it straight
    into an INSERT ... ON CONFLICT statement, which takes values, not mapped
    instances.
    """
    return {
        "id": order.id,
        "customer_id": order.customer_id,
        # Money is one value object; the database stores it as two columns.
        "total_amount": order.total.amount,
        "total_currency": order.total.currency,
        "internal_note": order.internal_note,
    }


def line_values(order: Order) -> list[dict[str, object]]:
    """The `order_lines` rows for this order, numbered in tuple order."""
    return [
        {
            "order_id": order.id,
            "line_number": line_number,
            "sku": line.sku,
            "quantity": line.quantity,
            "unit_amount": line.unit_price.amount,
            "unit_currency": line.unit_price.currency,
        }
        for line_number, line in enumerate(order.lines)
    ]


def to_domain(row: OrderRow, lines: list[OrderLineRow]) -> Order:
    """Rebuild the aggregate. `lines` must already be ordered by line_number.

    Construction runs every Pydantic validator, including
    Order.total_must_match_lines, so an inconsistent set of rows fails here
    rather than producing a nonsense response.
    """
    return Order(
        id=OrderId(row.id),
        customer_id=CustomerId(row.customer_id),
        lines=tuple(
            OrderLine(
                sku=line.sku,
                quantity=line.quantity,
                unit_price=Money(
                    amount=line.unit_amount, currency=line.unit_currency
                ),
            )
            for line in lines
        ),
        total=Money(amount=row.total_amount, currency=row.total_currency),
        internal_note=row.internal_note,
    )
```

- [ ] **Step 5: Run the tests and watch them pass**

```bash
uv run pytest tests/unit/test_db_mappers.py -v && uv run mypy && uv run lint-imports
```

Expected: four tests pass, mypy clean, both contracts KEPT.

- [ ] **Step 6: Commit**

```bash
git add examples/reference-service
git commit -m "feat(db): add sqlalchemy models and the row-to-aggregate mappers"
```

---

## Task 4: The engine and the PostgreSQL repository adapter

**Files:**
- Create: `examples/reference-service/src/reference_service/infrastructure/db/engine.py`
- Create: `examples/reference-service/src/reference_service/infrastructure/db/order_repository.py`
- Test: `examples/reference-service/tests/unit/test_engine.py`

**Interfaces:**
- Consumes: Task 1's `DatabaseSettings`; Task 3's `OrderRow`, `OrderLineRow`, `order_values`, `line_values`, `to_domain`.
- Produces: `async_dsn(dsn: PostgresDsn) -> str`, `build_engine(settings: DatabaseSettings) -> AsyncEngine`, `build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]`, and `PostgresOrderRepository(sessionmaker)` satisfying M0's `OrderRepository` port. Task 5 calls all four.

**Where the transaction lives.** Each repository call opens its own session and its
own transaction, and commits before returning. This is not a compromise: an aggregate
*is* the transactional consistency boundary in the light-DDD model spec D5 committed
to, so one transaction per aggregate save is the intended shape, and `save()` writing
both tables inside one transaction is exactly the guarantee that matters. Two
alternatives were considered and rejected while designing M1:

- **Committing in a FastAPI `yield` dependency.** Measured, not assumed: a dependency's
  cleanup code runs *after* the response is produced. A commit that fails there is
  invisible — the probe returned `200 {"ok": true}` to the client while the commit
  raised. Rollback in a dependency is safe (route exceptions do reach it); a commit is
  not. Committing inside the call means a failure raises during the request and becomes
  a 500 through M0's existing Problem Details handler.
- **An explicit `UnitOfWork` port.** It buys atomicity across several aggregates,
  which nothing in this service needs, and costs a new domain concept plus a rewrite
  of the services layer and its tests. If a team later needs two aggregates written
  together, that is when to add it — see the comment in `order_repository.py` below.

"A session per call" is not a connection per call. The engine and its pool are built
once in `container.py`; each call checks a connection out of that pool and returns it.

**Where the read isolation lives.** The paragraphs above are about `save()`;
`get()` needs its own guarantee, for a different reason. It issues two SELECTs —
one for the `orders` row, one for its `order_lines` — and PostgreSQL's default
`READ COMMITTED` gives each *statement*, not each transaction, its own snapshot.
A `save()` that commits between those two SELECTs can hand `get()` an order's
header from one version and its lines from another; `Order.total_must_match_lines`
then rejects the mismatch, turning a healthy read into a 500 the caller did nothing
to deserve. `get()` pins its transaction to `REPEATABLE READ` before the first
SELECT runs (see `READ_ISOLATION_LEVEL` in `order_repository.py`, Step 5) so both
SELECTs share one snapshot — a read-only transaction, so this cannot itself raise
the serialization failures a writing transaction under `REPEATABLE READ` could.
`save()`'s atomicity and `get()`'s isolation level are two halves of the same
promise: the writer never leaves a half-written state to be committed, and the
reader never straddles two different commits.

- [ ] **Step 1: Write the failing engine tests**

Create `tests/unit/test_engine.py`:

```python
"""Engine configuration. No database is contacted by any test here."""

from __future__ import annotations

import pytest
from pydantic import PostgresDsn, TypeAdapter

from reference_service.infrastructure.db.engine import async_dsn

_dsn = TypeAdapter(PostgresDsn)


def test_the_asyncpg_driver_is_added_to_a_plain_url() -> None:
    """One environment variable has to serve two tools that disagree.

    golang-migrate uses APP_DATABASE__DSN verbatim and knows the driver
    names `postgres` and `postgresql`. SQLAlchemy needs `+asyncpg` to pick
    its driver. Storing the plain form and adding the suffix here keeps one
    variable in the environment instead of two that can drift apart.
    """
    result = async_dsn(_dsn.validate_python("postgresql://app:secret@db:5432/app"))

    assert result == "postgresql+asyncpg://app:secret@db:5432/app"


def test_the_postgres_scheme_spelling_is_also_handled() -> None:
    result = async_dsn(_dsn.validate_python("postgres://app:secret@db:5432/app"))

    assert result == "postgresql+asyncpg://app:secret@db:5432/app"


def test_an_explicit_driver_is_left_alone() -> None:
    """Someone who spelled out a driver meant it; do not rewrite their URL."""
    result = async_dsn(
        _dsn.validate_python("postgresql+asyncpg://app:secret@db:5432/app")
    )

    assert result == "postgresql+asyncpg://app:secret@db:5432/app"


def test_a_libpq_only_query_parameter_is_rejected_with_a_readable_message() -> None:
    """`sslmode` is a libpq parameter that asyncpg does not understand.

    Without this check the failure is a TypeError from deep inside asyncpg
    at first connection, long after startup, naming neither the setting nor
    the file it came from. golang-migrate DOES want `?sslmode=disable`
    locally, so this mistake is an easy one to make; the compose file and
    the justfile add it at the migrate call site instead.
    """
    with pytest.raises(ValueError, match="sslmode"):
        async_dsn(
            _dsn.validate_python("postgresql://app:secret@db:5432/app?sslmode=disable")
        )


def test_unrelated_text_that_merely_contains_sslmode_is_not_rejected() -> None:
    """The guard checks query PARAMETER NAMES, not a raw substring scan.

    `parse_qs` splits each query pair on its FIRST "=" only, so text after
    that first "=" may itself contain more "=" characters. libpq's own
    `options` parameter carries a freeform "-c key=value" string as its
    VALUE, so `?options=-c search_path=sslmode=app` puts the literal text
    "sslmode=" into the raw URL without `sslmode` ever being the parameter
    NAME — the parsed key is "options", not "sslmode". A
    `"sslmode=" in raw` scan (the earlier, wrong version of this check)
    cannot tell the difference and would have wrongly rejected this DSN;
    confirmed directly in the fix report rather than assumed. The new
    parser-based check does not reject it.
    """
    result = async_dsn(
        _dsn.validate_python(
            "postgresql://app:secret@db:5432/app?options=-c search_path=sslmode=app"
        )
    )

    assert result == (
        "postgresql+asyncpg://app:secret@db:5432/app"
        "?options=-c%20search_path=sslmode=app"
    )
```

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/unit/test_engine.py -v
```

Expected: `ModuleNotFoundError` for `reference_service.infrastructure.db.engine`.

- [ ] **Step 3: Write the engine module**

Create `infrastructure/db/engine.py`:

```python
"""Engine and session factory construction.

Built once, at startup, by container.py. Everything here is configuration;
no query lives in this module.
"""

from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from pydantic import PostgresDsn
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from reference_service.settings import DatabaseSettings

# Parameters libpq accepts and asyncpg does not. golang-migrate wants
# `?sslmode=disable` against a local database, so a developer who puts the
# migrate URL into APP_DATABASE__DSN hits this. Rejecting it here, at startup,
# with the setting named, beats a TypeError from inside asyncpg at the first
# request.
_LIBPQ_ONLY_PARAMETERS = ("sslmode", "sslcert", "sslkey", "sslrootcert")


def async_dsn(dsn: PostgresDsn) -> str:
    """Return `dsn` with the asyncpg driver, leaving an explicit driver alone."""
    raw = str(dsn)
    # Parse the query string and check parameter NAMES, rather than scanning
    # the whole URL for the substring "sslmode=". A raw substring scan also
    # matches unrelated content that merely contains that text — libpq's own
    # `options` parameter carries a freeform "-c key=value" string as its
    # VALUE, so e.g. `?options=-c search_path=sslmode=app` puts the literal
    # text "sslmode=" into the URL without `sslmode` ever being a parameter
    # NAME (parse_qs splits each pair on its first "=" only, so the parsed
    # key here is "options", not "sslmode"); a substring scan cannot tell
    # the difference and would falsely reject this DSN. Never interpolate
    # `raw` into an error message below: it carries the password, and this
    # ValueError is raised, uncaught, from container startup — straight to
    # stderr and the log aggregator.
    query_parameters = parse_qs(urlsplit(raw).query)
    for parameter in _LIBPQ_ONLY_PARAMETERS:
        if parameter in query_parameters:
            raise ValueError(
                f"APP_DATABASE__DSN must not carry the libpq parameter "
                f"'{parameter}': asyncpg does not understand it. Remove it "
                f"from the URL — the migrate commands add '?sslmode=disable' "
                f"themselves."
            )

    scheme, separator, rest = raw.partition("://")
    if not separator:
        raise ValueError(
            "not a database URL: missing '://' between the scheme and the rest"
        )
    if "+" in scheme:
        return raw
    return f"postgresql+asyncpg://{rest}"


def build_engine(settings: DatabaseSettings) -> AsyncEngine:
    return create_async_engine(
        async_dsn(settings.dsn),
        pool_size=settings.pool_size,
        # Checking a connection out of the pool verifies it first, so a
        # connection killed by a database restart or an idle-timeout proxy is
        # replaced rather than handed to a request that then fails.
        pool_pre_ping=True,
        connect_args={
            # Applied by the server, per connection. A statement running longer
            # is cancelled, so one pathological query cannot hold a pooled
            # connection open indefinitely. asyncpg takes server settings as
            # strings.
            "server_settings": {"statement_timeout": str(settings.statement_timeout_ms)}
        },
    )


def build_sessionmaker(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        engine,
        # After commit, attribute access on a loaded object would otherwise
        # trigger a refresh query — which, outside an awaited context, raises
        # MissingGreenlet rather than reloading. Nothing here needs the refresh:
        # the mappers copy values out before the session closes.
        expire_on_commit=False,
    )
```

- [ ] **Step 4: Run the tests and watch them pass**

```bash
uv run pytest tests/unit/test_engine.py -v
```

Expected: five tests pass.

- [ ] **Step 5: Write the repository adapter**

Create `infrastructure/db/order_repository.py`. The base logic — the round
trip, the line ordering, the upsert, and the `None` case — was written and run
against PostgreSQL 16.13 while preparing this plan and confirmed working. The
`REPEATABLE READ` isolation level on `get()` was added afterward, during Task
4's own review, to close a torn-read gap explained in the code comment below;
Task 7's integration tier is what confirms it actually takes effect against a
real database.

```python
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
            # get()'s freedom from torn reads is not this method's atomicity
            # alone. This transaction either commits both statements above or
            # neither, but a reader using the default isolation level could
            # still take its two SELECTs from either side of that commit.
            # READ_ISOLATION_LEVEL on the read side is the other half of the
            # guarantee — see its comment near the top of this module.
```

- [ ] **Step 6: Verify the port is still satisfied structurally**

Append to `tests/unit/test_engine.py`:

```python
def test_the_postgres_adapter_satisfies_the_repository_port() -> None:
    """Structural, not nominal: no inheritance, no import of the Protocol.

    Mirrors both assertions in tests/unit/test_memory_repository.py: the
    annotated binding below (`repository: OrderRepository = ...`) is what
    gives mypy the full signature check — parameter types, return types, and
    async-ness — because mypy compares the assigned value against the
    declared type on every annotated assignment. The isinstance call that
    follows only confirms, at runtime, that the named attributes exist;
    runtime_checkable does not check signatures at all.
    """
    from reference_service.domain.repositories import OrderRepository
    from reference_service.infrastructure.db.order_repository import (
        PostgresOrderRepository,
    )

    repository: OrderRepository = PostgresOrderRepository(sessionmaker=None)  # type: ignore[arg-type]
    assert isinstance(repository, OrderRepository)
```

- [ ] **Step 7: Verify everything**

```bash
uv run pytest && uv run mypy && uv run lint-imports
```

Expected: all pass, mypy clean, both contracts KEPT. No container has been needed
by any test so far — Task 7 introduces the first one.

- [ ] **Step 8: Commit**

```bash
git add examples/reference-service
git commit -m "feat(db): add the async engine and the postgresql order repository"
```

---

## Task 5: Wire the composition root and the readiness check

**Files:**
- Modify: `examples/reference-service/src/reference_service/container.py`
- Test: `examples/reference-service/tests/unit/test_container.py` (new)

**Interfaces:**
- Consumes: Task 4's `build_engine`, `build_sessionmaker`, `PostgresOrderRepository`; M0's `Container`, `ReadinessRegistry`, `InMemoryOrderRepository`.
- Produces: `Container.engine: AsyncEngine | None`; `build_container` choosing the adapter from `settings.database`; `close_container` disposing the pool. Nothing above the container changes — `api/deps.py`, `services/order.py` and every router keep working untouched, which is the point of the port.

`create_async_engine` does not open a connection: it builds a pool that connects
lazily on first use. That is what lets every test in this task run without Docker.

- [ ] **Step 1: Write the failing container tests**

Create `tests/unit/test_container.py`:

```python
"""The composition root's adapter choice. No database is contacted."""

from __future__ import annotations

import pytest

from reference_service.container import build_container, close_container
from reference_service.infrastructure.db.order_repository import (
    PostgresOrderRepository,
)
from reference_service.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from reference_service.settings import Settings

DSN = "postgresql://app:secret@localhost:5432/app"


def test_no_database_configured_selects_the_in_memory_adapter() -> None:
    """A service generated with database=none must still start and serve."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert isinstance(container.orders, InMemoryOrderRepository)
    assert container.engine is None


def test_no_database_configured_registers_no_readiness_check() -> None:
    """/readyz must not report on a dependency this service does not have."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert container.readiness._checks == {}


def test_a_configured_dsn_selects_the_postgresql_adapter(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE__DSN", DSN)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert isinstance(container.orders, PostgresOrderRepository)
    assert container.engine is not None


def test_a_configured_dsn_registers_a_database_readiness_check(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE__DSN", DSN)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    container = build_container(settings)

    assert "database" in container.readiness._checks


async def test_close_container_disposes_the_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A pool left open holds connections after shutdown begins.

    M0's close_container did nothing and said so; this is the M1 case it
    was waiting for.
    """
    monkeypatch.setenv("APP_DATABASE__DSN", DSN)
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    container = build_container(settings)
    assert container.engine is not None

    disposed = False

    async def record_dispose() -> None:
        nonlocal disposed
        disposed = True

    monkeypatch.setattr(container.engine, "dispose", record_dispose)

    await close_container(container)

    assert disposed


async def test_close_container_is_safe_without_a_database() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    await close_container(build_container(settings))  # must not raise
```

`container.readiness._checks` reaches into a private attribute. That is deliberate
and confined to this file: the registry exposes no read API, adding one purely for a
test would be worse, and these two tests are the only place the contents matter.

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/unit/test_container.py -v
```

Expected: failures on `container.engine` not existing, and on the PostgreSQL adapter
never being selected.

- [ ] **Step 3: Rewrite the container's construction**

In `container.py`, add the imports:

```python
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine

from reference_service.infrastructure.db.engine import (
    build_engine,
    build_sessionmaker,
)
from reference_service.infrastructure.db.order_repository import (
    PostgresOrderRepository,
)
```

Add the field to `Container`:

```python
@dataclass
class Container:
    settings: Settings
    orders: OrderRepository
    # None when no database is configured. Held only so close_container can
    # dispose the pool at shutdown; nothing else reaches for it.
    engine: AsyncEngine | None = None
    readiness: ReadinessRegistry = field(default_factory=ReadinessRegistry)
    started: bool = False
```

Replace `build_container` and `close_container`:

```python
def build_container(settings: Settings) -> Container:
    if settings.database is None:
        # No database configured: the in-memory adapter, and no readiness
        # check, because there is no dependency to report on.
        return Container(settings=settings, orders=InMemoryOrderRepository())

    engine = build_engine(settings.database)
    container = Container(
        settings=settings,
        orders=PostgresOrderRepository(build_sessionmaker(engine)),
        engine=engine,
    )

    async def database_is_reachable() -> None:
        # Deliberately trivial. /readyz answers "can this process reach its
        # dependencies", not "is the schema correct" — a readiness probe that
        # runs a real query turns a slow database into an unready pod and takes
        # the service out of rotation for a problem it could have served
        # through. ReadinessRegistry.run bounds this with its own timeout and
        # reports only the exception TYPE, so a connection string in a driver's
        # error message never reaches the response body.
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    container.readiness.register("database", database_is_reachable)
    return container


async def close_container(container: Container) -> None:
    """Release resources. Runs after in-flight requests finish."""
    if container.engine is not None:
        # Closes every pooled connection. Without this, shutdown leaves
        # connections open until the server times them out, and a rolling
        # deployment can exhaust the database's connection limit with the
        # sockets of pods that have already stopped serving.
        await container.engine.dispose()
```

Delete the now-stale docstring line `"""Release resources. Nothing to close in M0;
M1 closes the database pool."""` — that sentence was a note to this task and is no
longer true.

- [ ] **Step 4: Run the tests and watch them pass**

```bash
uv run pytest tests/unit/test_container.py -v
```

Expected: six tests pass.

- [ ] **Step 5: Confirm nothing above the container had to change**

```bash
git status --porcelain examples/reference-service/src/reference_service/api
git status --porcelain examples/reference-service/src/reference_service/services
```

Expected: **no output from either.** The api and services layers are untouched by
persistence, which is the whole claim the port makes. If either reports a modified
file, something leaked through the boundary — stop and find out what.

- [ ] **Step 6: Run the full suite**

```bash
uv run pytest && uv run mypy && uv run lint-imports
```

Expected: M0's 102 tests plus the new ones, all passing, with no database anywhere.

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service
git commit -m "feat(container): select the database adapter from settings"
```

---

## Task 6: The compose stack and the migration commands

**Files:**
- Modify: `examples/reference-service/compose.yaml`
- Modify: `examples/reference-service/justfile`

**Interfaces:**
- Consumes: Task 2's `Dockerfile.migrations` and `migrations/`; Task 1's `APP_DATABASE__DSN`.
- Produces: `just migrate`, `just migrate-new NAME`, `just migrate-down N`, `just migrate-version`, `just migrate-force V`, `just psql`; and a `just up` that yields a migrated database and a running API in one command.

**The one place the local database URL is written.** It is the `entrypoint` of the
`migrate` compose service, and every recipe below inherits it by passing only a
subcommand. Repeating a connection string across a compose file and five justfile
recipes is how a service ends up migrating one database and querying another.

- [ ] **Step 1: Add postgres and migrate to compose**

Replace `compose.yaml` with:

```yaml
services:
  postgres:
    image: postgres:16-alpine
    environment:
      POSTGRES_USER: app
      POSTGRES_PASSWORD: secret
      POSTGRES_DB: app
    ports:
      # Published so `just psql` and any local tool can reach it. The
      # application inside compose does NOT use this — it connects over the
      # compose network to the host name `postgres`.
      - "5432:5432"
    healthcheck:
      # `migrate` and `app` both wait on this. Without it they start while
      # PostgreSQL is still initialising and fail on connection refused.
      # pg_isready is the server's own readiness tool and needs no client.
      test: ["CMD-SHELL", "pg_isready -U app -d app"]
      interval: 2s
      timeout: 3s
      retries: 15
    volumes:
      - postgres-data:/var/lib/postgresql/data

  migrate:
    build:
      context: .
      dockerfile: Dockerfile.migrations
    depends_on:
      postgres:
        condition: service_healthy
    volumes:
      # Mounted over the directory the image COPYs in, so migrations edited on
      # the host apply without rebuilding, and `just migrate-new` writes its new
      # files back out to the host. Production runs the image as built, with no
      # mount — see Dockerfile.migrations.
      - ./migrations:/migrations
    # The single definition of the local database URL. Every `just migrate-*`
    # recipe passes only a subcommand and inherits these flags.
    #
    # `?sslmode=disable` belongs HERE and not in APP_DATABASE__DSN: it is a
    # libpq parameter, golang-migrate requires it against a local server with
    # no TLS, and asyncpg rejects it. engine.py fails loudly if it ever appears
    # in the application's own URL.
    entrypoint:
      - migrate
      - -path=/migrations
      - -database
      - postgres://app:secret@postgres:5432/app?sslmode=disable
    command: ["up"]

  app:
    build: .
    ports:
      - "8000:8000"
    depends_on:
      # Not just "started": the API must not serve a request against a schema
      # that is not there yet. service_completed_successfully waits for the
      # one-shot migrate container to exit 0, so `just up` is a single command
      # that yields a migrated database and a working API.
      migrate:
        condition: service_completed_successfully
    environment:
      APP_ENVIRONMENT: production
      APP_LOG__LEVEL: info
      # Host `postgres` is the compose service name. No driver suffix and no
      # sslmode — see settings.py's DatabaseSettings.dsn.
      APP_DATABASE__DSN: postgresql://app:secret@postgres:5432/app
    # The Dockerfile's CMD passes uvicorn --timeout-graceful-shutdown 30,
    # letting in-flight requests drain for up to 30s on SIGTERM. Compose's
    # (and Docker's) own default kill deadline is 10s, so without raising
    # it here the container is SIGKILLed at 10s regardless — a promise
    # uvicorn cannot keep. Set comfortably above the app's own deadline so
    # the app's timeout is always the one that governs shutdown.
    stop_grace_period: 40s
    # No healthcheck: block here. The image already declares one (see the
    # Dockerfile's HEALTHCHECK), and it reads APP_HTTP_PORT the same way
    # the CMD does. A hardcoded port here would drift from that the moment
    # APP_HTTP_PORT is overridden — Compose applies the image's own
    # healthcheck automatically, so duplicating it just to hardcode the
    # port both drifts and repeats the same instruction twice.

volumes:
  postgres-data:
```

The `app` service's existing comments are carried over from M0 unchanged; only
`depends_on`, `environment` and the `ports` block are new.

- [ ] **Step 2: Add the migration recipes**

Add to `justfile`, after the existing `imports` recipe:

```just
# Apply every outstanding migration. Uses the migrate service's entrypoint,
# so the database URL lives in exactly one place — compose.yaml.
migrate:
    docker compose run --rm migrate up

# Write a new .up.sql / .down.sql pair. -seq gives sequential numbering, which
# is what turns two branches adding a migration into a git conflict instead of
# a silently skipped file (spec 6.4). --no-deps because creating files needs no
# database, and --entrypoint skips the -database flag `create` has no use for.
migrate-new name:
    docker compose run --rm --no-deps --entrypoint migrate migrate \
        create -ext sql -dir /migrations -seq {{name}}

# Roll back N steps. Defaults to one, because `down` with no argument means
# "all the way to empty" and that is not a default anyone wants to type twice.
migrate-down steps="1":
    docker compose run --rm migrate down {{steps}}

# Current version, and whether the database is dirty.
migrate-version:
    docker compose run --rm migrate version

# Clear a dirty flag by declaring the true version. Read the warning below
# before using this.
migrate-force version:
    docker compose run --rm migrate force {{version}}

# An interactive psql session against the running compose database.
psql:
    docker compose exec postgres psql -U app -d app
```

Add this comment block immediately above `migrate-force`, because the dirty state
is confusing exactly when someone is under pressure:

```just
# `migrate force` does NOT run or undo any SQL. It only overwrites the version
# recorded in schema_migrations and clears the dirty flag.
#
# A migration that fails partway leaves the database dirty, and golang-migrate
# then refuses every further command — correctly, because it cannot know how
# much of the failed file actually applied. Recovering means a human looking at
# the real schema, finishing or reversing the partial change BY HAND, and only
# then running `just migrate-force <the version that is genuinely applied>`.
# Running it first, to make the error go away, tells the tool a lie it will
# believe for the rest of the database's life.
```

- [ ] **Step 3: Start the stack and watch the ordering work**

```bash
docker compose down -v          # start from nothing
just up
```

Expected, in order: `postgres` becomes healthy; `migrate` runs, logs `1/u
create_orders_tables` and `2/u add_order_check_constraints`, and exits 0; `app`
starts only then and reports healthy.

- [ ] **Step 4: Verify the API now persists across a restart**

With the stack up, in another terminal:

```bash
curl -sS -X POST localhost:8000/api/v1/orders \
  -H 'content-type: application/json' \
  -d '{"customer_id":"11111111-1111-1111-1111-111111111111",
       "lines":[{"sku":"apple","quantity":3,"unit_amount":"1.50","currency":"EUR"}]}'
```

Note the `id` from the response, then:

```bash
docker compose restart app
curl -sS localhost:8000/api/v1/orders/<the id>
```

Expected: the order comes back after the restart. This is the single observable
difference M1 makes to the running service, and it is worth seeing once by hand.

- [ ] **Step 5: Verify readiness reports the database**

```bash
curl -sS localhost:8000/readyz
```

Expected: a body reporting `database: ok`. Then prove it actually checks something:

```bash
docker compose stop postgres
curl -sS -o /dev/null -w '%{http_code}\n' localhost:8000/readyz   # expect 503
curl -sS -o /dev/null -w '%{http_code}\n' localhost:8000/healthz  # expect 200
docker compose start postgres
```

`/healthz` staying 200 while `/readyz` fails is M0's liveness/readiness split doing
its job: the process is alive and must not be restarted; it just cannot serve yet.
Confirm the 503 body names only an exception type — no host name, no connection
string, no credentials.

- [ ] **Step 6: Verify the migration recipes**

```bash
just migrate-version      # expect: 2
just migrate-down 1
just migrate-version      # expect: 1
just migrate              # back up
just migrate-version      # expect: 2
```

- [ ] **Step 7: Verify `migrate-new` writes to the host**

```bash
just migrate-new add_orders_placed_at
ls migrations/
```

Expected: `000003_add_orders_placed_at.up.sql` and `.down.sql` exist **on the host**,
empty. **Delete both files** — this was a check of the recipe, not a real migration,
and leaving them would break Task 2's gate 3 (empty files) and gate 1 (the snapshot).

```bash
rm migrations/000003_add_orders_placed_at.*.sql
uv run pytest tests/unit/test_migration_files.py
```

- [ ] **Step 8: Tear down and commit**

```bash
docker compose down -v
git add examples/reference-service
git commit -m "feat(compose): add postgresql and one-shot migrations to the stack"
```

---

## Task 7: The integration tier and the adapter's tests

**Files:**
- Create: `examples/reference-service/tests/integration/__init__.py` (empty)
- Create: `examples/reference-service/tests/integration/conftest.py`
- Create: `examples/reference-service/tests/integration/test_order_repository.py`
- Modify: `examples/reference-service/justfile`

**Interfaces:**
- Consumes: Task 2's `migrations/`; Task 4's `build_engine`, `build_sessionmaker`, `PostgresOrderRepository`.
- Produces: the fixtures `postgres_container`, `database_url`, `sessionmaker`, `clean_database`, and the helper `run_migrate(args)`. Tasks 8 and 9 build their gates on all of them.

**The schema under test comes from the migrations, not from the models.** The
containers run the real `migrate/migrate:v4.19.0` against the real SQL files, which
is the whole point: a test database built by `Base.metadata.create_all()` would check
the models against themselves and pass happily while the migrations were broken.

**Import `testcontainers.community.postgres`, not `testcontainers.postgres`.** The
latter is deprecated in testcontainers 4.15 and emits a `DeprecationWarning` on
import. `pyproject.toml` sets `filterwarnings = ["error"]`, so the old path does not
merely warn — it fails collection with an error that names the wrong cause. Verified
while writing this plan.

**Three fixture problems below were found only by actually running everything
against real Docker containers, not by reading the code.** Each is explained where
it's fixed, but the shape is worth stating up front: `pytest_collection_modifyitems`
hooks from every `conftest.py` pytest loads run against the *whole session's*
collected items, not just their own directory's, so an unguarded one marks every
test in the suite `integration` and breaks tier separation entirely; pytest-asyncio's
default event-loop scope is per test function, which corrupts a session-scoped
engine's connection pool across tests; and an `AsyncEngine` that is built but never
disposed leaves `just test-integration` reporting every test passed while still
exiting 1. None of these are addressed by changing `build_engine` or
`PostgresOrderRepository` (Task 4's code, unmodified) — all three are fixed entirely
inside this task's own test fixtures.

**A second, independent review — reading the finished code rather than running
it — found four more problems, all in `conftest.py`, plus a gap in the isolation-level
test.** `run_migrate` could leak a container: only its success path called
`container.stop()`, so a Docker-side exception from `wait()`/`logs()` after
`start()` had already succeeded would skip it. The directory guard compared a
resolved directory against `item.path` left unresolved, which stops matching
behind a symlinked checkout — the exact tier-separation failure the guard exists
to prevent, arriving by a different door. Two of this section's own explanatory
claims needed correcting, not the code: pytest-asyncio *does* expose a way to set
the event-loop scope project-wide (declining it is the right call, but it is a
choice, not an absence of one), and the `pytestmark` rule for future test files
was documented somewhere a future author would not think to look. Separately, the
isolation-level test added for requirement 1 asserted on its own inline copy of
`get()`'s isolation call rather than on `get()` itself, so deleting the real call
from `order_repository.py` would have left it passing — Step 3 below covers the
fix, with a second test added alongside the first rather than a rewrite in place.

- [ ] **Step 1: Write the fixtures**

Create `tests/integration/__init__.py` (empty) and `tests/integration/conftest.py`:

```python
"""Containers for the integration tier.

One PostgreSQL container for the whole session, migrated once with the real
golang-migrate image, on a shared Docker network so the two containers can
find each other by name. Tables are truncated between tests, which is far
cheaper than a container per test and gives the same isolation.

Rule for every test module added to this directory: if it uses the
`sessionmaker` fixture below (or anything built on the same engine), it
must carry its own module-level `pytestmark =
pytest.mark.asyncio(loop_scope="session")`. pytest-asyncio does expose a
project-wide `asyncio_default_test_loop_scope` ini option that would apply
this scope everywhere at once, but pyproject.toml deliberately leaves it at
pytest-asyncio's own default ("function") rather than set it there: a
project-wide change would also alter event-loop behaviour for the async
tests in tests/unit/ and tests/api/, which have no need of it. Two
alternatives that WOULD have been central to just this directory — a
marker added dynamically in `pytest_collection_modifyitems` below, and a
package-level `pytestmark` in this directory's `__init__.py` — were both
tried and confirmed not to work; see `pytest_collection_modifyitems`'s
docstring for the mechanism. A module that forgets the rule does not fail
quietly: it crashes with `RuntimeError: Event loop is closed` on the
second test in that module that opens a session — loud enough to point
back here. See `sessionmaker`'s docstring for the full mechanism this rule
protects against.
"""

from __future__ import annotations

from collections.abc import AsyncIterator, Callable, Iterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from testcontainers.community.postgres import PostgresContainer
from testcontainers.core.container import DockerContainer
from testcontainers.core.network import Network

from reference_service.infrastructure.db.engine import (
    build_engine,
    build_sessionmaker,
)
from reference_service.settings import DatabaseSettings

# Pinned, and pinned to the same versions compose uses. A gate that passes
# against a different PostgreSQL than production runs is not a gate.
POSTGRES_IMAGE = "postgres:16-alpine"
MIGRATE_IMAGE = "migrate/migrate:v4.19.0"

MIGRATIONS_DIR = Path(__file__).resolve().parents[2] / "migrations"

# The alias the database answers to INSIDE the shared network. The migrate
# container cannot use the mapped localhost port — that port belongs to the
# host, not to another container.
DATABASE_ALIAS = "db"
DATABASE_USER = "app"
DATABASE_PASSWORD = "secret"
DATABASE_NAME = "app"

# sslmode is required by golang-migrate against a server with no TLS, and is
# rejected by asyncpg — so it appears on the migrate URL only. See engine.py.
MIGRATE_URL = (
    f"postgres://{DATABASE_USER}:{DATABASE_PASSWORD}"
    f"@{DATABASE_ALIAS}:5432/{DATABASE_NAME}?sslmode=disable"
)

# Spelled out rather than left to inference: the fixture below returns a
# closure, and tests in other files take it as a parameter, so they need a name
# for its type. A suppression naming ANN201 would NOT work here — the ANN
# ruleset is not enabled in ruff.toml, and RUF100 (which is) rejects a
# suppression that names a rule that is not enabled.
MigrateRunner = Callable[[str], tuple[int, str]]


_THIS_DIRECTORY = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark everything in this directory `integration` automatically.

    The marker is what `-m 'not integration'` in pyproject.toml's addopts
    filters out of the default run. Applying it here rather than by hand
    means a new test file cannot forget it and quietly make `just test`
    require Docker.

    The `_THIS_DIRECTORY in Path(item.path).resolve().parents` guard is
    load-bearing, not decorative, in two separate ways. First:
    `pytest_collection_modifyitems` implementations from EVERY conftest.py
    pytest loads are registered as session-wide hooks and all run against
    the FULL, whole-session `items` list once — a local conftest.py does
    not confine its own hook to its own directory. An unconditional `for
    item in items: item.add_marker(...)` here would mark every test in the
    ENTIRE suite `integration`, not just this directory's, which turns
    `-m 'not integration'` into "match nothing": `just test` would exit
    with pytest's NO_TESTS_COLLECTED (5) instead of running the unit and
    api tiers, and `just test-integration` would silently run the whole
    suite rather than just this directory. Confirmed empirically while
    building this file: the unscoped version reproduces both symptoms
    exactly. Second: `item.path` must be resolved before the comparison,
    not compared raw — `_THIS_DIRECTORY` above is already `.resolve()`d,
    and a symlink anywhere in the checkout's path could make an unresolved
    `item.path` fail to appear in its `.parents`, so the guard would stop
    matching and every test here would silently lose the marker — this
    exact bug arriving again, by a different door.

    This hook is deliberately NOT where the event-loop scope described in
    this file's module docstring gets fixed, even though that has the same
    "one place, so no file forgets it" shape as the marker above.
    `sessionmaker` is session-scoped, but pytest-asyncio decides which
    event loop scope a test uses inside ITS OWN `pytest_generate_tests` —
    which runs per test function during collection, before this hook ever
    sees the collected `items` list. A marker added here, via
    `item.add_marker(...)`, is provably too late: confirmed empirically by
    adding `pytest.mark.asyncio(loop_scope="session")` right here and
    checking `pytest --setup-plan`, which still showed
    `_function_scoped_runner` for every test. A package-level `pytestmark`
    in this directory's `__init__.py` was tried too and also made no
    difference. `pytestmark` at the top of a test MODULE is read early
    enough (module import happens before `pytest_generate_tests` fires for
    that module's functions) — which is why the rule lives there instead,
    stated at the top of this file.
    """
    for item in items:
        if _THIS_DIRECTORY in Path(item.path).resolve().parents:
            item.add_marker(pytest.mark.integration)


@pytest.fixture(scope="session")
def docker_network() -> Iterator[Network]:
    with Network() as network:
        yield network


@pytest.fixture(scope="session")
def postgres_container(docker_network: Network) -> Iterator[PostgresContainer]:
    container = (
        PostgresContainer(
            POSTGRES_IMAGE,
            # asyncpg, not the psycopg2 default: get_connection_url() then
            # returns the URL SQLAlchemy's async engine actually needs.
            driver="asyncpg",
            username=DATABASE_USER,
            password=DATABASE_PASSWORD,
            dbname=DATABASE_NAME,
        )
        .with_network(docker_network)
        .with_network_aliases(DATABASE_ALIAS)
    )
    with container:
        yield container


@pytest.fixture(scope="session")
def run_migrate(docker_network: Network) -> MigrateRunner:
    """Return a function running one migrate command to completion.

    Returns (exit code, logs) rather than raising, so the reversibility gate
    can assert on a specific failure instead of only on success.
    """

    def run(args: str) -> tuple[int, str]:
        container = (
            DockerContainer(MIGRATE_IMAGE)
            .with_network(docker_network)
            .with_volume_mapping(str(MIGRATIONS_DIR), "/migrations", "ro")
            .with_command(f"-path=/migrations -database {MIGRATE_URL} {args}")
        )
        container.start()
        # A failing migrate command does not raise here — it returns a
        # non-zero exit code, caught below and returned rather than thrown.
        # What the try/finally guards against is a Docker-side exception
        # from wait()/logs() itself (a lost connection to the daemon, for
        # instance): without it, that would skip stop() and leak the
        # container. The ordinary `migrate up` path is unlikely to hit
        # this, but Task 8's reversibility gate drives this same fixture
        # through `down -all` and back, which is exactly the kind of
        # unusual, longer-running command where a Docker-side error is
        # more likely to surface.
        try:
            raw = container.get_wrapped_container()
            # start() returns as soon as the container is running; this is
            # a one-shot command, so wait for it to exit and read its
            # status.
            exit_code = int(raw.wait()["StatusCode"])
            logs = raw.logs().decode().strip()
        finally:
            container.stop()
        return exit_code, logs

    return run


@pytest.fixture(scope="session")
def migrated_database(
    postgres_container: PostgresContainer,
    run_migrate: MigrateRunner,
) -> PostgresContainer:
    """Apply every migration once, with the same tool production uses."""
    exit_code, logs = run_migrate("up")
    assert exit_code == 0, f"migrate up failed:\n{logs}"
    return postgres_container


@pytest.fixture(scope="session")
def database_url(migrated_database: PostgresContainer) -> str:
    """The asyncpg URL for the migrated database, as seen from the host."""
    return str(migrated_database.get_connection_url())


@pytest_asyncio.fixture(scope="session", loop_scope="session")
async def sessionmaker(
    database_url: str,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    """Build the engine once per session and dispose it once per session.

    An `async` fixture, not a plain one, and pinned to `loop_scope="session"`
    rather than left to `asyncio_default_fixture_loop_scope` (which
    pyproject.toml never sets): every test in this directory shares ONE
    event loop via `pytestmark = pytest.mark.asyncio(loop_scope="session")`
    in each test module (this file's module docstring states that as a
    rule for every file added here; `pytest_collection_modifyitems` below
    explains why it cannot live centrally instead), and this fixture must
    resolve to that SAME loop — matching scope names share the identical
    `_session_scoped_runner` fixture pytest-asyncio creates on demand — so
    the engine's pooled connections are always used, and disposed, on the
    loop that opened them.

    The disposal itself is what this fixture adds over a plain `return`:
    `AsyncEngine.dispose()` closes every pooled connection cleanly. Without
    it, the engine and its still-open asyncpg connections are only ever
    reclaimed by garbage collection, at some later, unpredictable point —
    possibly after the loop that owns them has already closed — and
    asyncpg's own `Connection.__del__` responds to exactly that by raising
    a `ResourceWarning` instead of actually closing anything.
    pyproject.toml's `filterwarnings = ["error"]` then turns that warning
    into a hard error during pytest's shutdown, failing the whole run even
    though every test already passed. Confirmed empirically: before this
    fixture disposed the engine, `just test-integration` reported "8
    passed" and still exited 1, via three `ResourceWarning`s (an asyncpg
    connection, a transport, and its socket) that pytest's
    `unraisableexception` handling turned into errors at
    `pytest_unconfigure`.
    """
    settings = DatabaseSettings(dsn=database_url)  # type: ignore[arg-type]
    engine = build_engine(settings)
    try:
        yield build_sessionmaker(engine)
    finally:
        await engine.dispose()


@pytest.fixture(autouse=True)
def clean_database(migrated_database: PostgresContainer) -> None:
    """Empty the tables before each test.

    TRUNCATE ... CASCADE, not DELETE: it is far faster and it reaches
    order_lines through the foreign key. The schema is left alone, so the
    migrations still run exactly once per session.
    """
    result = migrated_database.exec(
        [
            "psql",
            "-U",
            DATABASE_USER,
            "-d",
            DATABASE_NAME,
            "-c",
            "TRUNCATE TABLE orders CASCADE",
        ]
    )
    assert result.exit_code == 0, result.output.decode()
```

`DatabaseSettings(dsn=database_url)` passes a `str` where a `PostgresDsn` is
declared; Pydantic validates and coerces it, and the `type: ignore` records that
mypy cannot see that. The URL already carries `+asyncpg`, which `async_dsn` leaves
alone — that behaviour has its own unit test in Task 4.

**Why `pytest_collection_modifyitems` needs the `_THIS_DIRECTORY` guard, resolved
on both sides.** A hook with this name, defined in *any* `conftest.py` pytest
loads, is registered session-wide and runs once against the complete,
whole-session `items` list — not scoped to the directory that defined it. An
earlier version of this fixture without the guard (`for item in items:
item.add_marker(pytest.mark.integration)`, no `if`) marked every test in the
entire suite `integration`, confirmed two ways: `uv run pytest --collect-only -q`
(the default `-m 'not integration'` addopts) collected zero tests and exited with
pytest's `NO_TESTS_COLLECTED` (5), because every test now carried the marker `-m
'not integration'` excludes; and `uv run pytest -m integration --collect-only -q`
collected all 137 tests — `tests/api/`, `tests/unit/` and `tests/integration/`
together — instead of just this directory's 9. With the guard, the default run
collects only the unit and api tiers and the `-m integration` run collects only
this directory. A later review caught a second, subtler way the same guard could
fail: `_THIS_DIRECTORY` is already `.resolve()`d, but the guard originally
compared it against the raw, unresolved `item.path` — behind a symlinked
checkout, `item.path` need not appear in `_THIS_DIRECTORY`'s `.parents` even
though it points at the same file, so the guard would silently stop matching and
every test here would silently lose the `integration` marker, which is this
exact tier-separation failure again, by a different door. Confirmed directly:
isolating the two comparisons in Python — `resolved_dir in unresolved_item_path
.parents` versus `resolved_dir in unresolved_item_path.resolve().parents`, both
against the same underlying file reached through a symlink — the first is
`False` and the second `True`. Resolving `item.path` before the comparison
closes that gap.

**Why `sessionmaker` is an `async` fixture pinned to `loop_scope="session"`, and
why every test module in this directory needs `pytestmark = pytest.mark.asyncio
(loop_scope="session")`.** `pyproject.toml` sets `asyncio_mode = "auto"` but never
sets `asyncio_default_test_loop_scope`, so pytest-asyncio 1.4's own default applies:
`"function"` — every async test function gets its own fresh event loop.
`sessionmaker` is session-scoped, and so is the connection pool inside the
`AsyncEngine` it wraps: a connection an earlier test checked back into that pool
stays there, still bound to that test's now-closed loop, and the next test that
checks it out triggers `build_engine`'s `pool_pre_ping` (a deliberate, correct
production setting, not touched here), which tries to ping the connection and raises
`RuntimeError: Event loop is closed` — confirmed directly: 4 of the first 8 tests
failed exactly that way before this fix. Adding
`pytest.mark.asyncio(loop_scope="session")` to each item inside
`pytest_collection_modifyitems` above does **not** work — confirmed by adding it
and checking `pytest --setup-plan`, which still showed a fresh
`_function_scoped_runner` per test — because pytest-asyncio resolves loop scope
inside its own `pytest_generate_tests` hook, which runs per test function during
collection, before `pytest_collection_modifyitems` ever sees the collected items. A
package-level `pytestmark` in this directory's `__init__.py` was tried too and also
made no difference. The only place that is read early enough is a `pytestmark` at
the top of the test **module** itself (module import happens before
`pytest_generate_tests` fires for that module's functions) — see
`test_order_repository.py`'s `pytestmark` in Step 3. This is a rule for every future
file in this directory, not just this one: **any test module added under
`tests/integration/` that touches the `sessionmaker` fixture (or any fixture built
on the same engine) must carry its own `pytestmark =
pytest.mark.asyncio(loop_scope="session")`.**

A first version of this plan claimed there was no way to enforce that rule
centrally. A review corrected the claim rather than the code: pytest-asyncio does
expose `asyncio_default_test_loop_scope` as a project-wide ini option that
would apply `"session"` scope everywhere at once, so a central mechanism does
exist — declining to use it is a choice, not a gap. It is declined here because
setting it project-wide would also change event-loop behaviour for the async
tests in `tests/unit/` and `tests/api/`, which have no need of it; scoping the
change to just this directory is worth the per-file `pytestmark` line. The rule
itself was also moved: it originally lived only inside
`pytest_collection_modifyitems`'s docstring, which nobody adding a new test file
would have reason to open, so it now lives in `conftest.py`'s own module
docstring, at the top of the file, where a new test file's author is more likely
to see it. A module that forgets the rule does not fail quietly — it crashes
with `RuntimeError: Event loop is closed` on the second test in that module that
opens a session, which is loud enough to point back here even without having
read the docstring first.

`sessionmaker` is further pinned to `loop_scope="session"` on the fixture itself
(via `@pytest_asyncio.fixture(scope="session", loop_scope="session")`, not plain
`@pytest.fixture`) so that its `finally: await engine.dispose()` runs on the exact
same event loop the tests used — matching `scope` names share the one
`_session_scoped_runner` pytest-asyncio creates on demand. Without the disposal,
`just test-integration` reported all 8 tests passing and still exited 1: the
engine's pooled asyncpg connections were only ever reclaimed by garbage collection,
which raises `ResourceWarning` instead of closing them, and this project's
`filterwarnings = ["error"]` turns that warning into a hard error during pytest's
shutdown — confirmed directly, via three such warnings (a connection, a transport,
and a socket) surfacing as an `ExceptionGroup` from `pytest_unconfigure`.

**Why `run_migrate`'s `container.stop()` moved into a `finally`.** The original
version called `container.start()`, then `raw.wait()` and `raw.logs()`, then
`container.stop()` in a straight line: if a failing `migrate` command were the
only concern this would be enough, since golang-migrate reports failure as a
non-zero exit code rather than by raising. A review pointed out the real risk is
a *Docker-side* exception from `wait()` or `logs()` themselves — a lost
connection to the daemon, for instance — which this straight-line version would
propagate without ever reaching `container.stop()`, leaking the container. Task
8's reversibility gate drives this same fixture through `down -all` and back,
which is exactly the kind of unusual, longer-running command where a Docker-side
error is more likely to surface than on the ordinary `migrate up` path. Wrapping
`get_wrapped_container()` through `logs()` in `try` and moving `container.stop()`
into `finally` closes that gap.

- [ ] **Step 2: Let the throwaway container credentials past the security linter**

`ruff.toml` selects the `S` (bandit) rules, and `DATABASE_PASSWORD = "secret"` in the
conftest above trips `S105 Possible hardcoded password assigned to`. Verified against
this project's own configuration — without this change, `just lint` fails.

The rule is right in general and wrong here: these credentials belong to a container
that is created and destroyed inside one test session and is reachable from nothing
else. Narrow the exemption to the directory where that is true, in
`[lint.per-file-ignores]`:

```toml
[lint.per-file-ignores]
"tests/*" = ["S101", "B017"]  # assert is how tests assert; B017 is deliberately broad exception
# Throwaway Testcontainers credentials. The container lives for one test
# session, is reachable from nothing outside it, and is destroyed afterwards.
# Scoped to this directory rather than all of tests/ so a real credential
# appearing anywhere else is still caught.
"tests/integration/*" = ["S101", "B017", "S105"]
```

Both lists repeat `S101` and `B017` because per-file-ignores does not merge the two
patterns — the most specific match wins outright, so the narrower entry has to carry
everything the broader one gave it.

- [ ] **Step 3: Write the adapter's integration tests**

Create `tests/integration/test_order_repository.py`:

```python
"""The PostgreSQL adapter against a real database and the real schema."""

from __future__ import annotations

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
```

`test_line_order_is_preserved` does not merely call `save()` then `get()` — an
earlier version that did exactly that passed 10 times out of 10 with
`.order_by(OrderLineRow.line_number)` removed from `get()`, because
`mappers.line_values()` assigns each row's `line_number` via `enumerate()` of the
very tuple `save()` inserts, so insertion order and `line_number` order are
identical by construction for anything reachable through `save()`/`get()` alone; the
query planner's chosen Bitmap Heap Scan then returns rows in that same (matching)
physical order regardless of whether `ORDER BY` is present. The version above
reaches around `save()` and inserts the two rows directly, in the *reverse* of their
`line_number` order — physical/insertion order and logical order now deliberately
disagree, so only an explicit `ORDER BY line_number` produces the correct sequence.
Confirmed both ways: with the real `ORDER BY` in place the test passed 8 times in a
row on its own (5 runs, then 3 more after restoring the file post-RED-check), plus
once more as part of the full `just test-integration` run; with `.order_by
(OrderLineRow.line_number)` temporarily removed from `get()` it failed all 10 times
it was run, deterministically, with `AssertionError: assert ['bread', 'apple'] ==
['apple', 'bread']` — the exact reversed order the rows were physically inserted in.

**Two tests now cover `READ_ISOLATION_LEVEL`, not one, because the first only
covered half of what requirement 1 asked for.**
`test_repeatable_read_is_transmitted_to_postgresql` is the original: it opens its
own session, applies `execution_options={"isolation_level": READ_ISOLATION_LEVEL}`
directly, and asks PostgreSQL itself via `SHOW transaction_isolation` whether the
setting took effect — proving SQLAlchemy and asyncpg genuinely transmit the
option through to the server rather than silently dropping or mistranslating it,
which was the real unknown. A review caught what it does *not* prove: it never
constructs a `PostgresOrderRepository` and never calls `get()` at all, so deleting
the isolation call from `get()` in `order_repository.py` would leave this test
passing regardless — it asserts on its own inline copy of the production code,
not on the production code itself.

`test_get_pins_the_read_transaction_to_repeatable_read` — the name the first test
used to carry, now moved to the one that actually earns it — closes that gap
deterministically, with no timing dependence. A `sqlalchemy.event` listener on
`set_connection_execution_options`, registered on `sessionmaker.kw["bind"]
.sync_engine` (the sync engine underlying the async one — SQLAlchemy's event API
operates on that layer even for an async engine), records every `isolation_level`
any connection this engine hands out is given. `save()` runs first only to create
a row `get()` can find, the recording is cleared immediately afterward (confirmed
empty at that point — `save()` sets no isolation_level of its own), then the real
`get()` runs, and the test asserts the recording equals `[READ_ISOLATION_LEVEL]`
exactly. Verified both ways, mutating `order_repository.py` itself this time, not
the test: with the real isolation call in `get()`, both tests passed together 6
times in a row (3 runs before the RED check, 3 more after restoring); with
`session.connection(execution_options={"isolation_level": READ_ISOLATION_LEVEL})`
temporarily deleted from `get()`, the new test failed 6 times in a row (5 in a
loop, one more with full detail) with `AssertionError: assert [] == ['REPEATABLE
READ']` while the first test kept passing unaffected (`1 failed, 1 passed` each
run) — proof the two tests cover genuinely different things, and that the new
one fails for exactly the
reason it exists.

- [ ] **Step 4: Add the recipes**

Add to `justfile`:

```just
# The container-backed tier. Needs a running Docker daemon; `just test` does not.
test-integration:
    uv run pytest -m integration

# Everything: unit, api and integration.
test-all:
    uv run pytest -m ''
```

`-m ''` clears the `-m 'not integration'` in `addopts` rather than fighting it —
pytest applies the last `-m` it is given.

- [ ] **Step 5: Run the integration tests**

```bash
just test-integration
```

Expected: nine tests pass. The first run pulls `postgres:16-alpine` and
`migrate/migrate:v4.19.0` if they are not cached, so it may take a minute; later
runs start containers in a few seconds.

- [ ] **Step 6: Confirm the tiers really are separate**

```bash
uv run pytest          # must not start any container
```

Expected: the unit and api tests pass in a few seconds and no container appears in
`docker ps`. If this run starts a container, the marker is not being applied and
`just test` has silently become dependent on Docker.

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service
git commit -m "test(integration): add the testcontainers tier and adapter tests"
```

---

## Task 8: Gate 1 (schema snapshot) and gate 2 (reversibility)

**Files:**
- Create: `examples/reference-service/tests/integration/test_schema_gates.py`
- Create: `examples/reference-service/schema.sql` (generated, then committed)
- Modify: `examples/reference-service/justfile`

**Interfaces:**
- Consumes: Task 7's `migrated_database` and `run_migrate` fixtures.
- Produces: `normalise_dump(dump: str) -> str` and `dump_schema(container) -> str`, plus the committed `schema.sql`.

**A trap that would otherwise fail every single run.** PostgreSQL 16.13's `pg_dump`
wraps its output in `\restrict <token>` and `\unrestrict <token>` lines, and **the
token is regenerated on every invocation**. Two dumps of a byte-identical schema
therefore differ. Measured while writing this plan: dumping the same database twice
produced a 12-line diff consisting of nothing but those two lines. Stripping them is
not cosmetic — without it, gate 1 fails permanently and looks like real drift.

- [ ] **Step 1: Write the failing gate tests**

Create `tests/integration/test_schema_gates.py`:

```python
"""Gates 1 and 2 of four: the schema snapshot, and reversibility.

Gate 3 (version collisions) is pure filename inspection and lives in
tests/unit/test_migration_files.py. Gate 4 (model drift) is in
test_schema_drift.py.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

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


def normalise_dump(dump: str) -> str:
    return _DUMP_NONCE.sub("", dump).strip() + "\n"


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
```

- [ ] **Step 2: Run the gates and watch gate 1 fail**

```bash
just test-integration
```

Expected: `test_gate_1_the_committed_schema_matches_the_migrations` fails with
`schema.sql is missing`. The reversibility tests should already pass — they compare
the database against itself.

- [ ] **Step 3: Add the snapshot recipe**

Add to `justfile`:

```just
# Regenerate the committed schema.sql from the migrations. Run this after
# changing any migration, and commit the result — the snapshot is reviewed
# like any other source file.
#
# Reuses the gate's own dump-and-normalise code rather than repeating it in
# shell: a second implementation here would be one more thing to keep in step
# with the pg_dump flags the gate uses.
schema-snapshot:
    UPDATE_SCHEMA_SNAPSHOT=1 uv run pytest -m integration \
        -k test_gate_1_the_committed_schema_matches_the_migrations

# All four schema gates in one command: version collisions from the unit tier,
# then the three that need a database.
gates:
    uv run pytest tests/unit/test_migration_files.py
    uv run pytest -m integration -k "schema_gates or schema_drift"
```

- [ ] **Step 4: Generate the snapshot**

```bash
just schema-snapshot
```

Expected: `schema.sql` appears. Read it. It should contain `CREATE TABLE
public.orders`, `CREATE TABLE public.order_lines`, `CREATE TABLE
public.schema_migrations`, the two primary keys, the foreign key with `ON DELETE
CASCADE`, and the three named check constraints — and **no `\restrict` line**.

- [ ] **Step 5: Run the gates again**

```bash
just test-integration
```

Expected: all four gate tests in this file pass.

- [ ] **Step 6: Prove gate 1 can fail**

Add a throwaway third migration:

```bash
just migrate-new add_a_column_we_will_remove
printf 'ALTER TABLE orders ADD COLUMN scratch TEXT;\n' \
  > migrations/000003_add_a_column_we_will_remove.up.sql
printf 'ALTER TABLE orders DROP COLUMN scratch;\n' \
  > migrations/000003_add_a_column_we_will_remove.down.sql
just test-integration
```

Expected: gate 1 fails, reporting that the migrations no longer produce the
committed `schema.sql`. This is the protection working — a schema change that was
not reviewed as a schema change.

Now confirm the intended path works, then remove it entirely:

```bash
just schema-snapshot        # accept the change
just test-integration       # green again
rm migrations/000003_add_a_column_we_will_remove.*.sql
just schema-snapshot        # back to the real schema
just test-integration
git status --porcelain      # schema.sql must be unchanged from step 4
```

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service
git commit -m "test(migrations): add the schema snapshot and reversibility gates"
```

---

## Task 9: Gate 4 — the model/schema drift gate

**Files:**
- Create: `examples/reference-service/tests/integration/test_schema_drift.py`
- Modify: `examples/reference-service/pyproject.toml` (confirm Task 1's comment is in place)

**Interfaces:**
- Consumes: Task 7's `database_url` fixture; Task 3's `Base`.

**Why Alembic is installed in a project that does not use Alembic.** Adopting
golang-migrate loses one thing Alembic gave away for free: the answer to "you changed
a model and forgot to write the migration". golang-migrate cannot diff models against
a database — it does not know Python exists. So Alembic is kept as a **development
dependency and a comparison engine only**. There is no `alembic/` directory, no
`alembic.ini`, no `alembic_version` table and no Alembic migration anywhere; exactly
one function is used, `alembic.autogenerate.compare_metadata`, and it is used to
*assert an empty difference list* rather than to generate anything. Because that looks
contradictory to anyone reading `pyproject.toml`, the comment added in Task 1 sits
beside the dependency, and the module docstring below repeats it.

**The trap this gate has by construction.** golang-migrate creates its own
`schema_migrations` bookkeeping table. It is genuinely in the database and is
deliberately **not** in `Base.metadata`, so an unfiltered comparison reports it as a
table to remove — one permanent false positive that would either fail the gate for
ever or, worse, get "fixed" by adding a fake model for it. Measured while writing this
plan: unfiltered, exactly one difference (`remove_table schema_migrations`); with the
filter below, zero.

- [ ] **Step 1: Write the failing drift test**

Create `tests/integration/test_schema_drift.py`:

```python
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
    Table("a_table_no_migration_creates", pretend, Column("id", Integer, primary_key=True))

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

    kinds = {difference[0] for difference in differences if isinstance(difference, tuple)}
    assert "add_table" in kinds, (
        f"expected the comparison to demand the missing table; got {differences}"
    )
```

- [ ] **Step 2: Run it**

```bash
just test-integration
```

Expected: both tests pass. If the first reports a `remove_table` difference for
`schema_migrations`, the `include_name` filter is not being applied.

- [ ] **Step 3: Prove the gate catches a real mistake**

Temporarily add a column to `OrderRow` in `infrastructure/db/models.py`, imitating
someone who edited a model and forgot the SQL:

```python
    forgotten: Mapped[str | None] = mapped_column(Text, nullable=True)
```

```bash
just test-integration
```

Expected: `test_gate_4_the_models_match_the_migrated_schema` fails with an
`add_column` difference naming `forgotten`. **Remove the line** and re-run to confirm
green. This is the moment the whole gate justifies Alembic's presence in
`pyproject.toml`.

- [ ] **Step 4: Run all four gates together**

```bash
just gates
```

Expected: gate 3 from the unit tier, then gates 1, 2 and 4 from the integration tier.
All green.

- [ ] **Step 5: Commit**

```bash
git add examples/reference-service
git commit -m "test(migrations): add the model and schema drift gate"
```

---

## Task 10: Translate validation at the use-case boundary

**Files:**
- Create: `examples/reference-service/src/reference_service/services/errors.py`
- Modify: `examples/reference-service/src/reference_service/services/order.py`
- Modify: `examples/reference-service/src/reference_service/api/errors.py` (comment only)
- Test: `examples/reference-service/tests/unit/test_order_service.py`
- Test: `examples/reference-service/tests/api/test_errors.py`

**Interfaces:**
- Produces: `ServiceDefectError` in `services/errors.py`.

**The bug being fixed, in one sentence.** `api/errors.py`'s
`_pydantic_validation_error` catches *every* `pydantic.ValidationError` anywhere in
the request and returns 422 — including one raised because a use case built a domain
object wrongly from a command that was already valid, which is a server defect and
must be a 500. M0 recorded this deliberately and named M1 as its owner, on the
grounds that its use cases were too thin for the boundary to earn its keep. They are
no longer thin: `PlaceOrder` now writes to a database, and "the server told the
client its own request was invalid" is a much worse failure once a write is involved.

**Why a 422 here is not a small mistake.** It tells the caller the fault is theirs.
A well-behaved client will not retry, will surface the error to a user, and the real
defect goes uninvestigated because it never appears as a server error in any
dashboard. A 500 says the opposite, and correctly.

- [ ] **Step 1: Write the failing service test**

Add to `tests/unit/test_order_service.py`:

```python
async def test_a_use_case_defect_is_not_reported_as_client_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A valid command that produces an invalid Order is OUR bug, not theirs.

    Simulated by making total_of return the wrong total, which is exactly
    the shape of the real defect: the command validated, and the use case
    then assembled the aggregate incorrectly. The resulting
    pydantic.ValidationError must NOT escape as a ValidationError, because
    api/errors.py turns those into 422s that blame the caller.
    """
    from decimal import Decimal

    from reference_service.domain.order import Money
    from reference_service.services import order as order_module
    from reference_service.services.errors import ServiceDefectError

    monkeypatch.setattr(
        order_module,
        "total_of",
        lambda lines: Money(amount=Decimal("999.99"), currency="EUR"),
    )

    place_order = PlaceOrder(FakeOrderRepository())
    command = PlaceOrderCommand(
        customer_id=uuid4(),
        lines=[
            PlaceOrderLine(
                sku="apple",
                quantity=1,
                unit_amount=Decimal("1.50"),
                currency="EUR",
            )
        ],
    )

    with pytest.raises(ServiceDefectError):
        await place_order(command)


async def test_a_use_case_defect_does_not_reach_the_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Nothing is written when the aggregate could not be built."""
    from decimal import Decimal

    from reference_service.domain.order import Money
    from reference_service.services import order as order_module
    from reference_service.services.errors import ServiceDefectError

    monkeypatch.setattr(
        order_module,
        "total_of",
        lambda lines: Money(amount=Decimal("999.99"), currency="EUR"),
    )

    repository = FakeOrderRepository()
    place_order = PlaceOrder(repository)
    command = PlaceOrderCommand(
        customer_id=uuid4(),
        lines=[
            PlaceOrderLine(
                sku="apple",
                quantity=1,
                unit_amount=Decimal("1.50"),
                currency="EUR",
            )
        ],
    )

    with pytest.raises(ServiceDefectError):
        await place_order(command)

    assert repository.saved == []
```

Check the file's existing imports cover `pytest`, `uuid4`, `PlaceOrder`,
`PlaceOrderCommand`, `PlaceOrderLine` and `FakeOrderRepository`; add any that are
missing.

- [ ] **Step 2: Run the tests and watch them fail**

```bash
uv run pytest tests/unit/test_order_service.py -v
```

Expected: both fail with `ModuleNotFoundError` for
`reference_service.services.errors`.

- [ ] **Step 3: Add the service error**

Create `services/errors.py`:

```python
"""Errors raised by the service layer itself.

Deliberately NOT a DomainError. A DomainError says a business rule was
broken, which is a statement about the caller's request and maps to a 4xx.
What lives here says this service is defective, which maps to a 5xx. Keeping
them in separate hierarchies is what stops one being mistaken for the other
in api/errors.py.
"""

from __future__ import annotations


class ServiceDefectError(Exception):
    """A use case could not build a valid domain object from a valid command.

    The command passed its own validation, so the caller's input was
    acceptable; the fault is in this service's assembly of the aggregate.
    No handler is registered for this type on purpose — it falls through to
    the catch-all in api/errors.py, which logs the full traceback and
    returns a 500 that describes none of our internals.
    """
```

- [ ] **Step 4: Draw the boundary in the use case**

In `services/order.py`, add the imports:

```python
from pydantic import ValidationError as PydanticValidationError

from reference_service.services.errors import ServiceDefectError
```

Replace the body of `PlaceOrder.__call__` with:

```python
    async def __call__(self, command: PlaceOrderCommand) -> Order:
        # The boundary. Everything below this point works from a command that
        # has ALREADY validated, so any validation failure here means this use
        # case assembled the aggregate wrongly — a server defect. Letting the
        # raw pydantic.ValidationError escape would reach the 422 handler in
        # api/errors.py and blame the caller for our bug.
        try:
            lines = tuple(
                OrderLine(
                    sku=item.sku,
                    quantity=item.quantity,
                    unit_price=Money(amount=item.unit_amount, currency=item.currency),
                )
                for item in command.lines
            )
            order = Order(
                id=OrderId(uuid4()),
                customer_id=CustomerId(command.customer_id),
                lines=lines,
                total=total_of(lines),
            )
        except (PydanticValidationError, ValueError) as exc:
            # ValueError as well as ValidationError: total_of raises a plain
            # ValueError on mixed currencies. PlaceOrderCommand already rejects
            # those, so reaching it here means the command validator and this
            # assembly disagree — again our defect, not the caller's.
            raise ServiceDefectError(
                "failed to build a valid Order from a valid PlaceOrderCommand"
            ) from exc

        # Outside the try: a repository failure is not a validation problem,
        # and wrapping it here would relabel a database outage as a defect in
        # this use case. It propagates to the catch-all handler as itself.
        await self._orders.save(order)
        return order
```

`pydantic.ValidationError` is a subclass of `ValueError`, so the two names in that
`except` overlap. Both are listed anyway: the pair documents that two genuinely
different failures are being caught, and a future reader removing the "redundant"
one would not change behaviour, while removing the other silently would.

- [ ] **Step 5: Run the tests and watch them pass**

```bash
uv run pytest tests/unit/test_order_service.py -v
```

- [ ] **Step 6: Add the api-level test**

Add to `tests/api/test_errors.py`, beside the existing `/deep-validation` tests:

```python
def test_a_service_defect_is_a_500_not_a_422(client: TestClient) -> None:
    """The end-to-end statement of what Task 10 fixed.

    Before this, a ValidationError raised inside a use case reached
    _pydantic_validation_error and became a 422 telling the caller their
    request was invalid. It is now a 500 that says the fault is ours.
    """
    from decimal import Decimal

    from reference_service.domain.order import Money
    from reference_service.services import order as order_module

    with pytest.MonkeyPatch.context() as patch:
        patch.setattr(
            order_module,
            "total_of",
            lambda lines: Money(amount=Decimal("999.99"), currency="EUR"),
        )
        response = client.post(
            "/api/v1/orders",
            json={
                "customer_id": "11111111-1111-1111-1111-111111111111",
                "lines": [
                    {
                        "sku": "apple",
                        "quantity": 1,
                        "unit_amount": "1.50",
                        "currency": "EUR",
                    }
                ],
            },
        )

    assert response.status_code == 500
    # And it still describes none of our internals.
    body = response.json()
    assert body["title"] == "Internal server error"
    assert "detail" not in body or body["detail"] is None
```

The `client` fixture builds its app with `raise_server_exceptions` at its default,
so if this test errors instead of returning 500, add
`TestClient(..., raise_server_exceptions=False)` — check how the existing 500 test in
this file handles it and follow that.

- [ ] **Step 7: Update the comment M0 left behind**

In `api/errors.py`, replace the paragraph beginning `# Known, deliberate
mislabeling — not fixed here:` with:

```python
        # Scope, now that M1's Task 10 has drawn the boundary: this handler
        # sees a PydanticValidationError only when a raw pydantic model
        # rejected input a shallower layer had already accepted — genuinely a
        # client fault, and genuinely a 422. A use case that fails to build a
        # valid domain object from an already-valid command no longer arrives
        # here: services/order.py catches that and raises ServiceDefectError,
        # which falls through to the catch-all below and becomes a 500. See
        # tests/api/test_errors.py's /deep-validation route for the case this
        # handler DOES exist for, and
        # test_a_service_defect_is_a_500_not_a_422 for the case it no longer
        # mislabels.
```

- [ ] **Step 8: Verify everything**

```bash
uv run pytest && uv run mypy && uv run lint-imports
```

Expected: all green. `lint-imports` matters here — `services/errors.py` is new, and
the services layer still may not import api, infrastructure, FastAPI, SQLAlchemy or
asyncpg.

- [ ] **Step 9: Commit**

```bash
git add examples/reference-service
git commit -m "fix(services): report use-case defects as server errors, not 422s"
```

---

## Task 11: Documentation, the spec's own updates, and the final pass

**Files:**
- Modify: `examples/reference-service/README.md`
- Modify: `docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md`
- Modify: `examples/reference-service/justfile`

- [ ] **Step 1: Update the service README**

Under **Requirements**, add PostgreSQL 16 and note that Docker is now needed for the
integration tier as well as for `just up`.

Under **Five-minute start**, state that `just up` now starts PostgreSQL, applies the
migrations and then starts the API, in that order, from one command.

Add a **Database** section:

````markdown
## Database

The schema is owned by [golang-migrate](https://github.com/golang-migrate/migrate),
as plain SQL in `migrations/`, applied by a container. Nothing about applying the
schema needs Python, so the production step is an init container running the small
image built from `Dockerfile.migrations`.

```
just migrate                 apply everything outstanding
just migrate-new NAME        write a new .up.sql / .down.sql pair
just migrate-down 1          roll back one step
just migrate-version         current version, and whether it is dirty
just migrate-force VERSION   clear a dirty flag — read the justfile comment first
just psql                    an interactive session against the local database
```

`schema.sql` is a committed snapshot of the schema those migrations produce. It is
generated, never hand-edited: run `just schema-snapshot` after changing a migration
and commit the result, so every schema change is reviewable as a schema change.

Run the service with no database at all by leaving `APP_DATABASE__DSN` unset — it
falls back to an in-memory repository and still serves.

### Schema governance

Four gates, all runnable with `just gates`:

| Gate | What it proves |
|---|---|
| Version collisions | Migration numbering is sequential, paired and well-formed, so a collision is a git conflict rather than a migration silently skipped in one environment |
| Schema snapshot | The migrations still produce the committed `schema.sql` |
| Reversibility | Every `down.sql` truly reverses its `up.sql` — checked before an incident, not during one |
| Model drift | The SQLAlchemy models still match the real schema, which is what catches a model changed without a migration |

Alembic appears in the development dependencies **only** as the comparison engine
behind the model drift gate. There is no `alembic/` directory and no Alembic
migration; golang-migrate owns the schema.
````

Under **Commands**, add `test-integration`, `test-all`, `gates`, `schema-snapshot`
and the five `migrate-*` recipes.

Under **Configuration**, document `APP_DATABASE__DSN`, `APP_DATABASE__POOL_SIZE` and
`APP_DATABASE__STATEMENT_TIMEOUT_MS`, including the rule that the DSN carries neither
a `+asyncpg` driver suffix nor an `sslmode` parameter, and why.

- [ ] **Step 2: Fold the integration tier into `just check`**

`check` currently runs `lint typecheck imports test precommit`. Leave it as it is,
and add a second command beside it:

```just
# What CI will run at M5, and what to run before opening a pull request that
# touches the schema or the adapter. Separate from `check` so the fast loop
# stays fast and usable without Docker.
check-all: check test-integration gates
```

- [ ] **Step 3: Bring the spec into line with what was built**

Three statements in the spec are now out of date. Update them, and say why in the
commit message — the spec is a living document in this repository, and M0 already
set the precedent of recording implementation findings back into it.

1. **Section 5.1** shows `database: DatabaseSettings` as a required field. It is
   optional (`DatabaseSettings | None = None`) so that a service generated with
   `database=none` keeps a working repository. Update the code block and add a
   sentence saying so.
2. **Section 6.2**'s example layout names `000002_add_orders_status_index.up.sql`.
   The real second migration is `000002_add_order_check_constraints`, because the
   `Order` aggregate has no `status` field and an index on `order_lines.order_id`
   would have been redundant against the composite primary key. Replace the example
   with the real filenames.
3. **Section 6.3** says integration tests "run the real `migrate/migrate` container
   against the Testcontainers PostgreSQL instance". That is exactly what was built —
   add the detail that the two containers share an explicit Docker network and the
   database is reached by network alias, because the host-mapped port is not
   reachable from another container.

Add a short subsection to section 6.5 recording the two traps found while
implementing the gates, so the next person does not rediscover them:

```markdown
Two implementation details that are not optional:

- **`pg_dump` output is not byte-stable.** PostgreSQL 16.13 wraps every dump in
  `\restrict` / `\unrestrict` lines carrying a token regenerated on each run.
  The snapshot gate must strip them before comparing, or it fails on every run.
- **Gate 4 must exclude `schema_migrations`.** golang-migrate's own bookkeeping
  table is in the database and is deliberately not in the SQLAlchemy models, so
  an unfiltered comparison reports one permanent false difference. Gate 1 does
  the opposite and includes it, because the snapshot describes the real database.
```

- [ ] **Step 4: The full verification pass**

Run every check, and read the output rather than the exit code:

```bash
docker compose down -v
uv run ruff check . && uv run ruff format --check .
uv run mypy
uv run lint-imports
uv run pytest                 # unit + api, no containers
just test-integration         # the container tier
just gates                    # all four gates
uvx --from rust-just just check
docker build -f Dockerfile.migrations -t reference-service-migrations:dev .
just up                       # postgres -> migrate -> app, in that order
```

Then confirm the tree is clean, which catches any hook that rewrote a file:

```bash
git status --porcelain
```

- [ ] **Step 5: Commit**

```bash
git add examples/reference-service docs
git commit -m "docs(pyfr): document the persistence layer and its four gates"
```

---

## Definition of done for M1

All of the following must hold before M2 starts.

- [ ] `just check` exits 0 and needs no Docker daemon — the fast loop is still fast.
- [ ] `just check-all` exits 0, adding the integration tier and all four gates.
- [ ] `just up` starts PostgreSQL, applies the migrations, and only then starts the API; a single command yields a working, migrated service.
- [ ] An order placed through the API survives `docker compose restart app`.
- [ ] `/readyz` reports `database: ok`, returns 503 when PostgreSQL is stopped, and leaks no host name, connection string or credential in that 503 body.
- [ ] `/healthz` still returns 200 while PostgreSQL is stopped.
- [ ] With `APP_DATABASE__DSN` unset, the service still starts, serves both order endpoints on the in-memory repository, and registers no database readiness check.
- [ ] `git status --porcelain` is empty after a full run, and `schema.sql` matches what the migrations produce.
- [ ] Each of the four gates has been watched to FAIL once, deliberately, and then restored: an out-of-sequence migration number (gate 3), an unsnapshotted schema change (gate 1), a model column with no migration (gate 4). Gate 2 is exercised by its own round trip.
- [ ] A deliberate `import sqlalchemy` in `domain/` fails `just imports`.
- [ ] `api/` and `services/` contain no import of SQLAlchemy, asyncpg or any session type — the only service-layer change in M1 is Task 10's error boundary.
- [ ] A use-case defect returns 500, not 422.

## Spec sections covered

| Spec section | Task |
|---|---|
| 5.1 settings, database sub-model | 1 |
| 5.2 composition root | 5 |
| 6.1 golang-migrate as the tool | 2 |
| 6.2 layout: migrations, schema.sql, Dockerfile.migrations | 2, 8 |
| 6.3 interfaces: local, compose, production, integration tests | 6, 7 |
| 6.4 no autogeneration; the dirty state; out-of-order versions | 2, 6 |
| 6.5 gate 1 schema snapshot | 8 |
| 6.5 gate 2 reversibility | 8 |
| 6.5 gate 3 version collisions | 2 |
| 6.5 gate 4 model/schema drift | 9 |
| 8.1 integration tests on Testcontainers | 7 |
| 10.5 pre-commit: sqlfluff on migration SQL | 2 |
| D12 golang-migrate owns the schema | 2, 6, 7 |
| D13 SQLAlchemy 2.0 async retained, with a drift gate | 3, 4, 9 |
| M0's deferred use-case validation boundary | 10 |

**Deliberately not in M1**, with the milestone that owns each: OpenTelemetry and
database span instrumentation (M2); the OpenAPI drift gate, Schemathesis and mutmut
(M3); Redis and S3 adapters (M4); `.github/workflows/*` and the runbook plus
`docs/how-to/handle-a-dirty-migration.md` from spec 6.4 (M5, M7); seed data,
`just config-check` and log redaction (M6).
