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
    # `options` parameter carries a freeform "-c key=value" string, so e.g.
    # `?options=-c search_path=sslmode_app` would falsely reject a DSN that
    # never set sslmode at all. Never interpolate `raw` into an error message
    # below: it carries the password, and this ValueError is raised,
    # uncaught, from container startup — straight to stderr and the log
    # aggregator.
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
