"""`just config-check` prints the configuration. The one thing it must
never print is a secret, and `model_dump` alone does not deliver that
(M6 plan, Verified Fact 7): a URL's password is plain text inside the
dumped string."""

import json
import string

import pytest
from hypothesis import assume, given
from hypothesis import strategies as st

from {{ cookiecutter.package_name }}.config_check import (
    MASK,
    main,
    mask_url_credentials,
    resolved_configuration,
)
from {{ cookiecutter.package_name }}.settings import Settings

_SAFE = string.ascii_letters + string.digits


@given(
    user=st.text(alphabet=_SAFE, min_size=1, max_size=12),
    password=st.text(alphabet=_SAFE, min_size=6, max_size=24),
)
def test_a_url_password_never_reaches_the_output(user: str, password: str) -> None:
    assume(password not in user)
    dsn = f"postgresql://{user}:{password}@db:5432/app"

    masked = mask_url_credentials(dsn)

    assert password not in masked
    assert masked == f"postgresql://{user}:{MASK}@db:5432/app"


def test_a_password_with_an_empty_user_is_masked_too() -> None:
    assert mask_url_credentials("redis://:r3d1s@cache:6379/0") == (
        f"redis://:{MASK}@cache:6379/0"
    )


def test_a_url_without_credentials_is_unchanged() -> None:
    assert mask_url_credentials("http://minio:9000") == "http://minio:9000"


def test_a_plain_string_is_unchanged() -> None:
    assert mask_url_credentials("receipts") == "receipts"


def test_a_malformed_url_is_returned_as_is() -> None:
    assert mask_url_credentials("http://[::1") == "http://[::1"


def test_the_resolved_configuration_masks_every_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE__DSN", "postgresql://app:db-pass@db:5432/app")
    monkeypatch.setenv("APP_CACHE__DSN", "redis://:cache-pass@cache:6379/0")
    monkeypatch.setenv("APP_PAYMENT__BASE_URL", "http://pay")
    monkeypatch.setenv("APP_PAYMENT__API_KEY", "pay-key")
    monkeypatch.setenv("APP_STORAGE__BUCKET", "receipts")
    monkeypatch.setenv("APP_STORAGE__ACCESS_KEY_ID", "access-id")
    monkeypatch.setenv("APP_STORAGE__SECRET_ACCESS_KEY", "storage-secret")
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    rendered = json.dumps(resolved_configuration(settings))

    for secret in ("db-pass", "cache-pass", "pay-key", "access-id", "storage-secret"):
        assert secret not in rendered
    # Everything that is not a secret is still there to read.
    assert '"bucket": "receipts"' in rendered
    assert "@db:5432/app" in rendered


def test_main_prints_one_json_object_and_returns_zero(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(env_file=None) == 0

    printed = json.loads(capsys.readouterr().out)
    assert printed["service_name"] == "{{ cookiecutter.project_slug }}"
    assert printed["log"]["level"] == "info"


def test_main_exits_78_without_echoing_the_bad_value(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The same path the service takes at startup: load_settings exits 78
    and, by include_input=False, never prints the offending value."""
    monkeypatch.setenv("APP_DATABASE__DSN", "mysql://app:sup3rs3cr3t@db/app")

    with pytest.raises(SystemExit) as exc_info:
        main(env_file=None)

    assert exc_info.value.code == 78
    captured = capsys.readouterr()
    assert "sup3rs3cr3t" not in captured.err
    assert "sup3rs3cr3t" not in captured.out
