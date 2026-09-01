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

# Parameters libpq accepts and asyncpg does not. golang-migrate's own
# hardcoded URL in compose.yaml wants `?sslmode=disable` against a local
# database with no TLS, so a developer who copies that same URL into
# APP_DATABASE__DSN hits this.
#
# Duplicated, deliberately, with settings.py's DatabaseSettings field
# validator of the same name — that one is now the check that actually
# runs first, as part of ordinary pydantic validation, which is what makes
# a bad value exit 78 with a readable message like every other
# misconfiguration (a bad value used to raise this as an uncaught
# ValueError from inside FastAPI's lifespan instead: a traceback and
# SystemExit: 3, not the exit 78 README.md documents for every other bad
# setting). This copy stays as defence in depth for any caller that builds
# an engine from a DatabaseSettings assembled some other way than through
# Settings/load_settings — a script, a future test — and so never ran
# that validator: rejecting it here, at startup, with the setting named,
# still beats a TypeError from inside asyncpg at the first request.
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
        # SQLAlchemy's own default max_overflow is 10, which would make the
        # real connection ceiling pool_size + 10 rather than pool_size —
        # a gap invisible to anyone reading "connection pool size" in the
        # README and copying pool_size into capacity planning against the
        # database's own max_connections. Pinning it to 0 makes pool_size a
        # true, exact ceiling: what the setting says is what the database
        # sees, per replica. A team that deliberately wants burst capacity
        # can still request it — but only by raising pool_size itself, not
        # by inheriting a default nobody chose.
        max_overflow=0,
        # Checking a connection out of the pool verifies it first, so a
        # connection killed by a database restart or an idle-timeout proxy is
        # replaced rather than handed to a request that then fails.
        pool_pre_ping=True,
        # A DBAPIError's default __str__ includes the full bound parameters
        # of the statement that failed — for this schema, that includes
        # internal_note and customer_id, and the catch-all handler in
        # api/errors.py logs that full traceback. hide_parameters replaces
        # the values with a placeholder in that message while leaving the
        # SQL statement itself (which carries no data) intact; the same
        # care container.py's readiness check already takes to keep
        # connection details out of a response, applied here to keep row
        # data out of a log line instead.
        #
        # NOT a complete guarantee: verified directly that a CHECK
        # constraint violation still puts the full failing row — internal_
        # note and customer_id included — into PostgreSQL's own error
        # DETAIL text, which asyncpg surfaces regardless of this setting.
        # hide_parameters controls SQLAlchemy's client-side echo of the
        # parameters IT sent; it has no reach into content the SERVER
        # decided to put in its own error response. That gap still reaches
        # only logs, never an HTTP response — _unexpected_error never
        # serialises exc — so it is narrower than the one this setting
        # closes, but it is not nothing.
        hide_parameters=True,
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
