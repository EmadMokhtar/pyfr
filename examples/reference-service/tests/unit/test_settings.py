from pathlib import Path

import pytest
from pydantic import ValidationError

from reference_service.settings import EXIT_CONFIG_ERROR, Settings, load_settings


def test_defaults_are_usable_with_no_environment() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.environment == "local"
    assert settings.service_name == "reference-service"
    assert settings.http_port == 8000
    assert settings.log.level == "info"
    assert settings.log.levels == {}
    assert settings.otel.logs_enabled is False


def test_nested_delimiter_fills_sub_models(monkeypatch: pytest.MonkeyPatch) -> None:
    """`APP_<model>__<field>` reaches a field inside a sub-model.

    All three OTel variables are set together, not just LOGS_ENABLED. On
    its own that one is now an invalid configuration — OTLP log export
    rides on the providers APP_OTEL__ENABLED builds, so enabling it alone
    silently configures nothing, and OtelSettings rejects it. This test is
    about the `__` delimiter reaching into a sub-model, so it uses a
    combination that is actually valid.
    """
    monkeypatch.setenv("APP_LOG__LEVEL", "debug")
    monkeypatch.setenv("APP_OTEL__ENABLED", "true")
    monkeypatch.setenv("APP_OTEL__ENDPOINT", "http://localhost:4317")
    monkeypatch.setenv("APP_OTEL__LOGS_ENABLED", "true")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.log.level == "debug"
    assert settings.otel.logs_enabled is True
    assert settings.otel.endpoint == "http://localhost:4317"


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


def test_database_is_absent_by_default() -> None:
    """No DSN configured means the in-memory adapter, not a crash.

    A service generated with database=none must keep working, so the
    sub-model is optional rather than required. Task 5 turns this None
    into the choice of adapter.
    """
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database is None


def test_database_settings_are_read_from_a_nested_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(
        "APP_DATABASE__DSN", "postgresql://app:secret@localhost:5432/app"
    )
    monkeypatch.setenv("APP_DATABASE__POOL_SIZE", "3")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.database is not None
    assert str(settings.database.dsn) == "postgresql://app:secret@localhost:5432/app"
    assert settings.database.pool_size == 3
    # Defaults from the spec's section 5.1, not silently zero.
    assert settings.database.statement_timeout_ms == 5_000


def test_database_settings_are_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same reasoning as LogSettings and OtelSettings.

    Settings.model_config's frozen=True governs Settings's own fields only.
    Without its own frozen=True, `settings.database.pool_size = 99` would
    succeed silently while Settings claims to be frozen.
    """
    monkeypatch.setenv(
        "APP_DATABASE__DSN", "postgresql://app:secret@localhost:5432/app"
    )
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.database is not None

    with pytest.raises(ValidationError):
        settings.database.pool_size = 99


def test_a_libpq_only_dsn_parameter_stops_the_process_with_exit_78(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Regression test for a real defect, not a hypothetical one.

    Before this fix, this exact check lived only in
    infrastructure/db/engine.py's async_dsn(), called from inside
    build_engine() during FastAPI's `lifespan` — well after load_settings
    had already returned successfully. Confirmed against the unpatched
    code: load_settings(env_file=None) with this same DSN returned a
    Settings object without raising anything, and the ValueError only
    surfaced later, uncaught, out of container.build_container() — a
    traceback and SystemExit: 3 at actual startup, not the exit 78
    README.md promises for every bad setting. The check now runs as an
    ordinary DatabaseSettings field validator, so it fails at the same
    point and the same way every other bad setting does.
    """
    monkeypatch.setenv(
        "APP_DATABASE__DSN",
        "postgresql://app:secret@localhost:5432/app?sslmode=disable",
    )

    with pytest.raises(SystemExit) as exit_info:
        load_settings(env_file=None)

    assert exit_info.value.code == EXIT_CONFIG_ERROR


def test_a_malformed_dsn_stops_the_process_with_exit_78(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fail fast and loudly, exactly as every other bad setting does."""
    monkeypatch.setenv("APP_DATABASE__DSN", "mysql://app@localhost/app")

    with pytest.raises(SystemExit) as exit_info:
        load_settings(env_file=None)

    assert exit_info.value.code == EXIT_CONFIG_ERROR


def test_a_malformed_dsn_s_password_never_reaches_stderr(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Regression test for a real defect, not a hypothetical one.

    pydantic's default ValidationError rendering (both plain str(exc) and
    the bare exception passed to an f-string) embeds the VALUE that failed
    validation, and for database.dsn that value is the whole connection
    string, credentials included. Confirmed against the unpatched
    load_settings: this exact DSN printed
    `input_value='mysql://app:sup3rs3cr3t@db.internal:3306/app'` to stderr,
    directly contradicting this module's own docstring and spec 5.1's
    promise that a secret cannot reach a log line or a traceback by
    accident.

    The message must still be useful, not merely safe: the field location
    and the constraint name are asserted below too, so a fix that achieved
    silence by discarding the whole message would not pass this either.
    """
    secret = "sup3rs3cr3t"  # noqa: S105 - the value under test, not a real credential
    monkeypatch.setenv(
        "APP_DATABASE__DSN", f"mysql://app:{secret}@db.internal:3306/app"
    )

    with pytest.raises(SystemExit) as exit_info:
        load_settings(env_file=None)

    assert exit_info.value.code == EXIT_CONFIG_ERROR
    stderr = capsys.readouterr().err
    assert secret not in stderr
    assert "db.internal" not in stderr
    # Still useful, not merely silent: names the field and the constraint.
    assert "dsn" in stderr
    assert "url_scheme" in stderr


def test_otel_is_off_by_default() -> None:
    """The M0/M1 no-dependency path must survive M2 untouched."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.otel.enabled is False
    assert settings.otel.logs_enabled is False
    assert settings.otel.endpoint is None
    assert settings.otel.sample_ratio == 1.0


def test_enabling_otel_without_an_endpoint_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Silently dropping every span is worse than refusing to start.

    With no endpoint the SDK still builds, still samples, still batches —
    and then fails to connect on a background thread, where the failure is
    a log line nobody reads rather than a startup error.
    """
    monkeypatch.setenv("APP_OTEL__ENABLED", "true")

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None)  # type: ignore[call-arg]

    assert "APP_OTEL__ENDPOINT" in str(caught.value)


