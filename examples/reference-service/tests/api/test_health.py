from fastapi.testclient import TestClient

from reference_service import __version__
from reference_service.main import create_app
from reference_service.settings import Settings


def test_healthz_reports_alive_with_the_running_version(client: TestClient) -> None:
    response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok", "version": __version__}


def test_readyz_is_ok_when_there_is_nothing_to_check(client: TestClient) -> None:
    response = client.get("/readyz")

    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_startupz_is_ok_once_the_lifespan_has_run(client: TestClient) -> None:
    assert client.get("/startupz").status_code == 200


def test_healthz_never_checks_a_dependency(settings: Settings) -> None:
    """A database blip must not make Kubernetes restart every pod at once."""
    app = create_app(settings)

    async def failing_check() -> None:
        raise RuntimeError("database is down")

    with TestClient(app) as client:
        app.state.container.readiness.register("database", failing_check)

        assert client.get("/healthz").status_code == 200

        readiness = client.get("/readyz")
        assert readiness.status_code == 503
        assert readiness.json()["checks"]["database"].startswith("error")


def test_a_slow_check_times_out_rather_than_hanging(settings: Settings) -> None:
    import asyncio

    app = create_app(settings)

    async def slow_check() -> None:
        await asyncio.sleep(5)

    with TestClient(app) as client:
        app.state.container.readiness.register("slow", slow_check)

        response = client.get("/readyz")

        assert response.status_code == 503
        assert "timeout" in response.json()["checks"]["slow"]


def test_shutdown_closes_the_container(settings: Settings) -> None:
    app = create_app(settings)

    with TestClient(app):
        assert app.state.container.started is True

    assert app.state.container.started is False
