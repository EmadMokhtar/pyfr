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
from typing import Annotated, Literal
from urllib.parse import parse_qs, urlsplit

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    HttpUrl,
    PostgresDsn,
    RedisDsn,
    SecretStr,
    StringConstraints,
    ValidationError,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, SettingsConfigDict

from reference_service.observability.redaction import DEFAULT_REDACT_FIELDS

# Exit code 78 is EX_CONFIG from sysexits.h: "configuration error".
EXIT_CONFIG_ERROR = 78

# A plain `str` here would let `APP_LOG__LEVEL=verbose` pass settings
# validation and then raise `ValueError: Unknown level: 'VERBOSE'` inside
# `configure_logging` instead — a crash instead of the readable exit-78
# message `load_settings` already produces for every other bad value.
LogLevel = Literal["debug", "info", "warning", "error", "critical"]


class LogSettings(BaseModel):
    """Logging. Structured JSON everywhere except a local environment."""

    # frozen=True here, not inherited: Settings.model_config's frozen=True
    # applies only to Settings's own fields, not to the sub-models nested
    # inside it. Without this, `settings.log.level = "debug"` would succeed
    # silently despite Settings claiming to be frozen. See the module
    # docstring for the one gap that remains even so (`levels`, below).
    model_config = ConfigDict(frozen=True)

    level: LogLevel = Field(default="info", description="The root log level.")
    # Still a genuinely mutable dict despite `frozen=True` above: frozen
    # refuses reassigning the `levels` field itself, but not mutating the
    # dict object already held there (`settings.log.levels["x"] = ...`
    # succeeds). See the module docstring.
    levels: dict[str, LogLevel] = Field(
        default_factory=dict,
        description=(
            "Per-logger overrides, as JSON. Silencing a chatty library is "
            "configuration, not a code change."
        ),
    )
    # A frozenset default needs no factory: it is immutable, so sharing one
    # instance between Settings objects is safe.
    redact_fields: frozenset[str] = Field(
        default=DEFAULT_REDACT_FIELDS,
        description=(
            "Field names whose values are replaced by `[REDACTED]` before a "
            "record is rendered, as a JSON array. Matched by exact name at "
            "any depth, ignoring case and treating `-` and `_` alike. Setting "
            "this REPLACES the default list rather than adding to it."
        ),
    )