def test_otlp_logs_cannot_be_enabled_on_their_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """logs_enabled rides on the same providers `enabled` builds."""
    monkeypatch.setenv("APP_OTEL__LOGS_ENABLED", "true")

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None)  # type: ignore[call-arg]

    assert "APP_OTEL__ENABLED" in str(caught.value)


@pytest.mark.parametrize("ratio", ["-0.1", "1.1"])
def test_sample_ratio_outside_zero_to_one_is_rejected(
    monkeypatch: pytest.MonkeyPatch, ratio: str
) -> None:
    monkeypatch.setenv("APP_OTEL__ENABLED", "true")
    monkeypatch.setenv("APP_OTEL__ENDPOINT", "http://localhost:4317")
    monkeypatch.setenv("APP_OTEL__SAMPLE_RATIO", ratio)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_payment_is_absent_by_default() -> None:
    """No provider configured means the in-memory gateway, not a crash.

    Same reasoning as `database`: a service with no payment provider set
    anywhere must still start, so the sub-model is optional rather than
    required.
    """
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.payment is None


def test_payment_settings_are_read_from_a_nested_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_PAYMENT__BASE_URL", "http://localhost:9099")
    monkeypatch.setenv("APP_PAYMENT__API_KEY", "sk-test-123")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.payment is not None
    assert str(settings.payment.base_url) == "http://localhost:9099/"
    assert settings.payment.api_key is not None
    assert settings.payment.api_key.get_secret_value() == "sk-test-123"
    # Defaults come from HttpClientSettings and PaymentSettings themselves,
    # not silently zero — nothing above overrode them.
    assert settings.payment.http.connect_timeout_seconds == 2.0
    assert settings.payment.retry_attempts == 3


def test_payment_settings_are_read_from_a_two_level_nested_environment_variable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`.env.example` documents `APP_PAYMENT__HTTP__CONNECT_TIMEOUT_SECONDS`
    as a working example — a variable that reaches through TWO levels of
    nesting (`Settings.payment`, then `PaymentSettings.http`), not one.
    Every other nested-env-var test in this file only exercises one level;
    this one pins the two-level form so the `.env.example` claim is
    actually exercised somewhere rather than merely documented.
    """
    monkeypatch.setenv("APP_PAYMENT__BASE_URL", "http://localhost:9099")
    monkeypatch.setenv("APP_PAYMENT__HTTP__CONNECT_TIMEOUT_SECONDS", "7.5")

    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.payment is not None
    assert settings.payment.http.connect_timeout_seconds == 7.5
    # The sibling fields on the same nested model are untouched.
    assert settings.payment.http.read_timeout_seconds == 5.0


def test_payment_settings_are_frozen(monkeypatch: pytest.MonkeyPatch) -> None:
    """Same reasoning as LogSettings, OtelSettings and DatabaseSettings.

    Settings.model_config's frozen=True governs Settings's own fields only.
    Without its own frozen=True, `settings.payment.retry_attempts = 99`
    would succeed silently while Settings claims to be frozen.
    """
    monkeypatch.setenv("APP_PAYMENT__BASE_URL", "http://localhost:9099")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.payment is not None

    with pytest.raises(ValidationError):
        settings.payment.retry_attempts = 99


def test_http_client_settings_nested_two_levels_deep_are_frozen_too(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The `frozen=True`-is-not-inherited hazard, one level further down.

    `PaymentSettings.model_config`'s own `frozen=True` (needed because
    `Settings`'s frozen=True does not reach `settings.payment`, see
    `test_payment_settings_are_frozen`) does not reach `settings.payment.http`
    either — `HttpClientSettings` needs its own `model_config`, independent
    of both of its parents, for exactly the reason the module docstring
    describes for `LogSettings` and `OtelSettings`.
    """
    monkeypatch.setenv("APP_PAYMENT__BASE_URL", "http://localhost:9099")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]
    assert settings.payment is not None

    with pytest.raises(ValidationError):
        settings.payment.http.connect_timeout_seconds = 99.0


def test_connect_timeout_seconds_must_be_positive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`gt=0`: httpx treats 0 as a valid deadline, not "immediately fail",
    so a boundary of `ge=0` would silently accept a setting that makes
    every outbound call time out at once. It must be strictly positive.
    """
    monkeypatch.setenv("APP_PAYMENT__BASE_URL", "http://localhost:9099")
    monkeypatch.setenv("APP_PAYMENT__HTTP__CONNECT_TIMEOUT_SECONDS", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]


def test_retry_attempts_must_be_at_least_one(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ge=1`: 0 attempts would mean the call is never made at all, which
    is not "no retries" but "no request" — a different setting entirely.
    """
    monkeypatch.setenv("APP_PAYMENT__BASE_URL", "http://localhost:9099")
    monkeypatch.setenv("APP_PAYMENT__RETRY_ATTEMPTS", "0")

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
