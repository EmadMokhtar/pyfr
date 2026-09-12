import os
from collections.abc import Iterator
from contextlib import contextmanager

import pytest
from fastapi.testclient import TestClient

from {{ cookiecutter.package_name }}.main import create_app
from {{ cookiecutter.package_name }}.settings import Settings


@contextmanager
def no_app_env_vars() -> Iterator[None]:
    """Remove every `APP_*` variable from the process environment for the
    duration of the block, putting back exactly what was there before on
    the way out.

    A plain context manager, not a fixture, because two call sites need
    this guarantee where NO fixture — session-scoped or otherwise — can
    reach them: `tests/contract/test_conformance.py` calls `create_app()`
    at IMPORT time, before pytest has run a single fixture, and
    `tests/unit/test_contract_drift.py`'s `render_openapi()` is also
    called directly by `just openapi` via `python -c`, entirely outside
    pytest. `_no_developer_app_env_vars` below gives every OTHER test this
    same guarantee as a fixture; this is the form usable where a fixture
    cannot run at all.

    `Settings(_env_file=None)` alone is NOT this guarantee, and it is easy
    to assume it is: `_env_file=None` only stops `Settings` reading a
    `.env` FILE. Pydantic-settings' environment-variable source reads
    `os.environ` unconditionally, regardless of that argument. Confirmed
    directly: with `APP_SERVICE_NAME=zzz` set, `Settings(_env_file=None)
    .service_name` is `"zzz"`, not the field's own default
    `"{{ cookiecutter.project_slug }}"` — the exact leak this function exists to close.
    """
    removed = {
        key: os.environ.pop(key) for key in list(os.environ) if key.startswith("APP_")
    }
    try:
        yield
    finally:
        os.environ.update(removed)


@pytest.fixture(autouse=True, scope="session")
def _no_developer_app_env_vars() -> Iterator[None]:
    """Strip `APP_*` from the environment for the whole test session.

    `justfile` sets `dotenv-load := true`, so a developer's own `.env`
    enters the environment of every recipe, including `just test` — and
    `Settings(_env_file=None)` does not protect against that: it only
    stops `Settings` reading a `.env` FILE itself, and does nothing about
    `APP_*` variables already sitting in `os.environ` by the time pytest
    starts. Without this, a "with no environment" test only passes
    because the shipped `.env.example` happens to match every default;
    a developer whose `.env` diverges gets a confusing, unrelated
    failure. Confirmed: running a single such test with a real
    `APP_ENVIRONMENT` set in the process environment fails it.

    Delegates to `no_app_env_vars` above rather than repeating the same
    `os.environ` surgery a second time — see its docstring for why THAT
    version, not a fixture, is what the two contract-tier modules need.
    A session-scoped fixture can hold that plain context manager open for
    the whole session simply by entering it and yielding inside, instead
    of exiting before the first test runs.
    """
    with no_app_env_vars():
        yield


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, environment="production")  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A client whose context manager runs startup and shutdown."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client
