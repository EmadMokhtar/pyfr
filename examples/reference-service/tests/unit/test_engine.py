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