class OtelSettings(BaseModel):
    """Tracing and metrics. Off by default: nothing starts until `enabled` is true."""

    # See LogSettings.model_config for why this is needed independently of
    # Settings's own frozen=True.
    model_config = ConfigDict(frozen=True)

    enabled: bool = Field(
        default=False,
        description=(
            "Turn on traces and metrics. Off by default: with it off the "
            "process builds no providers, opens no socket and starts no "
            "background task."
        ),
    )
    # Standard output is the source of truth for logs (spec D15). Enabling
    # this in production alongside a platform log agent doubles ingest
    # volume and cost. The local compose profile turns it on; nothing else
    # should.
    logs_enabled: bool = Field(
        default=False,
        description=(
            "Export logs over OTLP **in addition to** standard output. "
            "Requires `APP_OTEL__ENABLED`."
        ),
    )
    endpoint: str | None = Field(
        default=None,
        description=(
            "Where traces and metrics go, over OTLP/gRPC. **Required** when "
            "`APP_OTEL__ENABLED` is true — enabling the SDK with nowhere to "
            "send data stops the process at startup rather than dropping "
            "every span from a background thread."
        ),
    )
    # Parent-based sampling: a request already carrying a sampled parent is
    # always recorded, and this ratio decides only for requests that start
    # here. 1.0 locally so a developer sees the request they just made;
    # lower in production, where recording every span costs real money.
    sample_ratio: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of *new* traces recorded, 0.0 to 1.0. Sampling is "
            "parent-based, so a request arriving with a sampled parent is "
            "always recorded whatever this says."
        ),
    )
    # The SDK default is 60s, which matches the Grafana datasource's own
    # 60s timeInterval: changing this default without updating that
    # dashboard's timeInterval would desynchronise the two.
    metric_export_interval_ms: int = Field(
        default=60_000,
        ge=1_000,
        description=(
            "How often metrics are pushed. `just o11y` lowers it to 10000 "
            "so panels move while you watch."
        ),
    )

    @model_validator(mode="after")
    def _exporting_requires_somewhere_to_export_to(self) -> OtelSettings:
        """Refuse to start rather than drop telemetry on a background thread.

        With `enabled` true and no endpoint the SDK builds happily, samples
        happily, batches happily, and then fails to connect from its own
        exporter thread — where the failure is a log line nobody is reading
        at 3am, and the symptom is "the dashboards are empty" a week later.
        Failing here makes it exit 78 with the variable named, like every
        other bad setting (see load_settings).

        `logs_enabled` is checked against `enabled` rather than against
        `endpoint` because the log exporter shares the providers `enabled`
        builds: on its own it would configure nothing at all, which is the
        same silent-nothing failure in a second costume.
        """
        if self.enabled and not self.endpoint:
            raise ValueError(
                "APP_OTEL__ENABLED is true but APP_OTEL__ENDPOINT is not "
                "set: the SDK would start and then drop every span, metric "
                "and log record from its own exporter thread. Set the "
                "collector endpoint, or set APP_OTEL__ENABLED=false."
            )
        if self.logs_enabled and not self.enabled:
            raise ValueError(
                "APP_OTEL__LOGS_ENABLED is true but APP_OTEL__ENABLED is "
                "false: OTLP log export uses the providers APP_OTEL__ENABLED "
                "builds, so on its own this setting does nothing."
            )
        return self


# Parameters libpq accepts and asyncpg does not — see the field_validator
# below that rejects them, and infrastructure/db/engine.py's own copy of
# this same tuple, kept as defence in depth once validation moved here.
_LIBPQ_ONLY_DSN_PARAMETERS = ("sslmode", "sslcert", "sslkey", "sslrootcert")


class DatabaseSettings(BaseModel):
    """PostgreSQL. Optional: leave the whole block unset to run in-memory."""

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
    dsn: PostgresDsn = Field(
        description=(
            "Where to store orders. **Leave it unset to run with no database "
            "at all** — the service starts on an in-memory repository and "
            "serves normally."
        ),
    )
    # The hard ceiling on concurrent database connections this instance
    # opens. infrastructure/db/engine.py pins SQLAlchemy's own max_overflow
    # to 0, which is what makes this an EXACT number rather than this value
    # plus SQLAlchemy's default overflow of 10 — the distinction matters the
    # moment this figure is used for capacity planning against the
    # database's own max_connections.
    pool_size: int = Field(
        default=10,
        ge=1,
        description=(
            "Connections held open to PostgreSQL. This is a true ceiling: "
            "`max_overflow` is pinned to 0, so an eleventh concurrent "
            "checkout waits rather than opening a further connection, and "
            "gives up after SQLAlchemy's 30-second `pool_timeout`."
        ),
    )
    statement_timeout_ms: int = Field(
        default=5_000,
        ge=0,
        description=(
            "Applied by the server per connection. A statement running "
            "longer is cancelled, so one pathological query cannot hold a "
            "pooled connection indefinitely."
        ),
    )

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


