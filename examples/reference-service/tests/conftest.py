import os
from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from reference_service.main import create_app
from reference_service.settings import Settings


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

    The `monkeypatch` fixture itself is function-scoped only, so a
    session-scoped fixture instantiates `MonkeyPatch` directly instead —
    the documented pattern for using it beyond function scope. `.undo()`
    restores exactly the prior state, whether a given key existed before
    or not.
    """
    mp = pytest.MonkeyPatch()
    for key in [key for key in os.environ if key.startswith("APP_")]:
        mp.delenv(key)
    yield
    mp.undo()


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, environment="production")  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A client whose context manager runs startup and shutdown."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client
