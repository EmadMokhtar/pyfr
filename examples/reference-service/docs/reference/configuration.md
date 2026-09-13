---
last_reviewed: 2026-09-10
covers:
  - src/reference_service/settings.py
---

# Configuration

Configuration comes from environment variables. Every variable is prefixed
`APP_`, and nested settings use a double underscore: `APP_LOG__LEVEL` fills
`settings.log.level`. One flat environment therefore produces a structured
object.

For local work, copy the example file and edit it:

```bash
cp .env.example .env
```

`.env` is never committed. `.env.example` is the documented default.

## Variables

This table is generated from the settings model. To change a description,
edit `Field(description=...)` in
`examples/reference-service/src/reference_service/settings.py` and run
`just config-docs`.

<!-- generated: config-table. Run `just config-docs`. -->

| Variable | Type | Default | Meaning |
| --- | --- | --- | --- |
| `APP_ENVIRONMENT` | `local` \| `staging` \| `production` | `local` | `local` prints colourised, human-readable logs. Anything else prints one JSON object per line. |
| `APP_SERVICE_NAME` | string | `reference-service` | The OpenAPI document's title, and the `service.name` field on every log record. |
| `APP_HTTP_PORT` | integer, 1–65535 | `8000` | The port to serve on. Read by `just dev`, by the container's start command, and by the image's health check. |
| `APP_LOG__LEVEL` | `debug` \| `info` \| `warning` \| `error` \| `critical` | `info` | The root log level. |
| `APP_LOG__LEVELS` | JSON object | `{}` | Per-logger overrides, as JSON. Silencing a chatty library is configuration, not a code change. |
| `APP_LOG__REDACT_FIELDS` | JSON array | `["access_token","api_key","apikey","authorization","card_number","cookie","cvv","passwd","password","refresh_token","secret","secret_access_key","secret_key","set_cookie","token"]` | Field names whose values are replaced by `[REDACTED]` before a record is rendered, as a JSON array. Matched by exact name at any depth, ignoring case and treating `-` and `_` alike. Setting this REPLACES the default list rather than adding to it. |
| `APP_OTEL__ENABLED` | boolean | `false` | Turn on traces and metrics. Off by default: with it off the process builds no providers, opens no socket and starts no background task. |
| `APP_OTEL__LOGS_ENABLED` | boolean | `false` | Export logs over OTLP **in addition to** standard output. Requires `APP_OTEL__ENABLED`. |
| `APP_OTEL__ENDPOINT` | string | unset | Where traces and metrics go, over OTLP/gRPC. **Required** when `APP_OTEL__ENABLED` is true — enabling the SDK with nowhere to send data stops the process at startup rather than dropping every span from a background thread. |
| `APP_OTEL__SAMPLE_RATIO` | float, 0.0–1.0 | `1.0` | Fraction of *new* traces recorded, 0.0 to 1.0. Sampling is parent-based, so a request arriving with a sampled parent is always recorded whatever this says. |
| `APP_OTEL__METRIC_EXPORT_INTERVAL_MS` | integer, ≥ 1000 | `60000` | How often metrics are pushed. `just o11y` lowers it to 10000 so panels move while you watch. |
| `APP_DATABASE__DSN` | PostgreSQL URL | unset, required once any `APP_DATABASE__*` is set | Where to store orders. **Leave it unset to run with no database at all** — the service starts on an in-memory repository and serves normally. |
| `APP_DATABASE__POOL_SIZE` | integer, ≥ 1 | `10` | Connections held open to PostgreSQL. This is a true ceiling: `max_overflow` is pinned to 0, so an eleventh concurrent checkout waits rather than opening a further connection, and gives up after SQLAlchemy's 30-second `pool_timeout`. |
| `APP_DATABASE__STATEMENT_TIMEOUT_MS` | integer, ≥ 0 | `5000` | Applied by the server per connection. A statement running longer is cancelled, so one pathological query cannot hold a pooled connection indefinitely. |
| `APP_PAYMENT__BASE_URL` | URL | unset, required once any `APP_PAYMENT__*` is set | The payment provider's base URL. **Leave it unset to run on the in-memory gateway, which authorises everything.** `just up` points it at a local stub. |
| `APP_PAYMENT__API_KEY` | secret | unset | Sent as a bearer token. `SecretStr`, so it cannot reach a log line or a traceback by accident — it always prints as a row of asterisks, never the real value. |
| `APP_PAYMENT__RETRY_ATTEMPTS` | integer, ≥ 1 | `3` | Attempts, not retries: `3` means one call and two further tries. |
| `APP_PAYMENT__RETRY_INITIAL_WAIT_SECONDS` | float, > 0 | `0.1` | Wait before the first retry. Backs off from here. |
| `APP_PAYMENT__RETRY_MAX_WAIT_SECONDS` | float, > 0 | `2.0` | The backoff's ceiling *before* jitter. `stamina` adds up to a further second of random jitter on top (`wait_jitter`, fixed, not configured by this variable), and the whole retry loop separately stops at a fixed 45-second wall-clock budget regardless of this value — see the payment gateway's `infrastructure/http/payment_gateway.py`. |
| `APP_PAYMENT__BREAKER_FAILURE_THRESHOLD` | integer, ≥ 1 | `5` | Consecutive failures before the circuit opens. |
| `APP_PAYMENT__BREAKER_RESET_AFTER_SECONDS` | float, > 0 | `30.0` | How long the circuit stays open before admitting one probe. |
| `APP_PAYMENT__HTTP__CONNECT_TIMEOUT_SECONDS` | float, > 0 | `2.0` | How long to wait for the TCP/TLS handshake. |
| `APP_PAYMENT__HTTP__READ_TIMEOUT_SECONDS` | float, > 0 | `5.0` | How long to wait for a response once the request is sent. Never retried on expiry — see [Outbound HTTP calls](../guides/outbound-http.md#the-retry-rule-and-why-it-is-narrow). |
| `APP_PAYMENT__HTTP__WRITE_TIMEOUT_SECONDS` | float, > 0 | `5.0` | How long to wait while sending the request body. |
| `APP_PAYMENT__HTTP__POOL_TIMEOUT_SECONDS` | float, > 0 | `1.0` | How long to wait for a free connection from this client's own pool, before any socket to the gateway opens. |
| `APP_PAYMENT__HTTP__MAX_CONNECTIONS` | integer, ≥ 1 | `20` | The connection pool's ceiling. |
| `APP_PAYMENT__HTTP__MAX_KEEPALIVE_CONNECTIONS` | integer, ≥ 0 | `10` | Idle connections kept open for reuse. |
| `APP_CACHE__DSN` | Redis URL | unset, required once any `APP_CACHE__*` is set | Where the order cache lives. **Leave it unset to run with no cache at all** — the service reads and writes the order repository directly. See [`CachedOrderRepository`](../explanation/layers.md#what-a-port-buys-the-caching-decorator). |
| `APP_CACHE__TTL_SECONDS` | integer, ≥ 1 | `300` | How long a cached order stays valid. A safety net, not the primary invalidation path — saving an order deletes its cache entry outright; the TTL only bounds how stale a value can get if that delete itself fails. |
| `APP_CACHE__POOL_SIZE` | integer, ≥ 1 | `10` | Connections held open to Redis. |
| `APP_CACHE__CONNECT_TIMEOUT_SECONDS` | float, > 0 | `0.5` | How long to wait for the connection to Redis. Deliberately sub-second: a cache that can stall a request for longer than the database query it is trying to avoid has made the service slower than having no cache. `redis-py` treats `0` as "wait forever", not "give up immediately", which is why this is `> 0` rather than `≥ 0`. |
| `APP_CACHE__OPERATION_TIMEOUT_SECONDS` | float, > 0 | `0.5` | How long to wait for a single Redis command. Same reasoning as the connect timeout, and the same `redis-py` `0`-means-forever trap. |
| `APP_STORAGE__BUCKET` | string, 3–63 chars | unset, required once any `APP_STORAGE__*` is set | The S3 bucket receipts are stored in. Checked against Amazon's naming rule (lowercase, digits, hyphens, dots) at startup, so a typo like a capital letter fails as exit 78, not as the first failed `PutObject`. |
| `APP_STORAGE__ENDPOINT_URL` | URL | unset | **Leave it unset for real Amazon S3** — botocore derives the endpoint from the region on its own. **Set it for everything else** — MinIO, Cloudflare R2, Ceph, or any other S3-compatible provider. This one field is the whole of "one adapter for every provider": there is no provider branch anywhere in `S3ReceiptStore`. |
| `APP_STORAGE__REGION` | string | `us-east-1` | Required by botocore's request signing even against a provider, like MinIO, that ignores it. `us-east-1` is the conventional filler value. |
| `APP_STORAGE__ACCESS_KEY_ID` | secret | unset, required once any `APP_STORAGE__*` is set | `SecretStr`, so it cannot reach a log line or a traceback by accident. |
| `APP_STORAGE__SECRET_ACCESS_KEY` | secret | unset, required once any `APP_STORAGE__*` is set | `SecretStr`, same reasoning. |
| `APP_STORAGE__CONNECT_TIMEOUT_SECONDS` | float, > 0 | `2.0` | How long to wait for the connection to the storage endpoint. |
| `APP_STORAGE__READ_TIMEOUT_SECONDS` | float, > 0 | `5.0` | How long to wait for a response once the request is sent. |

<!-- /generated: config-table -->

**Both settings are optional, and absent is a supported configuration, not a
broken one.** Leave `APP_CACHE__DSN` unset and the service serves every order
read straight from PostgreSQL, exactly as if the cache decorator were never
wrapped around the repository. Leave `APP_STORAGE__BUCKET` (and the rest of
the `storage` block) unset and `GET /orders/{id}/receipt` serves from an
in-memory store that vanishes on restart, instead of 503ing. Neither gap
shows up on `/readyz` as a failure — see
[the readiness change](http-api.md#get-readyz-readiness).

### The database URL carries no driver and no `sslmode`

Two things that look like omissions are deliberate, and the service refuses to
start if either is wrong.

**No driver suffix.** Write `postgresql://…`, not `postgresql+asyncpg://…`.
The engine adds the asyncpg driver itself when it builds the connection pool.

**No `sslmode`.** It is a libpq parameter that asyncpg does not understand, so
it would fail at the first connection rather than at startup. The migration
container needs `?sslmode=disable` against a local server, and adds it to its
own URL in `compose.yaml` — a connection string this application never reads.

Both are rejected during settings validation, which means exit 78 and a
message naming the field, not a traceback from inside a driver an hour later.

`APP_LOG__LEVELS` takes a JSON object, quoted so the shell does not split it:

```bash
APP_LOG__LEVELS='{"httpx": "warning", "uvicorn.error": "warning"}'
```

`APP_LOG__REDACT_FIELDS` takes a JSON array the same way, and **replaces**
the default list rather than adding to it — copy the default from the table
above and add your own names to it:

```bash
APP_LOG__REDACT_FIELDS='["password","token","authorization","pin","otp"]'
```

Matching is by field name only, at any depth, ignoring case and treating
`-` and `_` alike. See [Logging](logging.md#redaction) for what that does and
does not cover.

!!! danger "`APP_OTEL__LOGS_ENABLED` doubles your log bill"

    Standard output is the source of truth for logs. Most platforms already
    run an agent that reads a container's standard output and forwards it.
    Turning on log export as well sends every record twice — once through
    the agent, once over the network — doubling both ingest volume and cost.

    It is off by default and should stay off in production. It exists for
    local work, where trace-to-log correlation in Grafana is worth having and
    there is no agent.

## Bad configuration stops the process

Settings are built once at startup and validated then. A missing or malformed
value prints a readable message to standard error and exits with code **78**:

```
Invalid configuration:
  http_port: Input should be less than or equal to 65535 (less_than_equal)
```

Each line names the setting, what is wrong with it, and the rule that rejected
it. The offending **value is deliberately not echoed**. Pydantic's own
rendering includes it, and for `APP_DATABASE__DSN` that value is a connection
string with a password in it — a misconfiguration would otherwise write the
database password to the startup logs. The trade-off is real and applies to
every setting: a typo in `APP_HTTP_PORT` is now named but not shown. A blanket
rule cannot be forgotten the way a list of "settings that hold secrets" can.


78 is `EX_CONFIG` from `sysexits.h`, the conventional Unix exit code for a
configuration error. An orchestrator can tell "this was misconfigured" apart
from "this crashed".

The alternative — accepting a bad value and failing later — turns a typo into
a 500 response an hour after deployment, at which point nobody connects the
two. Failing at startup means a bad deployment never receives traffic.

This is why `APP_LOG__LEVEL` is a fixed set of five values rather than a
plain string. `APP_LOG__LEVEL=verbose` as a plain string would pass validation
and then raise `ValueError: Unknown level: 'VERBOSE'` deep inside logging
setup — a crash, in place of the readable exit-78 message every other bad
value produces.

## Settings are frozen, with one gap

`Settings` and its sub-models are frozen: assigning to a field after startup
raises rather than silently changing behaviour under a running server.

One gap remains, and it is documented rather than hidden. `APP_LOG__LEVELS`
holds an ordinary Python dictionary. Freezing refuses to *replace* the
dictionary, but the dictionary object itself is still mutable, so
`settings.log.levels["x"] = "debug"` succeeds. Nothing in the code does this.
It is recorded here because a claim that settings are simply "frozen" would
promise more than the code delivers.

## One more gap worth knowing

Unknown keys in a `.env` **file** are rejected. An unknown variable set
directly in the process environment — `APP_SOMETHING_UNKNOWN=1` — is silently
ignored.

The two sources are treated differently by the settings library, and there is
no option that closes the environment-variable half. So a typo in a deployment
manifest will not be caught: the variable is ignored and the default is used.
Prefer changing `.env.example` and keeping deployment variables reviewed.
