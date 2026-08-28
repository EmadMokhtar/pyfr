import pytest

from reference_service.settings import Settings, load_settings


def test_defaults_are_usable_with_no_environment() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.environment == "local"
    assert settings.service_name == "reference-service"
    assert settings.http_port == 8000
    assert settings.log.level == "info"
    assert settings.log.levels == {}
    assert settings.otel.logs_enabled is False


def test_nested_delimiter_fills_sub_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_LOG__LEVEL", "debug")
    monkeypatch.setenv("APP_OTEL__LOGS_ENABLED", "true")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.log.level == "debug"
    assert settings.otel.logs_enabled is True


def test_per_logger_levels_parse_from_json(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_LOG__LEVELS", '{"botocore":"warning"}')

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.log.levels == {"botocore": "warning"}


def test_settings_are_frozen() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    with pytest.raises(Exception):
        settings.http_port = 9000  # type: ignore[misc, unused-ignore]


def test_load_settings_exits_on_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "not-a-real-environment")

    with pytest.raises(SystemExit) as exc_info:
        load_settings(env_file=None)

    assert exc_info.value.code == 78
