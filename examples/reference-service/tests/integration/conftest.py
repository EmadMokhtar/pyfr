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
