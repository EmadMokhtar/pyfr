"""Application configuration.

Settings are read once at startup and are frozen. A missing or malformed
variable stops the process immediately with a readable message, rather than
producing a 500 response an hour later.

"Frozen" is precise, not a slogan: `SettingsConfigDict(frozen=True)` on
`Settings` is NOT recursive — it only refuses reassigning `Settings`'s own
top-level fields (`settings.http_port = 9000` raises). Without their own
`model_config`, `settings.log` and `settings.otel` would still allow
`settings.log.level = "debug"` to succeed silently. `LogSettings` and
`OtelSettings` below each carry `frozen=True` for exactly this reason.

One gap remains even with both frozen: `LogSettings.levels` is a plain
`dict`. `frozen=True` refuses REASSIGNING the `levels` field itself
(`settings.log.levels = {...}` raises), but the dict object it already
holds stays an ordinary mutable dict — `settings.log.levels["x"] = "debug"`
succeeds. Nothing in this codebase mutates it, so this is not a live bug,
but a docstring claiming settings are simply "frozen" without this caveat
would be claiming more than the code delivers.
"""

from __future__ import annotations

import sys
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, PostgresDsn, ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

# Exit code 78 is EX_CONFIG from sysexits.h: "configuration error".
EXIT_CONFIG_ERROR = 78

# A plain `str` here would let `APP_LOG__LEVEL=verbose` pass settings
# validation and then raise `ValueError: Unknown level: 'VERBOSE'` inside
# `configure_logging` instead — a crash instead of the readable exit-78
# message `load_settings` already produces for every other bad value.
LogLevel = Literal["debug", "info", "warning", "error", "critical"]


class LogSettings(BaseModel):
    # frozen=True here, not inherited: Settings.model_config's frozen=True
    # applies only to Settings's own fields, not to the sub-models nested
    # inside it. Without this, `settings.log.level = "debug"` would succeed
    # silently despite Settings claiming to be frozen. See the module
    # docstring for the one gap that remains even so (`levels`, below).
    model_config = ConfigDict(frozen=True)

    level: LogLevel = "info"
    # Per-logger overrides, so silencing a chatty library is configuration
    # rather than a code change. Example: {"sqlalchemy.engine": "warning"}
    # Values are constrained the same way as `level`, for the same reason.
    #
    # Still a genuinely mutable dict despite `frozen=True` above: frozen
    # refuses reassigning the `levels` field itself, but not mutating the
    # dict object already held there (`settings.log.levels["x"] = ...`
    # succeeds). See the module docstring.
    levels: dict[str, LogLevel] = Field(default_factory=dict)


class OtelSettings(BaseModel):
    # See LogSettings.model_config for why this is needed independently of
    # Settings's own frozen=True.
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    # Standard output is the source of truth for logs. Enabling this in
    # production alongside a platform log agent doubles ingest volume and
    # cost. The local compose profile turns it on; nothing else should.
    logs_enabled: bool = False
    endpoint: str | None = None


class DatabaseSettings(BaseModel):
    # See LogSettings.model_config for why each sub-model needs its own
    # frozen=True independently of Settings's.
    model_config = ConfigDict(frozen=True)

    # Stored WITHOUT a driver suffix — `postgresql://`, never
    # `postgresql+asyncpg://`. One setting has to satisfy two tools that
    # disagree about the URL: golang-migrate registers the driver names
    # `postgres` and `postgresql` and uses this string verbatim, while
    # SQLAlchemy needs the `+asyncpg` suffix to pick its driver. Storing the
    # plain form and letting infrastructure/db/engine.py add the suffix keeps
    # ONE variable in the environment. Storing two would let them drift, and
    # a service pointing its migrations at one database and its queries at
    # another fails in a way that takes hours to see.
    dsn: PostgresDsn
    pool_size: int = Field(default=10, ge=1)
    # Applied per connection as PostgreSQL's `statement_timeout`. A query that
    # runs longer is cancelled by the server, so one pathological statement
    # cannot hold a pooled connection open indefinitely.
    statement_timeout_ms: int = Field(default=5_000, ge=0)


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
    # Optional on purpose: None selects the in-memory adapter, which is the
    # path a service generated with database=none takes. See container.py.
    database: DatabaseSettings | None = None


def load_settings(env_file: str | None = ".env") -> Settings:
    """Build settings, or stop the process with a readable message."""
    try:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    except ValidationError as exc:
        sys.stderr.write(f"Invalid configuration:\n{exc}\n")
        raise SystemExit(EXIT_CONFIG_ERROR) from exc