class HttpClientSettings(BaseModel):
    """The outbound HTTP client used to call the payment gateway."""

    # See LogSettings.model_config for why each sub-model needs its own
    # frozen=True rather than inheriting it.
    model_config = ConfigDict(frozen=True)

    # Four phases, four separate deadlines, none of them optional. httpx
    # accepts None for "wait forever" on any of them, and a client built
    # that way is indistinguishable from a working one until the day the
    # dependency stops answering.
    connect_timeout_seconds: float = Field(
        default=2.0,
        gt=0,
        description="How long to wait for the TCP/TLS handshake.",
    )
    read_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        description=(
            "How long to wait for a response once the request is sent. "
            "Never retried on expiry — see [Outbound HTTP calls]"
            "(../guides/outbound-http.md#the-retry-rule-and-why-it-is-narrow)."
        ),
    )
    write_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        description="How long to wait while sending the request body.",
    )
    # How long a request may wait for a free connection from the pool. It
    # is the one people forget: with the pool exhausted, requests queue
    # here rather than at the socket, and an unbounded wait turns a slow
    # dependency into a stalled service just as effectively.
    pool_timeout_seconds: float = Field(
        default=1.0,
        gt=0,
        description=(
            "How long to wait for a free connection from this client's own "
            "pool, before any socket to the gateway opens."
        ),
    )

    max_connections: int = Field(
        default=20,
        ge=1,
        description="The connection pool's ceiling.",
    )
    max_keepalive_connections: int = Field(
        default=10,
        ge=0,
        description="Idle connections kept open for reuse.",
    )


class PaymentSettings(BaseModel):
    """The payment gateway. Optional: leave unset for the in-memory gateway."""

    model_config = ConfigDict(frozen=True)

    base_url: HttpUrl = Field(
        description=(
            "The payment provider's base URL. **Leave it unset to run on "
            "the in-memory gateway, which authorises everything.** "
            "`just up` points it at a local stub."
        ),
    )
    api_key: SecretStr | None = Field(
        default=None,
        description=(
            "Sent as a bearer token. `SecretStr`, so it cannot reach a log "
            "line or a traceback by accident — it always prints as a row "
            "of asterisks, never the real value."
        ),
    )
    http: HttpClientSettings = Field(default_factory=HttpClientSettings)

    retry_attempts: int = Field(
        default=3,
        ge=1,
        description="Attempts, not retries: `3` means one call and two further tries.",
    )
    retry_initial_wait_seconds: float = Field(
        default=0.1,
        gt=0,
        description="Wait before the first retry. Backs off from here.",
    )
    retry_max_wait_seconds: float = Field(
        default=2.0,
        gt=0,
        description=(
            "The backoff's ceiling *before* jitter. `stamina` adds up to a "
            "further second of random jitter on top (`wait_jitter`, fixed, "
            "not configured by this variable), and the whole retry loop "
            "separately stops at a fixed 45-second wall-clock budget "
            "regardless of this value — see the payment gateway's "
            "`infrastructure/http/payment_gateway.py`."
        ),
    )

    breaker_failure_threshold: int = Field(
        default=5,
        ge=1,
        description="Consecutive failures before the circuit opens.",
    )
    breaker_reset_after_seconds: float = Field(
        default=30.0,
        gt=0,
        description="How long the circuit stays open before admitting one probe.",
    )


class CacheSettings(BaseModel):
    """Redis. Optional: leave the whole block unset to run with no cache."""

    # See LogSettings.model_config for why each sub-model needs its own
    # frozen=True rather than inheriting Settings's.
    model_config = ConfigDict(frozen=True)

    dsn: RedisDsn = Field(
        description=(
            "Where the order cache lives. **Leave it unset to run with no "
            "cache at all** — the service reads and writes the order "
            "repository directly. See "
            "[`CachedOrderRepository`]"
            "(../explanation/layers.md#what-a-port-buys-the-caching-decorator)."
        ),
    )
    # How long a cached order stays valid. Five minutes is short enough that
    # a cache that somehow misses an invalidation self-corrects quickly, and
    # long enough to be worth having. The TTL is a safety net, not the
    # primary invalidation mechanism — CachedOrderRepository.save() deletes
    # the key outright.
    ttl_seconds: int = Field(
        default=300,
        ge=1,
        description=(
            "How long a cached order stays valid. A safety net, not the "
            "primary invalidation path — saving an order deletes its cache "
            "entry outright; the TTL only bounds how stale a value can get "
            "if that delete itself fails."
        ),
    )
    pool_size: int = Field(
        default=10,
        ge=1,
        description="Connections held open to Redis.",
    )
    # Both deadlines are deliberately sub-second, and both are required.
    #
    # This is the single most important pair of numbers in the cache. The
    # cache exists to make reads faster; a slow Redis that is not bounded
    # makes every read SLOWER than having no cache at all, because each
    # request pays the full Redis stall and then still queries PostgreSQL.
    # redis-py accepts None for "wait forever" on both, and a client built
    # that way is indistinguishable from a working one until the day Redis
    # starts swapping. gt=0 because 0 means "no deadline" to redis-py, not
    # "give up immediately".
    connect_timeout_seconds: float = Field(
        default=0.5,
        gt=0,
        description=(
            "How long to wait for the connection to Redis. Deliberately "
            "sub-second: a cache that can stall a request for longer than "
            "the database query it is trying to avoid has made the service "
            'slower than having no cache. `redis-py` treats `0` as "wait '
            'forever", not "give up immediately", which is why this is '
            "`> 0` rather than `≥ 0`."
        ),
    )
    operation_timeout_seconds: float = Field(
        default=0.5,
        gt=0,
        description=(
            "How long to wait for a single Redis command. Same reasoning as "
            "the connect timeout, and the same `redis-py` `0`-means-forever "
            "trap."
        ),
    )


