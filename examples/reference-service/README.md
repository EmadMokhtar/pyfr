# Reference Service

The PyFr reference service. Generated from
[PyFr](https://github.com/EmadMokhtar/pyfr). It persists orders to a real PostgreSQL database with the
schema under migration control, authorises payment over a retrying,
circuit-breaking HTTP client, caches order reads in Redis behind a fail-open
decorator, and renders and stores one receipt per order in S3-compatible
object storage. All four dependencies are optional and absent by default —
the service starts and serves correctly with none of them configured.

## Requirements

- [uv](https://docs.astral.sh/uv/) — the only Python tool you need
- Docker, for `just up`, for the integration test tier (`just test-integration`,
  `just gates`) — real containers throughout: PostgreSQL, Redis and MinIO — and
  for `just security`, which scans the built images
- [just](https://github.com/casey/just) — the command runner
- PostgreSQL 18, Redis 8 and MinIO — none installed locally; pulled as
  `postgres:18-alpine`, `redis:8-alpine` and the pinned `quay.io/minio/minio` image by
  `just up` and by the integration tests

## Five-minute start

```bash
uv sync                    # or: just install
uv run pre-commit install  # one-time: wires up the lint hooks
just dev                   # http://localhost:8000/docs — in-memory repository
```

`just up` is the containerized alternative: one command starts PostgreSQL,
Redis and MinIO, waits for PostgreSQL and MinIO to report healthy, applies
every migration and creates the receipts bucket, and only then starts the
API — in that order, so there is no window where the API is up against a
schema that is not there yet, or a bucket that does not exist yet. Once the
API reports healthy, a one-shot `seed` container creates five fixed orders
through it and exits, so `GET /api/v1/orders/<id>` has something to return
before anyone has typed a `POST`; `docker compose logs seed` prints the ids.
`just seed` does the same against `just dev`.

## Commands

| Command | What it does |
|---|---|
| `just install` | Sync dependencies from the lock file |
| `just dev` | Run with auto-reload on port 8000 |
| `just test` | Run the unit and api tiers — no containers, no Docker needed |
| `just test-integration` | Run the container-backed integration tier (needs Docker) |
| `just test-all` | Run every tier: unit, api and integration |
| `just gates` | All five schema governance gates, plus the configuration reference drift check — see [Database](#database) |
| `just config-docs` | Regenerate `.env.example` and the configuration table from `settings.py` — see [Configuration](#configuration) |
| `just config-docs-check` | Fail if either generated file has drifted from `settings.py`. Runs as part of `just gates` |
| `just config-check` | Print the resolved configuration as JSON with every secret and URL password masked, or exit 78 with the same message the service prints when it refuses to start — see [Configuration](#configuration) |
| `just schema-snapshot` | Regenerate the committed `schema.sql` after a migration change |
| `just migrate` | Apply every outstanding migration |
| `just migrate-new NAME` | Write a new `.up.sql` / `.down.sql` pair |
| `just migrate-manifest` | Regenerate `migrations/manifest.sha256` — run after `migrate-new`, never after editing an already-committed migration |
| `just migrate-down [N]` | Roll back N steps (default 1) |
| `just migrate-version` | Current version, and whether it is dirty |
| `just migrate-force VERSION` | Clear a dirty flag — read the justfile comment first |
| `just lint` | ruff check and format check |
| `just fmt` | Fix lint issues and format |
| `just typecheck` | mypy — strict on domain and services |
| `just imports` | Verify the layer dependency rule |
| `just check` | lint, typecheck, imports, test, precommit, then `git diff --exit-code` — fails loudly if any pre-commit hook (ruff-format, uv-lock, and others mutate files) changed the tree instead of silently passing on a second run; needs no Docker; run this before pushing |
| `just check-all` | `check`, plus `test-integration`, `gates`, `o11y-gates` and `contract-gates` — the same five gates CI runs as separate jobs, in one local command; run it before a pull request that touches the schema, the adapter, the API contract, or observability |
| `just up` / `just down` | Start / stop the container stack; `up` seeds five orders once the API is healthy, `down` removes the volumes, the seed's state included |
| `just seed` | Create the same five orders against `just dev` (`localhost:${APP_HTTP_PORT}`), idempotently — state in `.seed-state.json`, ignored by git |
| `just build-images` | Build both container images for this machine's architecture without starting them, exactly as CI's `security` job and the release workflow do before scanning |
| `just audit` | pip-audit over every pin in `uv.lock`, reading a `uv export` so nothing is resolved or installed — see [Supply chain](#supply-chain) |
| `just scan` | Trivy over both built images; fails on a fixed HIGH or CRITICAL finding, exemptions only through `.trivyignore.yaml` — needs Docker |
| `just sbom` | A CycloneDX software bill of materials per image, into `sbom/` — needs Docker |
| `just security` | `build-images`, `audit`, `scan`, `sbom` — what CI's `security` job runs; not part of `check-all` because its result changes with the advisory databases, not the code |
| `just build-multiarch` | Build both images for `linux/amd64` and `linux/arm64` with no output — what CI's `build` job runs |
| `just publish-images VERSION` | Push both platforms of both images to GHCR under `VERSION` — run by the release workflow, not by hand |
| `just scan-published VERSION` | Scan the pushed images for both platforms — release workflow only |
| `just promote-latest VERSION` | Point `latest` at the scanned `VERSION` — release workflow only |
| `just openapi` | Regenerate the committed `openapi.json` from the running app — read the diff before committing it |
| `just test-contract` | The contract tier: Schemathesis conformance testing over ASGI. The drift check runs in `just test` / `just check` instead — see [Contract governance](#contract-governance) |
| `just contract-gates` | `test-contract`, then the `oasdiff` breaking-change check against `openapi.baseline.json` — needs Docker |
| `just contract-release` | Promote `openapi.json` to the baseline. Only at a release — never to silence a red `contract-gates` |
| `just test-record` | Re-record the outbound HTTP cassettes against the local payment stub — see [Outbound payments](#outbound-payments) |
| `just mutants` / `just mutants-gate` | Mutation testing over `domain/` and `services/`, and the gate against the recorded floor |
| `just docs-examples` | Start the compose stack, run every marked `curl` example in `docs/` against it, then tear it down — pass or fail |
| `just redis-cli` | An interactive `redis-cli` session against the running compose cache |
| `just minio-console` | Print, and try to open, the MinIO web console — see [Object storage](#object-storage) |

## Endpoints

| Path | Purpose |
|---|---|
| `GET /healthz` | Liveness. Never checks a dependency. |
| `GET /readyz` | Readiness. Gates on the database only; reports the cache and object storage without gating on either — see [Readiness: two tiers](#readiness-two-tiers). |
| `GET /startupz` | Whether startup has finished. |
| `POST /api/v1/orders` | Place an order. |
| `GET /api/v1/orders/{order_id}` | Fetch an order. |
| `GET /api/v1/orders/{order_id}/receipt` | Fetch the order's receipt, rendering and storing it on first request — see [Object storage](#object-storage). |
| `GET /docs` | Interactive API documentation. |

### Readiness: two tiers

`/readyz`'s response carries `checks` (gating — decides the status code) and
`dependencies` (informational — reported, never decisive):

```json
{"status": "ok", "checks": {"database": "ok"}, "dependencies": {"cache": "ok", "storage": "ok"}}
```

Only the database is gating. The cache and the object store are always
informational, and that split is deliberate rather than an oversight:

- The cache **fails open** — `CachedOrderRepository` swallows every Redis
  error and falls through to PostgreSQL — and Redis is **shared across every
  pod**. Gating on it would make every pod report itself unready in the same
  second, turning a degradation the service is built to survive into a total,
  self-inflicted outage.
- Losing object storage breaks exactly one endpoint
  (`GET /orders/{id}/receipt`), so taking 100% of traffic off a pod to
  protect that one endpoint would cost far more than it saves.

Verified against a real stack, not just reasoned about: with Redis stopped, an
order read still returned 200; with MinIO stopped, the receipt endpoint
returned 503 while the order endpoint kept returning 200; with either
stopped, `/readyz` itself still returned 200.

## Contract governance

`openapi.json` is committed at the project root, generated from the code
and never hand-edited. Three gates keep it honest: a byte-for-byte drift
check against the code, generated conformance testing against the running
app (Schemathesis, over ASGI — no server, no socket), and a breaking-change
check (`oasdiff`) cross-checked against the version in `pyproject.toml`.

```
just openapi           regenerate the contract from the code — read the diff before committing
just test-contract     conformance testing — no Docker needed
just contract-gates    test-contract, plus the breaking-change check — needs Docker
just contract-release  promote the current contract to the baseline — only at a release
```

The drift check itself is not in this list: it needs no Docker and no
generation, so it runs as an ordinary test in `just test` / `just check`
instead — see `tests/unit/test_contract_drift.py`.

Writing the conformance gate against code that already existed found five
real defects — three of the service's own error responses silently
bypassing RFC 9457, a published schema more permissive than the model it
described, and a client input that produced a 500 instead of a 422 — none
of them contrived.

## Layout

```
src/reference_service/
  domain/          entities and repository ports; imports only pydantic
  services/        application services; one file per aggregate
  infrastructure/  adapters; the only code that knows a storage technology
  api/             the only code that knows HTTP
```

The arrows point inward: `infrastructure` and `api` import `domain`, never
the reverse. `just imports` fails the build if that stops being true.

## Database

The schema is owned by [golang-migrate](https://github.com/golang-migrate/migrate),
as plain SQL in `migrations/`, applied by a container. Nothing about applying the
schema needs Python, so the production step is an init container running the small
image built from `Dockerfile.migrations`.

```
just migrate                 apply everything outstanding
just migrate-new NAME        write a new .up.sql / .down.sql pair
just migrate-manifest        regenerate manifest.sha256 — run after migrate-new
just migrate-down 1          roll back one step
just migrate-version         current version, and whether it is dirty
just migrate-force VERSION   clear a dirty flag — read the justfile comment first
just psql                    an interactive session against the local database
```

`schema.sql` is a committed snapshot of the schema those migrations produce. It is
generated, never hand-edited: run `just schema-snapshot` after changing a migration
and commit the result, so every schema change is reviewable as a schema change.

Run the service with no database at all by leaving `APP_DATABASE__DSN` unset — it
falls back to an in-memory repository and still serves.

### Schema governance

Five gates. The first four rebuild the database from scratch every run, which is
exactly why none of them can see the fifth's trap: an EXISTING migration file
edited in place, after it may already be applied elsewhere. All five run with
`just gates`:

| Gate | What it proves |
|---|---|
| Version collisions | Migration numbering is sequential, paired and well-formed, so a collision is a git conflict rather than a migration silently skipped in one environment |
| Schema snapshot | The migrations still produce the committed `schema.sql` |
| Reversibility | Every `down.sql` truly reverses its `up.sql` — checked before an incident, not during one |
| Model drift | The SQLAlchemy models still match the real schema, which is what catches a model changed without a migration |
| Migration manifest | No migration file `manifest.sha256` already records has changed since it was recorded. Editing an already-applied migration instead of adding a new one is silently ignored everywhere that migration already ran (`migrate up` reports "no change" there) — this is the only gate that can see it |

Alembic appears in the development dependencies **only** as the comparison engine
behind the model drift gate. There is no `alembic/` directory and no Alembic
migration; golang-migrate owns the schema.

## Cache

`CachedOrderRepository` is a decorator, not a second adapter beside
`PostgresOrderRepository` — it satisfies `OrderRepository` and holds another
`OrderRepository` inside it. That is the whole reason it can be added and
removed by editing `container.py` alone: nothing above the infrastructure
layer — not the service, not the router, not the domain — imports `redis` or
knows a cache exists.

It is **fail open** by rule, not by accident: every Redis failure (a
connection error, a timeout, an unparseable cached payload) is logged and
swallowed, and the wrapped repository answers instead. There is no setting
that changes this, because a cache that can make a request *fail* has made
the service strictly worse than having no cache at all. Verified against a
real stack: with Redis stopped, an order read still returned 200.

Reads check Redis first and populate it on a miss. Saves write to PostgreSQL
first and then delete the cache key — never the other way around, because
delete-then-save leaves a window where a concurrent reader can repopulate the
cache with the value that is about to become stale.

```
just redis-cli   an interactive redis-cli session against the running compose cache
```

Leave `APP_CACHE__DSN` unset to run with no cache at all — every order read
goes straight to PostgreSQL, the same supported arrangement `database` above
has with the in-memory repository. `just up` points it at the compose Redis.

## Outbound payments

`PlaceOrder` authorises a payment before saving the order, through one
outbound HTTP client shared by every future outbound integration: four
explicit timeouts, a narrow retry rule (only what provably never reached
the gateway — never a read timeout, never a 502 or 504, because those may
have been delivered and this authorises money), and a hand-written circuit
breaker with three states. A decline is 402; a provider that cannot be
reached is 503 with `Retry-After`.

```
just test-record   re-record the outbound cassettes against the local payment stub
just mutants       mutation testing over domain/ and services/
just mutants-gate  fail the build if the mutation score falls below the recorded floor
```

Leave `APP_PAYMENT__BASE_URL` unset to run on the in-memory gateway, which
authorises everything — the same arrangement `database` above has with the
in-memory repository. `just up` points it at a local WireMock stub instead.

Two things are worth knowing rather than assuming. The recorded cassettes
prove this adapter still parses that stub's wire format; they cannot detect
the real provider changing, because the stub is static and nothing about it
changes on its own. And if this process dies between a successful
authorisation and a successful save, the payment provider is left holding
an authorisation with no order to match it — a gap M3 records rather than
closes, because closing it needs an outbox or a reconciliation job, and
message queues are excluded from this project entirely.

## Object storage

`GET /api/v1/orders/{order_id}/receipt` serves a receipt document over
`S3ReceiptStore`, one adapter over `aioboto3` for every S3-compatible
provider — Amazon S3, MinIO, Cloudflare R2, Ceph — distinguished only by
`APP_STORAGE__ENDPOINT_URL`. There is no provider branch anywhere in the
adapter.

**Receipts are rendered on demand, never written when the order is placed.**
The first request for a given order renders the document and stores it;
every request after that serves the stored bytes unchanged. This keeps
object storage entirely out of the order-placement write path, so a storage
outage can never fail a payment — it can only make one read endpoint 503
with `Retry-After` (fixed at 30 seconds, unlike the payment provider's
breaker-derived one above — object storage has no breaker in front of it).
Verified against a real stack: with MinIO stopped, the receipt endpoint
returned 503 while the order endpoint kept returning 200.

```
just minio-console   print, and try to open, the MinIO web console (minioadmin / minioadmin)
```

Leave the `APP_STORAGE__*` block unset to run with no object store at all —
receipts are held in memory and vanish on restart, the same supported
arrangement `database` and `cache` have with their own in-memory fallbacks.
`just up` starts MinIO and a one-shot `minio-bootstrap` container that
creates the bucket, because MinIO does not create one on demand and the
application deliberately does not create its own — that would need
`CreateBucket` permission in production, on top of the narrower
`GetObject`/`PutObject`/`HeadBucket` the receipt store actually uses.

Object storage calls are **not traced**, unlike everything else this service
instruments. `opentelemetry-instrumentation-botocore` was tried against a
real MinIO container and produced zero spans for any `aioboto3` call — traced
`ListBuckets`, `PutObject` and `GetObject` all succeeded and all produced
nothing, because `aiobotocore`'s async client replaces the exact method the
instrumentor patches. The dependency was removed rather than shipped doing
nothing; see `instrument_redis` in `src/reference_service/observability/otel.py`
for the full measurement. Redis commands, by contrast, are traced normally.

## Observability

Telemetry is off by default and costs nothing when off — no providers built,
no socket opened, no background task started.

```bash
just o11y
```

That adds one container holding Grafana, Prometheus, Tempo, Loki and an
OpenTelemetry collector, with three dashboards and the service level
objective rules from `ops/` mounted in. Grafana is on
<http://localhost:3000> with no login; look in the **PyFr** folder.

Make a request and you can follow it three ways: as a trace in Tempo, as log
lines carrying that trace's `trace_id`, and as metrics on the service-health
dashboard.

The service-health dashboard's Redis panel is titled "Redis command latency
(p50/p99)", not "Redis pool usage" — that was the original plan, and it
turned out not to exist to draw. `opentelemetry-instrumentation-redis` emits
spans but no metrics at all; confirmed against a live stack by generating
real cache traffic and finding no Prometheus series with `redis` or `pool` in
its name. The panel instead turns Redis command spans into a latency
histogram through the span-metrics connector `grafana/otel-lgtm` runs by
default — a real, useful signal (it is how a "fast" cache read that is
actually costing 40ms gets noticed), just not the saturation signal that was
asked for.

`just o11y-gates` validates the objective rules with `promtool`, which runs
from inside the pinned image rather than needing its own install.

## Configuration

Every variable is prefixed `APP_`; nested settings use `__`. Copy
`.env.example` to `.env` to start. The whole `APP_DATABASE__*` block ships
commented out there, like `APP_OTEL__ENDPOINT`: the justfile sets
`dotenv-load := true`, so a `.env` with `APP_DATABASE__DSN` uncommented but
no PostgreSQL actually running would make `just dev` silently pick the
PostgreSQL adapter instead of the in-memory one described below, and 500 on
the first order. Uncomment the whole block once a database is actually
reachable at that URL — `just up` provides one without needing this block set
at all (see [Database](#database)). Uncomment all three lines together, not
`APP_DATABASE__DSN` alone: `database` only stays optional when NONE of its
variables are set — with any one of `APP_DATABASE__POOL_SIZE` or
`APP_DATABASE__STATEMENT_TIMEOUT_MS` present but `APP_DATABASE__DSN`
missing, settings validation fails outright (`dsn`: "Field required")
instead of falling back to the in-memory repository.

| Variable | Default | Meaning |
|---|---|---|
| `APP_ENVIRONMENT` | `local` | `local` gives colourised console logs; anything else gives JSON |
| `APP_SERVICE_NAME` | `reference-service` | Used as the OpenAPI title and the `service.name` log field |
| `APP_HTTP_PORT` | `8000` | Port to serve on — read by `just dev` and the container's `CMD` |
| `APP_LOG__LEVEL` | `info` | Root log level |
| `APP_LOG__LEVELS` | `{}` | Per-logger overrides, as JSON |
| `APP_LOG__REDACT_FIELDS` | the fifteen names in `.env.example` (`password`, `token`, `authorization`, `card_number`, …) | Field names whose values are replaced by `[REDACTED]` before a record is rendered, as a JSON array — matched by name at any depth, ignoring case and treating `-` and `_` alike. Setting it **replaces** the default list. Keys only: a secret interpolated into the message string is not seen, so put secrets in fields, never in the event string |
| `APP_DATABASE__DSN` | unset (commented out in `.env.example`) | PostgreSQL connection string, read by the **application only** — `just up`'s migrate service and every `just migrate-*` recipe carry their own hardcoded URL in `compose.yaml` and never read this one, so there is no golang-migrate/SQLAlchemy drift to worry about here. Unset selects the in-memory repository (see [Database](#database)); when set, store it WITHOUT a `+asyncpg` driver suffix and WITHOUT an `sslmode` parameter — `infrastructure/db/engine.py` adds `+asyncpg` itself, and `sslmode` is a libpq parameter asyncpg does not understand, rejected at settings-validation time (exit 78, naming the field) rather than reaching asyncpg as a raw error |
| `APP_DATABASE__POOL_SIZE` | `10` | The hard ceiling on concurrent database connections this instance opens. `infrastructure/db/engine.py` pins SQLAlchemy's `max_overflow` to `0`, so this is an exact number, not this plus SQLAlchemy's own default overflow of 10 — the difference matters when this figure is used for capacity planning against the database's own `max_connections` |
| `APP_DATABASE__STATEMENT_TIMEOUT_MS` | `5000` | PostgreSQL `statement_timeout`, applied per connection — a runaway query is cancelled by the server rather than holding a pooled connection forever |
| `APP_OTEL__ENABLED` | `false` | Turn on OpenTelemetry traces and metrics — see [Observability](#observability). Off by default; with it off nothing OpenTelemetry is built at all |
| `APP_OTEL__LOGS_ENABLED` | `false` | Export logs over OTLP too, in addition to standard output. Doubles log ingest if enabled alongside a platform log agent — leave it off in production |
| `APP_OTEL__ENDPOINT` | unset | The OTLP collector endpoint. **Required** when `APP_OTEL__ENABLED` is true |
| `APP_PAYMENT__BASE_URL` | unset | The payment provider's base URL — see [Outbound payments](#outbound-payments). Leave unset for the in-memory gateway, which authorises everything |
| `APP_CACHE__DSN` | unset | Redis connection string — see [Cache](#cache). Leave unset to run with no cache at all; every order read goes straight to PostgreSQL |
| `APP_CACHE__TTL_SECONDS` | `300` | How long a cached order stays valid. A safety net, not the primary invalidation path — saving an order deletes its cache entry outright |
| `APP_STORAGE__BUCKET` | unset | The S3 bucket receipts are stored in — see [Object storage](#object-storage). Required, along with the access key pair, once any `APP_STORAGE__*` variable is set |
| `APP_STORAGE__ENDPOINT_URL` | unset | **Leave unset for real Amazon S3** — botocore derives the endpoint from the region itself. **Set it for everything else** — MinIO, Cloudflare R2, Ceph. This one field is the whole of "one adapter per provider" |
| `APP_STORAGE__ACCESS_KEY_ID` / `APP_STORAGE__SECRET_ACCESS_KEY` | unset | `SecretStr`, so neither can reach a log line or a traceback by accident |

Invalid configuration stops the process at startup with exit code 78 and a
readable message, rather than causing a 500 response later. `just config-check`
— or, inside the image, `docker compose run --rm app python -m
reference_service.config_check` — loads settings the same way and either
exits 78 with that message or prints the configuration the service would
start with, as JSON, with every `SecretStr` and every URL password masked.

## Supply chain

```
just audit             pip-audit over uv.lock — no Docker
just scan              Trivy over both built images — fails on a fixed HIGH or CRITICAL finding
just sbom              a CycloneDX bill of materials per image, into sbom/
just security          build-images, then all three — what CI's security job runs
just build-multiarch   both images for linux/amd64 and linux/arm64, no output — what CI's build job runs
```

A finding is exempted only through `.trivyignore.yaml`, where every entry
names a reason, a path and an `expired_at` date; after that date the finding
fails the scan again. There is no skip flag anywhere else. The five entries
there today are all in the `migrate/migrate` Go binary, in code `migrate up`
never runs; a Dependabot bump of that base image is the moment to re-scan
and drop them.

On release, the repository's workflow builds and scans the
single-architecture images first, then builds both images for both
architectures and pushes `ghcr.io/emadmokhtar/reference-service` and
`ghcr.io/emadmokhtar/reference-service-migrations` under the
repository's version, scans the pushed digests for both platforms, generates
the SBOMs from those same references (so their subject is the image people
pull), and only then points `latest` at that version; the SBOMs are attached
to the GitHub Release. On a pull request the
SBOMs come from the local build instead and are uploaded as the `sbom`
workflow artifact. Nothing is pushed from a pull request. pip is removed from the
runtime image — it was the only source of findings there — and the image is
deliberately not distroless: the start command needs a shell to expand
`APP_HTTP_PORT`.

## Graceful shutdown and the orchestrator's kill deadline

The container's `CMD` passes uvicorn `--timeout-graceful-shutdown 30`: on
SIGTERM, uvicorn stops accepting new connections but lets in-flight
requests finish for up to 30 seconds before it exits. That number is only
a promise if the orchestrator's own kill deadline is set comfortably
above it — otherwise requests still running when the deadline hits are
killed, not drained, no matter what uvicorn was told. `compose.yaml` sets
`stop_grace_period: 40s` for exactly this reason: Docker Compose's own
default is 10 seconds, well under uvicorn's 30. A Kubernetes deployment
has the identical mismatch and needs the identical fix —
`terminationGracePeriodSeconds` on the pod spec, set the same way, above
uvicorn's `--timeout-graceful-shutdown`. It is easy to miss because
Kubernetes' own default (30s) happens to equal uvicorn's deadline here
exactly, leaving no margin at all.

## Testing note: `caplog` does not work here

`configure_logging` calls `logging.getLogger().handlers.clear()`, which
also removes the handler pytest's own logging plugin installs. Any test
that calls `create_app` (directly, or via the `client` fixture) therefore
gets nothing in `caplog`, even with `caplog.at_level(...)`. Assert on
captured stdout instead — `capsys.readouterr().out`, parsed with
`json.loads` per line — as every test in `tests/api/` and
`tests/unit/test_logging.py` already does.
