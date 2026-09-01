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
from urllib.parse import parse_qs, urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    PostgresDsn,
    ValidationError,
    field_validator,
)
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


# Parameters libpq accepts and asyncpg does not — see the field_validator
# below that rejects them, and infrastructure/db/engine.py's own copy of
# this same tuple, kept as defence in depth once validation moved here.
_LIBPQ_ONLY_DSN_PARAMETERS = ("sslmode", "sslcert", "sslkey", "sslrootcert")


class DatabaseSettings(BaseModel):
    # See LogSettings.model_config for why each sub-model needs its own
    # frozen=True independently of Settings's.
    model_config = ConfigDict(frozen=True)

    # Read by the APPLICATION only. `just up`'s migrate service and every
    # `just migrate-*` recipe carry their OWN hardcoded URL in compose.yaml
    # (see MIGRATE_URL there) and never read this variable — so there is no
    # golang-migrate/SQLAlchemy drift to prevent by way of this setting;
    # that drift is impossible structurally, because golang-migrate never
    # sees this value at all.
    #
    # Stored WITHOUT a driver suffix — `postgresql://`, never
    # `postgresql+asyncpg://` — and WITHOUT an `sslmode` parameter, for two
    # reasons that both still hold on their own: infrastructure/db/engine.py
    # adds the `+asyncpg` suffix itself (an explicitly-supplied driver is
    # left alone, but there is no reason to supply one here), and `sslmode`
    # is a libpq parameter asyncpg does not understand at all — rejected
    # below, by this same model, rather than reaching asyncpg as a raw
    # error at the first connection.
    dsn: PostgresDsn
    # The hard ceiling on concurrent database connections this instance
    # opens. infrastructure/db/engine.py pins SQLAlchemy's own max_overflow
    # to 0, which is what makes this an EXACT number rather than this value
    # plus SQLAlchemy's default overflow of 10 — the distinction matters the
    # moment this figure is used for capacity planning against the
    # database's own max_connections.
    pool_size: int = Field(default=10, ge=1)
    # Applied per connection as PostgreSQL's `statement_timeout`. A query that
    # runs longer is cancelled by the server, so one pathological statement
    # cannot hold a pooled connection open indefinitely.
    statement_timeout_ms: int = Field(default=5_000, ge=0)

    @field_validator("dsn")
    @classmethod
    def _dsn_must_not_carry_libpq_only_parameters(cls, dsn: PostgresDsn) -> PostgresDsn:
        """Fail here, as ordinary settings validation, not three calls later.

        infrastructure/db/engine.py's async_dsn() used to be the only place
        this was checked, and it ran from inside build_engine(), called
        from FastAPI's `lifespan` — well after load_settings had already
        succeeded. A bad value there raised an uncaught ValueError straight
        out of startup: a traceback and `SystemExit: 3`, not the readable,
        exit-78 message load_settings produces for every OTHER bad setting
        (a wrong http_port, an unknown log level, a malformed dsn of any
        other kind). Running the identical check here instead means a
        libpq-only parameter fails exactly like those do: caught by
        load_settings's `except ValidationError`, named by field, exit 78 —
        and README.md's "every bad setting exits 78" claim becomes true
        for this one too.

        Never interpolate `dsn` itself into the message below: like
        engine.py's copy of this check, this runs on a value that may carry
        a password, and this ValueError's text is what load_settings
        eventually renders to stderr.
        """
        query_parameters = parse_qs(urlsplit(str(dsn)).query)
        for parameter in _LIBPQ_ONLY_DSN_PARAMETERS:
            if parameter in query_parameters:
                raise ValueError(
                    f"must not carry the libpq parameter '{parameter}': "
                    f"asyncpg does not understand it. Remove it from the "
                    f"URL — golang-migrate never reads this setting (see "
                    f"the dsn field's own comment); its own URL in "
                    f"compose.yaml adds '?sslmode=disable' itself, on a "
                    f"connection string this application never sees."
                )
        return dsn


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
        # exc.errors(include_input=False), not str(exc) or the bare exc:
        # pydantic's default rendering embeds the VALUE that failed
        # validation for every field, and for database.dsn that value is
        # the connection string with its password in it — verified: a
        # malformed `APP_DATABASE__DSN=mysql://app:sup3rs3cr3t@...` printed
        # `input_value='mysql://app:sup3rs3cr3t@...'` to stderr here, in
        # direct contradiction of this module's own docstring ("a missing
        # or malformed variable stops the process ... with a readable
        # message") and of spec 5.1's promise that a secret cannot reach a
        # log line or a traceback by accident. include_input=False elides
        # it while keeping the field location and the constraint message —
        # confirmed on the installed pydantic (2.13.4) to still identify
        # exactly which setting is wrong and why.
        #
        # Applied globally, not only to database.dsn: every OTHER field
        # loses the courtesy of having its bad value echoed back too, which
        # is a real trade-off — a typo in, say, http_port is now named by
        # field and constraint but not shown verbatim. The alternative, an
        # allowlist of "safe" fields to elide, requires every future
        # secret-bearing setting (a Redis or S3 credential in a later
        # milestone) to remember to join that list before its own first
        # malformed value is safe to print. A blanket rule cannot be
        # forgotten the way a list can.
        sys.stderr.write(f"Invalid configuration:\n{exc.errors(include_input=False)}\n")
        raise SystemExit(EXIT_CONFIG_ERROR) from exc