# Amazon's bucket naming rules, the subset that is a pure string check:
# 3-63 characters, lowercase letters, digits, hyphens and dots, starting
# and ending alphanumeric. Deliberately not the full rule set — the
# IP-address-shaped and `xn--`-prefixed exclusions need more than a regex
# and their absence costs nothing here, because the provider rejects those
# too and this check exists to catch the ORDINARY mistake (a capital
# letter, an underscore, a trailing slash) at startup rather than on the
# first request.
_BUCKET_NAME_PATTERN = r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$"


class StorageSettings(BaseModel):
    """S3-compatible object storage. Optional: leave unset for no storage."""

    model_config = ConfigDict(frozen=True)

    bucket: Annotated[str, StringConstraints(pattern=_BUCKET_NAME_PATTERN)] = Field(
        json_schema_extra={"type_label": "string, 3–63 chars"},
        description=(
            "The S3 bucket receipts are stored in. Checked against Amazon's "
            "naming rule (lowercase, digits, hyphens, dots) at startup, so a "
            "typo like a capital letter fails as exit 78, not as the first "
            "failed `PutObject`."
        ),
    )
    # None means real Amazon S3, where botocore derives the endpoint from
    # the region. Anything else — MinIO, Cloudflare R2, Ceph — sets it.
    # This one field is the whole of "one adapter for every S3-compatible
    # provider" (spec 9.1): there is no provider branch anywhere below it.
    endpoint_url: HttpUrl | None = Field(
        default=None,
        description=(
            "**Leave it unset for real Amazon S3** — botocore derives the "
            "endpoint from the region on its own. **Set it for everything "
            "else** — MinIO, Cloudflare R2, Ceph, or any other "
            'S3-compatible provider. This one field is the whole of "one '
            'adapter for every provider": there is no provider branch '
            "anywhere in `S3ReceiptStore`."
        ),
    )
    region: str = Field(
        default="us-east-1",
        description=(
            "Required by botocore's request signing even against a "
            "provider, like MinIO, that ignores it. `us-east-1` is the "
            "conventional filler value."
        ),
    )
    # SecretStr for the same reason PaymentSettings.api_key is: repr is
    # "**********", so a traceback frame or a careless f-string cannot
    # publish it.
    access_key_id: SecretStr = Field(
        description=(
            "`SecretStr`, so it cannot reach a log line or a traceback by accident."
        ),
    )
    secret_access_key: SecretStr = Field(
        description="`SecretStr`, same reasoning.",
    )
    connect_timeout_seconds: float = Field(
        default=2.0,
        gt=0,
        description="How long to wait for the connection to the storage endpoint.",
    )
    read_timeout_seconds: float = Field(
        default=5.0,
        gt=0,
        description="How long to wait for a response once the request is sent.",
    )


