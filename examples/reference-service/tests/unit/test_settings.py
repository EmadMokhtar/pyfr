from pathlib import Path

import pytest
from pydantic import ValidationError

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


def test_nested_settings_are_frozen_too() -> None:
    """`SettingsConfigDict(frozen=True)` on `Settings` is not recursive.

    Without their own `model_config`, `settings.log` and `settings.otel`
    would silently accept reassignment even though `Settings` itself
    claims to be frozen.
    """
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    with pytest.raises(Exception):
        settings.log.level = "debug"  # type: ignore[misc, unused-ignore]

    with pytest.raises(Exception):
        settings.otel.enabled = True  # type: ignore[misc, unused-ignore]


def test_log_levels_dict_contents_remain_mutable_despite_frozen() -> None:
    """The one documented gap: `frozen` protects the field, not the dict.

    `frozen=True` on `LogSettings` refuses REASSIGNING `levels`, but the
    plain `dict` object it already holds is still an ordinary mutable
    dict. This test pins that known, documented limitation so a future
    change either fixes it deliberately or updates the docstring that
    describes it — not both silently drifting apart.
    """
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    settings.log.levels["botocore"] = "warning"

    assert settings.log.levels == {"botocore": "warning"}


def test_load_settings_exits_on_invalid_configuration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_ENVIRONMENT", "not-a-real-environment")

    with pytest.raises(SystemExit) as exc_info:
        load_settings(env_file=None)

    assert exc_info.value.code == 78


def test_load_settings_exits_78_on_an_unknown_log_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test: an unknown level used to pass settings validation
    entirely and only raise `ValueError: Unknown level: 'VERBOSE'` later,
    deep inside `configure_logging` — contradicting the promised exit 78.
    """
    monkeypatch.setenv("APP_LOG__LEVEL", "verbose")

    with pytest.raises(SystemExit) as exc_info:
        load_settings(env_file=None)

    assert exc_info.value.code == 78


def test_load_settings_exits_78_on_an_unknown_per_logger_level(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_LOG__LEVELS", '{"botocore":"verbose"}')

    with pytest.raises(SystemExit) as exc_info:
        load_settings(env_file=None)

    assert exc_info.value.code == 78


def test_extra_forbid_does_not_reject_an_unknown_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The surprising half of `extra="forbid"`.

    It governs keys present in the `.env` FILE only. An unknown
    `APP_SOMETHING_UNKNOWN` set directly in the process environment is
    silently accepted and ignored — not rejected. This is the actual,
    verified behaviour; do not "fix" this test to expect a
    `ValidationError`, there is no setting that closes this half of the
    gap. See `test_extra_forbid_rejects_an_unknown_key_in_the_env_file`
    for the half it does cover.
    """
    monkeypatch.setenv("APP_SOMETHING_UNKNOWN", "x")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.environment == "local"


def test_extra_forbid_rejects_an_unknown_key_in_the_env_file(
    tmp_path: Path,
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("APP_SOMETHING_UNKNOWN=x\n")

    with pytest.raises(ValidationError):
        Settings(_env_file=str(env_file))  # type: ignore[call-arg]


def test_http_port_rejects_a_value_below_the_valid_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_HTTP_PORT", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_http_port_rejects_a_value_above_the_valid_range(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_HTTP_PORT", "65536")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_http_port_accepts_the_boundary_values(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_HTTP_PORT", "1")
    assert Settings(_env_file=None).http_port == 1  # type: ignore[call-arg]

    monkeypatch.setenv("APP_HTTP_PORT", "65535")
    assert Settings(_env_file=None).http_port == 65535  # type: ignore[call-arg]
