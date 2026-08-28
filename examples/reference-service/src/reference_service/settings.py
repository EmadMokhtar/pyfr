"""Application configuration.

Settings are read once at startup and are frozen. A missing or malformed
variable stops the process immediately with a readable message, rather than
producing a 500 response an hour later.
"""

from __future__ import annotations

import sys
from typing import Literal

from pydantic import BaseModel, Field, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# Exit code 78 is EX_CONFIG from sysexits.h: "configuration error".
EXIT_CONFIG_ERROR = 78

# A plain `str` here would let `APP_LOG__LEVEL=verbose` pass settings
# validation and then raise `ValueError: Unknown level: 'VERBOSE'` inside
# `configure_logging` instead — a crash instead of the readable exit-78
# message `load_settings` already produces for every other bad value.
LogLevel = Literal["debug", "info", "warning", "error", "critical"]


class LogSettings(BaseModel):
    level: LogLevel = "info"
    # Per-logger overrides, so silencing a chatty library is configuration
    # rather than a code change. Example: {"sqlalchemy.engine": "warning"}
    # Values are constrained the same way as `level`, for the same reason.
    levels: dict[str, LogLevel] = Field(default_factory=dict)


class OtelSettings(BaseModel):
    enabled: bool = False
    # Standard output is the source of truth for logs. Enabling this in
    # production alongside a platform log agent doubles ingest volume and
    # cost. The local compose profile turns it on; nothing else should.
    logs_enabled: bool = False
    endpoint: str | None = None


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_",
        env_nested_delimiter="__",
        env_file=".env",
        env_file_encoding="utf-8",
        frozen=True,
        # This governs keys present in the `.env` FILE only — an unknown
        # `APP_SOMETHING_UNKNOWN` set directly in the process environment
        # is silently accepted and ignored, not rejected. Verified: passing
        # it via monkeypatch.setenv raises nothing; the same key inside a
        # `.env` file raises `extra_forbidden`. pydantic-settings treats
        # the two sources differently, and there is no setting that closes
        # the environment-variable half of this gap.
        extra="forbid",
    )

    environment: Literal["local", "staging", "production"] = "local"
    service_name: str = "reference-service"
    http_port: int = Field(default=8000, ge=1, le=65535)
    log: LogSettings = Field(default_factory=LogSettings)
    otel: OtelSettings = Field(default_factory=OtelSettings)


def load_settings(env_file: str | None = ".env") -> Settings:
    """Build settings, or stop the process with a readable message."""
    try:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    except ValidationError as exc:
        sys.stderr.write(f"Invalid configuration:\n{exc}\n")
        raise SystemExit(EXIT_CONFIG_ERROR) from exc