class Settings(BaseSettings):
    """Every environment variable this service reads, prefixed `APP_`."""

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

    environment: Literal["local", "staging", "production"] = Field(
        default="local",
        description=(
            "`local` prints colourised, human-readable logs. Anything else "
            "prints one JSON object per line."
        ),
    )
    service_name: str = Field(
        default="reference-service",
        description=(
            "The OpenAPI document's title, and the `service.name` field on "
            "every log record."
        ),
    )
    http_port: int = Field(
        default=8000,
        ge=1,
        le=65535,
        description=(
            "The port to serve on. Read by `just dev`, by the container's "
            "start command, and by the image's health check."
        ),
    )
    log: LogSettings = Field(default_factory=LogSettings)
    otel: OtelSettings = Field(default_factory=OtelSettings)
    # Optional on purpose: None selects the in-memory adapter, which is the
    # path a service generated with database=none takes. See container.py.
    database: DatabaseSettings | None = None
    # Optional on purpose: None selects the in-memory gateway, which is
    # what keeps `just dev` working with no payment provider anywhere —
    # the same arrangement `database` above has with the in-memory
    # repository.
    payment: PaymentSettings | None = None
    # Optional on purpose: None selects the plain repository with no cache
    # in front of it, exactly as `database` None selects the in-memory one.
    # A service generated with cache=none takes this path. See container.py.
    cache: CacheSettings | None = None
    # Optional on purpose: None selects InMemoryReceiptStore, so the receipt
    # endpoint works with no object store anywhere — the same arrangement
    # `payment` has with the in-memory gateway.
    storage: StorageSettings | None = None


def load_settings(env_file: str | None = ".env") -> Settings:
    """Build settings, or stop the process with a readable message."""
    try:
        return Settings(_env_file=env_file)  # type: ignore[call-arg]
    except ValidationError as exc:
        # exc.errors(include_input=False), not str(exc) or the bare exc:
        # pydantic's default rendering embeds the VALUE that failed
        # validation for every field, and for a DSN field that value is
        # the connection string with its password in it — verified: a
        # malformed DSN `mysql://app:sup3rs3cr3t@...` printed
        # `input_value='mysql://app:sup3rs3cr3t@...'` to stderr here, in
        # direct contradiction of this module's own docstring ("a missing
        # or malformed variable stops the process ... with a readable
        # message") and of spec 5.1's promise that a secret cannot reach a
        # log line or a traceback by accident. include_input=False elides
        # it while keeping the field location and the constraint message —
        # confirmed on the installed pydantic (2.13.4) to still identify
        # exactly which setting is wrong and why.
        #
        # Applied globally, not only to DSN fields: every OTHER field
        # loses the courtesy of having its bad value echoed back too, which
        # is a real trade-off — a typo in, say, http_port is now named by
        # field and constraint but not shown verbatim. The alternative, an
        # allowlist of "safe" fields to elide, requires every future
        # secret-bearing setting (a Redis or S3 credential in a later
        # milestone) to remember to join that list before its own first
        # malformed value is safe to print. A blanket rule cannot be
        # forgotten the way a list can.
        # One line per problem rather than the raw repr of a list of dicts:
        # the module docstring promises a READABLE message, and eliding the
        # input must not be paid for in legibility. loc/msg/type are the three
        # fields that say which setting, what is wrong, and which rule
        # rejected it; `ctx` is deliberately left out because it can carry the
        # offending value, which is the whole thing this elision exists to
        # keep out of the log. JSON was the other candidate and would also be
        # structured, but nobody reading a startup failure in a terminal wants
        # to parse braces to find the field name.
        details = "\n".join(
            f"  {'.'.join(str(part) for part in error['loc']) or '<root>'}: "
            f"{error['msg']} ({error['type']})"
            for error in exc.errors(include_input=False)
        )
        sys.stderr.write(f"Invalid configuration:\n{details}\n")
        raise SystemExit(EXIT_CONFIG_ERROR) from exc
