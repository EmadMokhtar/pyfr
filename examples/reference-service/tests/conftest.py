from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from reference_service.main import create_app
from reference_service.settings import Settings


@pytest.fixture
def settings() -> Settings:
    return Settings(_env_file=None, environment="production")  # type: ignore[call-arg]


@pytest.fixture
def client(settings: Settings) -> Iterator[TestClient]:
    """A client whose context manager runs startup and shutdown."""
    with TestClient(create_app(settings)) as test_client:
        yield test_client
