# Reference Service

The PyFr reference service: the walking skeleton every generated project
starts from. It runs, it is tested, and as of M1 it persists orders to a real
PostgreSQL database, with the schema under migration control. A cache and
object storage still arrive in later milestones.

## Requirements

- [uv](https://docs.astral.sh/uv/) — the only Python tool you need
- Docker, for `just up` and for the integration test tier (`just test-integration`,
  `just gates`) — both start real containers, PostgreSQL included
- [just](https://github.com/casey/just) — the command runner
- PostgreSQL 16 — never installed locally; pulled as the `postgres:16-alpine`
  image by `just up` and by the integration tests

## Five-minute start

```bash
uv sync                    # or: just install
uv run pre-commit install  # one-time: wires up the lint and commit-msg hooks
just dev                   # http://localhost:8000/docs — in-memory repository
```

`just up` is the containerized alternative: one command starts PostgreSQL, waits
for it to report healthy, applies every migration, and only then starts the API —
in that order, so there is no window where the API is up against a schema that
is not there yet.

## Commands

| Command | What it does |
|---|---|
| `just install` | Sync dependencies from the lock file |
| `just dev` | Run with auto-reload on port 8000 |
| `just test` | Run the unit and api tiers — no containers, no Docker needed |
| `just test-integration` | Run the container-backed integration tier (needs Docker) |
| `just test-all` | Run every tier: unit, api and integration |
| `just gates` | All four schema governance gates — see [Database](#database) |
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
| `just check-all` | `check`, plus `test-integration` and `gates` — what CI will run at M5, and what to run before a pull request that touches the schema or the adapter |
| `just up` / `just down` | Start / stop the container stack |

## Endpoints

| Path | Purpose |
|---|---|
| `GET /healthz` | Liveness. Never checks a dependency. |
| `GET /readyz` | Readiness. Checks dependencies with short timeouts. |
| `GET /startupz` | Whether startup has finished. |
| `POST /api/v1/orders` | Place an order. |
| `GET /api/v1/orders/{order_id}` | Fetch an order. |
| `GET /docs` | Interactive API documentation. |

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
| `APP_DATABASE__DSN` | unset (commented out in `.env.example`) | PostgreSQL connection string, read by the **application only** — `just up`'s migrate service and every `just migrate-*` recipe carry their own hardcoded URL in `compose.yaml` and never read this one, so there is no golang-migrate/SQLAlchemy drift to worry about here. Unset selects the in-memory repository (see [Database](#database)); when set, store it WITHOUT a `+asyncpg` driver suffix and WITHOUT an `sslmode` parameter — `infrastructure/db/engine.py` adds `+asyncpg` itself, and `sslmode` is a libpq parameter asyncpg does not understand, rejected at settings-validation time (exit 78, naming the field) rather than reaching asyncpg as a raw error |
| `APP_DATABASE__POOL_SIZE` | `10` | The hard ceiling on concurrent database connections this instance opens. `infrastructure/db/engine.py` pins SQLAlchemy's `max_overflow` to `0`, so this is an exact number, not this plus SQLAlchemy's own default overflow of 10 — the difference matters when this figure is used for capacity planning against the database's own `max_connections` |
| `APP_DATABASE__STATEMENT_TIMEOUT_MS` | `5000` | PostgreSQL `statement_timeout`, applied per connection — a runaway query is cancelled by the server rather than holding a pooled connection forever |
| `APP_OTEL__ENABLED` | `false` | Reserved for M2's OpenTelemetry exporter |
| `APP_OTEL__LOGS_ENABLED` | `false` | Reserved for M2; would double log ingest if enabled alongside a platform log agent |
| `APP_OTEL__ENDPOINT` | unset | Reserved for M2; the OTLP collector endpoint the exporter would send to |

Invalid configuration stops the process at startup with exit code 78 and a
readable message, rather than causing a 500 response later.

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
