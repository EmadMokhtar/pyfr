
# PyFr — Python Microservice Cookiecutter Template

**Design specification**

| | |
|---|---|
| Date | 2026-08-28 |
| Status | Approved, ready for implementation planning |
| Scope | Milestones M0–M8 |
| Supersedes | The framework positioning in the repository `README.md` |

---

## 1. Purpose

PyFr generates production-ready Python microservices. A developer answers a short
list of prompts and receives a repository that runs, is tested, is observable, is
documented, and releases itself — with no manual infrastructure work.

The target is a working service in ten minutes, replacing the two to four weeks
teams currently spend assembling the same components by hand.

### 1.1 Product shape

PyFr v1 is a **pure cookiecutter template**. All code is generated into the new
repository and owned entirely by the team that generated it. Nothing is published
to a package index, and generated services import no PyFr package.

A shared runtime library is a deliberate *later* decision. Once three to five real
services exist, the parts nobody ever edits will be visible, and those are the
parts worth extracting. Guessing those boundaries now would mean maintaining
backward-compatibility promises for abstractions that have never met a real
requirement.

The usual cost of this decision is that a fix in the adapter layer must be
re-applied by hand in each generated service. Section 11 removes that cost: a
generated project can pull later template versions into itself through a git
three-way merge. Teams therefore keep full ownership of their code *and* receive
template fixes — which is what makes D1 affordable rather than merely cheap to
start.

### 1.2 Relationship to the existing README

The repository `README.md` currently pitches PyFr as a GoFr-style *framework* — a
library with a `Context` object that services import. That positioning is
superseded by this document. The existing `package/context.py` sketch is not
carried forward; its responsibilities are met by the composition root
(section 5.2) and the observability module (section 7).

The README must be rewritten during M5 to describe a template. Claims it makes
that this design does honour — Backstage integration, Kubernetes manifests,
multi-database support — are addressed in sections 11.7 and 12, section 14, and
section 4.6 respectively.

---

## 2. Settled decisions

Each decision below is fixed. Changing one invalidates the sections that follow it.

| # | Decision | Rationale |
|---|---|---|
| D1 | Pure template for v1; extract a library later | Learn abstraction boundaries from real use rather than guessing them |
| D2 | uv for everything Python | Locking, syncing, running, tool execution, Python version pinning, Docker builds. No pip, no `requirements.txt`, no pipx. The one pip-named tool, `pip-audit`, runs as `uvx pip-audit` and audits the uv-resolved environment |
| D3 | Prompt and prune | Cookiecutter asks per category; only the chosen adapter is generated. Zero dead code and minimal images in generated services |
| D4 | Full Grafana LGTM, OpenTelemetry-native, behind a compose profile | The only option delivering working SLI/SLO dashboards on first run; the profile keeps it off a laptop by default |
| D5 | Light DDD, four layers | Domain, service, infrastructure, api. Business logic testable with no I/O |
| D6 | Domain models are Pydantic | Invariants enforced declaratively and re-checked on assignment |
| D7 | API schemas separate from domain models, joined by mappers | The HTTP contract evolves independently of the business model |
| D8 | Narrow backend matrix | PostgreSQL, Redis, S3-compatible — each optional. Fully built and tested rather than several half-finished |
| D9 | OpenAPI specification as a governed artifact | Drift gate, Schemathesis conformance, oasdiff breaking-change gate feeding the version bump |
| D10 | All four documentation hygiene mechanisms | Strict build, link checking, executable examples, review dates and path coupling |
| D11 | Reference service first, then templatise | Never debug Jinja and Python simultaneously |
| D12 | golang-migrate owns the schema | Language-agnostic, runs without the application, plain SQL |
| D13 | SQLAlchemy 2.0 async retained, with a model/schema drift gate | Typed querying plus an automated link between SQL and Python models |
| D14 | Generated projects update from newer template versions via a git vendor branch | Keeps cookiecutter and its first-party Backstage action; adds no third-party update dependency; git supplies a real merge base, so deleted example code stays deleted |
| D15 | Structured logs go to standard output as JSON; OTLP log export is opt-in | stdout survives collector outages and captures crashes and pre-initialisation failures; OTLP added on top gives local trace-to-log correlation in Grafana with no scraper to wire up |

---

## 3. Repository layout and the three phases

### 3.1 Layout

```
pyfr/
  cookiecutter.json                      # prompts and defaults
  hooks/
    pre_gen_project.py                   # validate answers before writing
    post_gen_project.py                  # prune, git init, uv sync, first commit
  {{cookiecutter.project_slug}}/         # the template body
  examples/reference-service/            # generated output, committed, CI-verified
  tests/
    test_generation.py                   # prompts, pruning, hook behaviour
    test_generated_service.py            # generate, then run its full suite
    reference-answers.yaml               # fixed answers examples/ is built from
  docs/                                  # documentation about PyFr itself
  justfile  pyproject.toml  uv.lock
  .github/workflows/{ci,release}.yaml
  README.md  LICENSE
```

### 3.2 Migration from the current repository state

The repository today contains a partial sketch. The following changes happen at
the start of M0:

- The contents of `project/src/` move to `examples/reference-service/`, which is
  the reference service root throughout Phase A; at M7 the templatised copy
  becomes `{{cookiecutter.project_slug}}/`.
- Delete `project/src/.venv` — a virtual environment inside a template directory
  would be copied into every generated project.
- Delete `.DS_Store`; add `.idea/` to `.gitignore`.
- `ruff.toml` targets `py39` while `.python-version` says `3.13`. Reconcile to the
  chosen Python version.
- `docker/Dockerfile` installs from a non-existent `requirements.txt`. Replaced by
  a uv-based multi-stage build (D2).
- `package/config.py` uses `@dataclass` and `os.getenv`. Replaced by Pydantic
  Settings (section 5.1).
- `package/context.py` is deleted; see section 1.2.

### 3.3 The three phases

**Phase A (M0–M6).** Build `examples/reference-service/` as ordinary Python. It
runs, its tests pass, `docker compose up` works. No Jinja anywhere. Every hard
problem — the database adapter, OpenTelemetry wiring, the Grafana dashboards — is
solved as a normal engineering problem.

**Phase B (M7).** One focused conversion pass: move the tree under
`{{cookiecutter.project_slug}}/`, replace the literal service name with
`{{ cookiecutter.package_name }}`, and add the conditionals that prune unchosen
backends.

**Phase C (after M7, permanently).** The template becomes the source of truth.
`just regen` regenerates `examples/reference-service` from the template using the
fixed answers in `tests/reference-answers.yaml`. CI fails if the result differs
from what is committed.

Two consequences make this worth the discipline: the template and the reference
service can never drift, and **every pull request shows the generated output as a
reviewable diff** — a reviewer sees what a template change did to real files, not
only to Jinja.

### 3.4 The Jinja collision, and how it is handled

Cookiecutter renders every file through Jinja, which treats `{{` as a variable
reference. Several shipped files contain `{{` for their own unrelated reasons:

| File | Contains | Handling |
|---|---|---|
| `.github/workflows/*.yaml` | `${{ secrets.GITHUB_TOKEN }}` | `{% raw %}` around the expressions; the file is still rendered, because workflows must be conditional on prompts |
| `ops/prometheus/rules/*.yml` | `{{ $labels.job }}` in annotations | `{% raw %}`; the SLO target must be templated in |
| `justfile` | `{{name}}` for its own parameter interpolation | `{% raw %}`; recipes differ by backend choice |
| `ops/grafana/dashboards/*.json` | Grafana variable syntax | `_copy_without_render` — see below |

**Dashboards are copied verbatim.** The dashboard JSON uses a Grafana template
variable `$service` rather than a hard-coded service name, so the JSON is
byte-identical across every generated service and needs no rendering. Only the
small provisioning file that sets the variable's default is rendered.

The generation tests (section 8.3) assert that no `{{` or `{%` survives into a
generated project, so a future file that trips this cannot ship silently.

---

## 4. Generated service architecture

### 4.1 Layer layout

```
src/<package_name>/
  main.py             # FastAPI app factory + lifespan
  settings.py         # Pydantic Settings, validated at startup
  container.py        # composition root: builds adapters, wires ports

  domain/             # imports nothing but pydantic
    order.py          # entity + value objects, invariants enforced
    repositories.py   # Protocol: OrderRepository
    errors.py         # DomainError hierarchy

  service/
    order.py          # PlaceOrderLine, PlaceOrderCommand, PlaceOrder, GetOrder
                      # — application services and their commands, one file per aggregate

  infrastructure/
    db/               # SQLAlchemy 2.0 async: engine, models, repository adapter
    cache/            # redis adapter
    storage/          # aioboto3 adapter
    http/client.py    # shared httpx client: timeouts, retries, circuit breaker

  api/
    deps.py           # FastAPI dependencies reading from app.state
    errors.py         # domain error -> RFC 9457 Problem Details
    middleware.py     # correlation id, access logging
    health.py         # /healthz  /readyz  /startupz
    v1/               # router.py, schemas.py, mappers.py

  observability/
    logging.py otel.py metrics.py
```

### 4.2 Request flow

```
HTTP request
  -> middleware: extract or create correlation id; bind to structlog + OTel span
  -> api/v1/router: FastAPI validates the body against the api schema
  -> api/v1/mappers: schema -> service command
  -> service/order: orchestrates; holds no business rules itself
  -> domain/order: invariants enforced by Pydantic on construction
  -> domain/repositories.OrderRepository        [Protocol — the boundary]
  -> infrastructure/db/order_repository: the only code that knows SQL
```

The return path mirrors this. Errors take a separate route: a domain error
propagates upward untouched and one handler in `api/errors.py` turns it into a
Problem Details response. **The domain layer never knows an HTTP status code
exists.**

### 4.3 The dependency rule

`infrastructure` imports `domain`; `domain` never imports `infrastructure`. Ports
are `typing.Protocol` — Python's structural interface, satisfied by having the
right method signatures with no inheritance and no import of the Protocol itself.

This rule is enforced mechanically, not by review: an import-linter contract in CI
fails the build when the arrow points the wrong way.

### 4.4 Domain models

Domain entities and value objects are Pydantic models carrying their own
invariants:

```python
class Money(BaseModel):
    model_config = ConfigDict(frozen=True)          # value object: immutable
    amount: Annotated[Decimal, Field(ge=0, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]

class Order(BaseModel):
    model_config = ConfigDict(validate_assignment=True)
    id: OrderId
    lines: Annotated[list[OrderLine], Field(min_length=1)]

    @model_validator(mode="after")
    def total_must_match_lines(self) -> "Order": ...
```

`validate_assignment=True` is the part that matters for DDD: an invalid `Order`
cannot exist even after a field is reassigned, so the entity protects its own
rules rather than trusting its callers. `frozen=True` gives value objects the
immutability and value equality their definition requires.

### 4.5 API schemas are separate

`api/v1/schemas.py` holds distinct Pydantic models for requests and responses, and
`api/v1/mappers.py` holds the functions between them. This costs mapping code and
buys three things: internal fields cannot leak by default, a domain field can be
renamed without breaking the published contract, and v1 and v2 of an endpoint can
be served from one domain model.

The template generates a complete worked example of the pattern, so it is copied
rather than reinvented.

### 4.6 Adding a backend

The narrow matrix (D8) means a team on MySQL or MongoDB writes their own adapter.
`docs/how-to/add-a-backend.md` walks through the port interface, the composition
root registration, the compose service and the integration test, using the
shipped PostgreSQL adapter as the worked example.

---

## 5. Configuration and wiring

### 5.1 Settings

```python
class DatabaseSettings(BaseModel):
    dsn: PostgresDsn
    pool_size: int = 10
    statement_timeout_ms: int = 5_000

class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="APP_", env_nested_delimiter="__",
        env_file=".env", frozen=True,
    )
    environment: Literal["local", "staging", "production"]
    database: DatabaseSettings
    otel: OtelSettings
```

- `env_nested_delimiter="__"` means `APP_DATABASE__DSN` fills
  `settings.database.dsn`, so one flat environment produces a structured object.
- Secrets use `SecretStr`, whose representation prints `**********`, so a secret
  cannot reach a log line or a traceback by accident.
- Settings are constructed at startup. A missing or malformed variable kills the
  process immediately with a readable message, rather than producing a 500
  response an hour later.
- `just config-check` prints the resolved configuration with secrets masked.
- Each settings sub-model is pruned away when its backend is `none`.

### 5.2 Wiring: a composition root, not a DI framework

`container.py` is one plain module that constructs the adapters. FastAPI's
`lifespan` builds the container at startup, places it on `app.state`, and closes
it on shutdown. `api/deps.py` holds small functions reading from `app.state`,
overridden in tests via `app.dependency_overrides`.

No dependency-injection library is used. FastAPI's own `Depends` plus one module
already does the job, and a DI container is a large concept for every new team
member to learn for no gain at this size.

---

## 6. Database migrations and schema governance

### 6.1 Tool

`golang-migrate/migrate`, distributed as a Go binary and a Docker image.
Migrations are plain SQL files in matched pairs; progress is tracked in a
`schema_migrations` table holding the current version and a `dirty` flag.

Chosen over Alembic for two reasons. It is **language-agnostic**, so an
organisation running Go services on GoFr alongside these Python services uses one
migration tool, one file format, one command and one runbook. And it **runs
without the application** — the production migration step is a container running
`migrate up`, needing no Python interpreter and no import of service code, which
makes it a clean Kubernetes init container or pre-deployment Job.

Alembic and golang-migrate are never both used for migration. Two tools owning one
schema is actively harmful: each keeps its own version table and each is blind to
what the other did.

### 6.2 Layout

```
migrations/
  000001_create_orders_table.up.sql
  000001_create_orders_table.down.sql
  000002_add_orders_status_index.up.sql
  000002_add_orders_status_index.down.sql
schema.sql                    # committed snapshot of the resulting schema
Dockerfile.migrations         # FROM migrate/migrate + COPY migrations/
```

### 6.3 Interfaces

**Local** use goes through `just`, which runs the official image, so nobody
installs a Go binary — Docker is already required for the compose stack:

```
just migrate-new create_orders_table   # writes the .up.sql / .down.sql pair
just migrate                           # apply everything outstanding
just migrate-down 1                    # roll back one step
just migrate-version                   # current version, and whether dirty
just migrate-force 3                   # clear dirty state, after manual checking
```

**Compose** includes a one-shot `migrate` service that waits for PostgreSQL to be
healthy, applies migrations and exits, so `just up` yields a migrated database
with no second command.

**Production** builds `Dockerfile.migrations` as a small image pushed alongside the
application image with the same version tag, run as an init container. The
application image stays Python-only.

**Integration tests** run the real `migrate/migrate` container against the
Testcontainers PostgreSQL instance, so tests exercise the same tool and the same
ordering that production uses.

### 6.4 Known traps, and how the template answers them

**No autogeneration.** golang-migrate cannot diff models against a database and
draft a migration. SQL is written by hand. More explicit, more typing.

**The `dirty` state.** A migration that fails partway marks the version dirty, and
the tool refuses to proceed until a human runs `migrate force <version>` after
confirming the database's real state. This is correct — it refuses to guess — but
it is confusing under pressure, so `docs/runbook.md` carries a worked example and
`docs/how-to/handle-a-dirty-migration.md` covers the recovery procedure.

**Silent skipping of out-of-order versions.** `migrate up` applies every migration
whose version exceeds the current one. A migration merged later but numbered lower
than an environment's current version **will never be applied there, with no
error.** The template therefore uses sequential numbering (`migrate create -seq`),
so a collision surfaces as a git conflict, plus a CI check rejecting duplicate
version numbers and malformed filenames.

### 6.5 Schema governance: four gates

All four run in CI against a throwaway PostgreSQL container.

1. **Schema snapshot gate.** Apply all migrations to an empty database, run
   `pg_dump --schema-only`, fail if the output differs from the committed
   `schema.sql`. This makes the real schema a reviewable artifact in every pull
   request, and lets a reader see the current schema without replaying every
   migration file.
2. **Reversibility gate.** Apply all up, then all down, then all up again. Broken
   `down.sql` files are otherwise discovered during an incident.
3. **Version collision check.** Reject duplicate version numbers and malformed
   filenames (section 6.4).
4. **Model/schema drift gate.** Alembic is kept as a **dev-only dependency used
   solely as a comparison engine** — no Alembic migrations directory, no Alembic
   version table, no competing tool. One integration test points
   `alembic.autogenerate.compare_metadata` at the freshly migrated database and
   asserts the difference list is empty:

   ```python
   ctx = MigrationContext.configure(conn)
   assert compare_metadata(ctx, Base.metadata) == []
   ```

   This restores the "you changed a model and forgot the migration" protection
   that adopting golang-migrate would otherwise have lost. Because its presence
   looks contradictory, `pyproject.toml` and the test both carry a prominent
   comment explaining exactly why Alembic is installed.

---

## 7. Observability and SLOs

### 7.1 Scope boundary

The template ships **instrumentation, dashboards and rules** — not a production
observability platform. Teams already have somewhere to send data. The
application's only commitment is to emit OpenTelemetry data to whatever
`OTEL_EXPORTER_OTLP_ENDPOINT` points at. The compose stack exists so a developer
can see their own traces on a laptop, and so the dashboards are verified as
actually working.

### 7.2 Instrumentation

OpenTelemetry SDK plus automatic instrumentation for FastAPI, SQLAlchemy, Redis
and httpx. These follow the OpenTelemetry semantic conventions, so
`http.server.request.duration` means the same thing here as in a Go service and
one dashboard works across both.

- Resource attributes: `service.name`, `service.version`, `deployment.environment`.
- Sampling: parent-based with a configurable ratio — 100% locally, lower in
  production.
- Traces and metrics leave over OTLP. Logs take a different route by default —
  see section 7.6.
- Logs are structlog JSON. A processor injects the active `trace_id` and `span_id`
  into every line, so a log entry links back to its trace.

### 7.3 Local stack

The compose `o11y` profile runs the single `grafana/otel-lgtm` image, which
bundles Grafana, Prometheus, Tempo, Loki and a collector. One extra container
rather than six, with the real dashboards mounted in — the same portable JSON that
loads into production Grafana.

### 7.4 Dashboards

Provisioned from version-controlled files:

1. **Service health** — RED metrics (rate, errors, duration percentiles) plus the
   saturation signals that predict outages: database pool usage, Redis pool usage,
   event loop lag.
2. **SLI and SLO** — current indicator value, error budget remaining, burn rate,
   30-day trend.
3. **Runtime** — Python and uvicorn internals: garbage collection, memory, worker
   state.

A `service_info` metric carrying the running version lets the dashboards annotate
deployments, so a latency change and the deployment that caused it appear on the
same chart.

### 7.5 SLO definitions and alerting

- **Availability SLI**: fraction of requests not returning 5xx.
- **Latency SLI**: fraction of requests completing under a threshold, default
  300 ms.
- **Objective**: default 99.9% over a rolling 30 days.

Both the target and the latency threshold are set at generation time
(section 9.1).

Alerting uses **multi-window, multi-burn-rate rules** from Google's Site
Reliability Engineering workbook. Rather than alerting when the error rate crosses
a fixed line, it alerts on how fast the error budget is being consumed, measured
over two windows at once: a fast-burn rule pages for a sudden outage, a slow-burn
rule opens a ticket for steady low-level failure. Using two windows together is
what prevents both alert storms from brief blips and silent slow degradation.

### 7.6 Structured logging

**Transport (D15). Standard output is the source of truth; OTLP log export is
opt-in.**

```
PRODUCTION   app -> stdout (JSON) -> platform log agent -> Loki
             APP_OTEL__LOGS_ENABLED=false        (default)

LOCAL        app -> stdout (console renderer, colour, human-readable)
                \-> OTLP -> grafana/otel-lgtm -> Loki
             APP_OTEL__LOGS_ENABLED=true         (set by the o11y profile)
```

Standard output survives a collector outage, and it captures crashes and any
failure occurring before the OpenTelemetry SDK has initialised — which is exactly
the output you need when a service will not start. OTLP is added on top so a
developer sees logs beside the matching trace in Grafana without wiring up a log
scraper on their laptop.

**Enabling OTLP logs in production alongside a platform agent doubles ingest
volume and cost.** The setting carries a comment saying so, and the generated
configuration reference (section 10.3) repeats the warning.

**One pipeline for every record, including third-party ones.** uvicorn,
SQLAlchemy, boto3 and httpx log through the standard library's `logging` module,
not structlog. structlog's `ProcessorFormatter` is installed as the formatter on
the root `logging` handler so those records pass through the same processor chain
and emerge in the same shape. Without this bridge roughly half the output during
an incident is unstructured text sitting beside the clean JSON.

```python
# observability/logging.py — shape, not final code
shared_processors = [
    structlog.contextvars.merge_contextvars,     # correlation id, user id
    structlog.processors.add_log_level,
    structlog.processors.TimeStamper(fmt="iso", utc=True),
    add_otel_context,                            # trace_id, span_id
    redact_sensitive_fields,                     # section 12, item 6
    structlog.processors.StackInfoRenderer(),
    structlog.processors.dict_tracebacks,        # exceptions as structure
]
renderer = (
    structlog.dev.ConsoleRenderer()
    if settings.environment == "local"
    else structlog.processors.JSONRenderer(serializer=orjson.dumps)
)
```

`dict_tracebacks` is not cosmetic. A default traceback is multi-line text, so a
log backend ingests one exception as many unrelated entries with nothing joining
them. Rendered as a structured field it stays one searchable event.

**The field-name contract.** Every record carries a fixed set of keys, named to
follow the same OpenTelemetry semantic conventions as the traces and metrics
(section 7.2), so one query works across a Python service and a Go one:

| Key | Source | Example |
|---|---|---|
| `timestamp` | processor | `2026-08-28T09:14:22.481Z` |
| `level` | processor | `error` |
| `event` | the call site | `order.placed` |
| `logger` | standard library logger name | `my_service.service.order` |
| `service.name`, `service.version`, `deployment.environment` | resource attributes | |
| `trace_id`, `span_id` | the active span | |
| `correlation_id` | context variables, bound by middleware | |
| `http.request.method`, `http.route`, `http.response.status_code`, `duration_ms` | access log records only | |

`event` is a short, stable, lowercase dotted identifier — `order.placed`, never a
sentence — so events can be grouped and counted. Variable data goes in fields and
is never interpolated into the message.

**Access logging.** uvicorn's own access log is disabled (`access_log=False`) and
replaced by middleware emitting one structured record per request. It logs
`http.route`, the route *template* `/orders/{order_id}`, and never the raw path.
Raw paths make every order identifier a distinct label value — **high
cardinality**, meaning a field with an unbounded number of distinct values, which
is the standard way to overwhelm a log or metrics backend. Health endpoints are
excluded by default, because a readiness probe firing every two seconds otherwise
dominates the volume.

**Levels are configuration, not code.** `APP_LOG__LEVEL` sets the root level and
`APP_LOG__LEVELS` takes a per-logger mapping, so silencing a chatty library needs
no code change and no redeployment of a new image:

```
APP_LOG__LEVEL=info
APP_LOG__LEVELS='{"sqlalchemy.engine":"warning","botocore":"warning"}'
```

**Redaction** (section 12, item 6) is a processor in the shared chain rather than a
responsibility of each call site, so it covers third-party records too. It masks by
key name from a configured list, and a unit test asserts a known secret never
reaches the rendered output.

**Testing.** `structlog.testing.capture_logs` lets unit tests assert on emitted
events as dictionaries instead of matching text — a test states that an
`order.rejected` event was emitted with `reason="insufficient_funds"`, which does
not break when someone rewords a message.

---

## 8. Testing strategy

### 8.1 Generated service

```
tests/
  unit/          domain + service. No I/O, no containers. Milliseconds.
  integration/   Testcontainers: postgres, redis, minio. Real adapters.
  contract/      Schemathesis against the app over ASGI, no network.
  cassettes/     VCR recordings of outbound HTTP.
```

**Unit tests carry the weight.** Because the domain layer imports nothing but
Pydantic, business rules are tested with no database, no event loop and no
fixtures. This is the practical payoff of D5: if a unit test needs a container, a
layer boundary has leaked.

**Hypothesis** provides property-based testing for domain invariants — generating
hundreds of random valid inputs to check a rule holds, rather than testing three
hand-picked examples. It pairs well with Pydantic domain models: "no sequence of
valid operations produces an `Order` whose total disagrees with its lines" is one
short test covering cases nobody would think to write.

**Integration tests** use Testcontainers to start real PostgreSQL, Redis and MinIO
for the session. Schema comes from the real `migrate/migrate` container
(section 6.3). The schema drift gate lives here.

**VCR** (`pytest-recording`) records outbound HTTP to YAML cassettes and replays
them, keeping tests fast and offline. Two settings matter: `record_mode=none` in
CI, so a test attempting an unrecorded request *fails* rather than quietly
reaching the internet; and `filter_headers` stripping `Authorization` and cookies,
so credentials never land in a committed cassette. Cassettes rot exactly as
documentation does — they keep passing long after the real API changed — so
`just test-record` refreshes them and a weekly scheduled job re-records against
real upstreams to detect drift before a deployment does.

**Mutation testing with mutmut.** Mutation testing introduces small deliberate
changes into the source — `>` to `>=`, `+` to `-`, `True` to `False` — and re-runs
the tests. A mutation that survives proves the tests never checked that behaviour.
It measures whether tests *assert*, where coverage only measures whether lines
*executed*.

It is slow, so it is configured deliberately rather than naively: mutate only
`domain/` and `service/` (mutating adapters produces noise about error paths
nobody cares about), run only over files changed in a pull request, and run the
full suite nightly against a tracked survival threshold. Coverage remains, with
the failing threshold set at 85%, and the documentation states plainly that
coverage is the weaker of the two signals.

### 8.2 Contract testing

Three gates, all offline:

1. **Drift gate** — `openapi.json` is committed; CI regenerates it and fails on any
   difference. An API change then appears in the pull request diff as a change to
   the contract, rather than buried in a router file.
2. **Conformance** — Schemathesis reads the specification, generates
   random-but-valid requests from it, and checks the application never violates its
   own contract. Known exceptions are marked in a documented, reviewed list rather
   than by disabling the check.
3. **Backward-compatibility gate** — `oasdiff` compares the specification against
   the last released one and classifies each change as breaking or not. See
   section 10.2 for how this feeds the version bump.

Consumer-driven contract testing (Pact) is out of scope: it only pays off with
buy-in from consumer teams and a hosted broker, and in a freshly generated single
service it is scaffolding nobody runs.

### 8.3 The template's own test suite

Using `pytest-cookies`:

- **Generation tests** — all 8 backend combinations. Assert that pruning actually
  happened: no `redis` string anywhere when cache is `none`, no unused dependency
  in `pyproject.toml`, no empty directory left behind, no surviving `{{` or `{%`,
  hooks ran.
- **Full-suite tests** — 3 sampled combinations (everything on, everything off,
  PostgreSQL only): generate, `uv sync`, then run the generated service's entire
  lint, type-check and test suite. Slow, so these run on merge and nightly rather
  than on every push.
- **Golden diff test** — regenerate `examples/reference-service` and fail on any
  difference from what is committed.

The golden diff is what holds the scheme together: it is impossible to change the
template without the generated result appearing in the pull request as a readable
diff.

---

## 9. The generation interface

### 9.1 Prompts

Kept deliberately short — every prompt forces a decision on someone in a hurry.

```
project_name, project_slug, package_name, description
author_name, author_email, github_org
python_version           3.13 | 3.12
database                 postgres | none
cache                    redis | none
object_storage           s3 | none
http_port                8000
slo_availability_target  99.9 | 99.95 | 99.5
slo_latency_ms           300
license                  Apache-2.0 | MIT | Proprietary
```

No `include_k8s_manifests` prompt exists in M0–M8. Kubernetes manifests are an M9
feature (section 13), and a prompt must never offer something the template cannot
yet generate.

The answers given here are recorded in `.pyfr-answers.yml` so the project can be
updated from a later template version (section 11.1).

`project_slug` and `package_name` are derived by default
(`My Service` -> `my-service` -> `my_service`) and rarely typed by hand.

Object storage is one adapter, not many: Amazon S3, MinIO, Cloudflare R2, Ceph and
Backblaze B2 all speak the same API, so a single `aioboto3` adapter with a
configurable `endpoint_url` covers all of them — MinIO locally, real S3 in
production, no code change.

### 9.2 `pre_gen_project.py`

Validates before anything is written, exiting with a clear message rather than
generating a broken project:

- `project_slug` matches `^[a-z][a-z0-9-]*$`.
- `package_name` is a valid Python identifier that does not shadow a standard
  library module — a service named `email` or `types` breaks in confusing ways.
- `http_port` is a valid port number.

### 9.3 `post_gen_project.py`

Does what Jinja cannot:

- Delete whole pruned files and directories.
- `git init` and an initial commit.
- `uv sync` and install the pre-commit git hook.
- Generate the first `openapi.json` so the drift gate has a day-one baseline.
- Print next steps.

Network steps are best-effort: if `uv sync` fails offline, the hook prints the
command to run later rather than aborting an otherwise-fine project.

### 9.4 Pruning rules

Two mechanisms with one invariant. Jinja `{% if %}` removes lines inside a file,
for example a dependency in `pyproject.toml`. The post-generation hook removes
whole files and directories, for example `infrastructure/cache/`.

**No empty directory and no unused import may survive.** The generation tests
enforce this, so it cannot quietly stop being true.

---

## 10. Release, versioning, documentation, CI

### 10.1 Two version numbers

The template has a version; each generated service has its own, and they are
independent. Both use Conventional Commits with **Commitizen**, which reads the
commits since the last tag, decides the bump (`feat:` minor, `fix:` patch, `!` or
a `BREAKING CHANGE:` footer major), updates `pyproject.toml`, writes
`CHANGELOG.md` and creates the tag.

Template tags give users pinning:
`cookiecutter gh:<org>/pyfr --checkout v2.3.0`.

The version has one source — `pyproject.toml` — and travels everywhere: read at
startup with `importlib.metadata.version()` into the OpenTelemetry
`service.version` resource attribute, the `/healthz` response body, and the
`service_info` metric.

### 10.2 The gate tying the contract to the version

`oasdiff` says whether the API broke. Conventional Commits say what the bump will
be. These can disagree — someone removes a response field and writes `fix:`. CI
cross-checks them: **if oasdiff reports a breaking change and no commit in the
range is marked breaking, the build fails**, naming the offending API change.

Without this, a service silently ships a breaking change as a patch release, and
every client pinned to a minor version breaks in production.

### 10.3 Documentation

MkDocs Material, organised by **Diátaxis**, which separates documentation into
four kinds because readers arrive with four different needs — tutorials, how-to
guides, reference, explanation. Mixing them is why many documentation sites
frustrate their readers.

```
docs/
  index.md              what this service is, five-minute start
  tutorial/             add your first endpoint, end to end
  how-to/               add-a-backend, run-migrations, record-cassettes,
                        add-a-dashboard-panel, handle-a-dirty-migration,
                        update-from-template
  reference/            configuration (generated), api (from openapi.json),
                        architecture
  explanation/          why four layers, why golang-migrate, why the gates
  adr/                  architecture decision records
  runbook.md            on-call: dirty migrations, dependency down,
                        high burn rate, rollback
```

**The configuration reference is generated, not written.** A script walks the
Pydantic Settings model and emits a Markdown table of every environment variable
with its type, default and whether it is secret. It is regenerated in CI and
drift-gated, so the document that goes stale fastest in every service cannot go
stale here.

**Hygiene checks (D10):**

| Check | Catches |
|---|---|
| `mkdocs build --strict` | Broken internal references |
| `lychee` | Dead external links |
| Executable code blocks | Documentation that is *wrong*, not merely old |
| `last_reviewed` frontmatter with a maximum age | Neglect |
| `covers:` path coupling | Code changed while its documentation did not |

Path coupling and review dates start as **warnings**, with a documented switch to
hard failures once a team trusts them — a large refactor triggers path-coupling
warnings across many pages at once, which is annoying exactly when a team is
busiest.

### 10.4 CI for a generated service

```
lint         ruff check + ruff format --check
types        mypy: strict on domain/ and service/, lenient elsewhere
imports      import-linter: the dependency rule (section 4.3)
unit         pytest tests/unit + hypothesis
integration  testcontainers: postgres, redis, minio
migrations   schema snapshot, reversibility, version collisions, model drift
contract     openapi drift, schemathesis, oasdiff + version cross-check
docs         mkdocs --strict, lychee, executable code blocks, freshness
security     pip-audit, trivy, SBOM
build        multi-architecture image + migrations image
```

Type-checking strictness is deliberately uneven: `mypy --strict` on domain and
service, where the logic lives and types encode business rules; lenient in
infrastructure, where third-party stubs are imperfect and strictness produces
`# type: ignore` comments rather than safety.

`security` runs `pip-audit` through `uvx`, auditing the uv-resolved environment;
this is the one place a pip-named tool appears, and it does not reintroduce pip as
a package manager (D2).

`release.yaml` runs Commitizen, pushes both images, publishes a GitHub Release and
deploys the documentation site. `nightly.yaml` runs the full mutation suite and
re-audits dependencies. A separate weekly job re-records VCR cassettes
(section 8.1). Both hold the slow, valuable work that must not sit in the pull
request path.

### 10.5 Pre-commit hooks

Kept under roughly two seconds, or people bypass them: ruff check and format,
`uv lock` freshness, Commitizen's commit-message check, `gitleaks`, `sqlfluff` on
the migration SQL, plus whitespace and YAML checks.

Deliberately excluded: mypy, OpenAPI regeneration and the test suite. Those live
in `just check`, the one command a developer runs before pushing.

---

## 11. Updating a generated project

A generated project must be able to pull in a newer template version. This is what
makes D1 affordable: teams own their code outright and still receive template
fixes.

### 11.1 What creation records

The post-generation hook writes one file, and only that file is required for
updates to work later:

```yaml
# .pyfr-answers.yml
_template: https://github.com/<org>/pyfr
_template_version: v2.3.0
project_name: My Service
package_name: my_service
python_version: "3.13"
database: postgres
cache: redis
object_storage: s3
http_port: 8000
slo_availability_target: "99.9"
slo_latency_ms: 300
license: Apache-2.0
```

`_template_version` is a git tag rather than a commit hash, because Commitizen
already tags every template release (section 10.1) and a tag can be looked up in a
changelog. The value is baked into `cookiecutter.json` and bumped by the template's
own release workflow, so the hook never has to inspect the checkout it was
rendered from — a detail that matters for Backstage (section 11.7).

### 11.2 The template branch

An update is a three-way merge, which needs a **merge base**: a commit both sides
descend from, representing the last state they agreed on. The generated repository
supplies one by keeping a `template` branch that holds pristine generated output
and nothing else.

The branch does not have to exist at creation time. It can always be
reconstructed, because **a generated repository's first commit is by definition
unmodified template output**:

```
git branch template $(git rev-list --max-parents=0 HEAD)
```

`just update` creates it this way on first run. Nothing but `.pyfr-answers.yml`
therefore has to survive project creation, which is what lets the mechanism work
identically from the command line and from a developer portal.

### 11.3 The update flow

```
just update [--to v2.5.0]

  1. read .pyfr-answers.yml          -> answers, current version
  2. resolve the target version       (newest template tag, or --to)
  3. ensure the template branch exists (section 11.2)
  4. check out template into a temporary git worktree
  5. re-render the template at the target version with the recorded
     answers, into a temporary directory
  6. copy the result over the template worktree, deleting files the
     template no longer produces, skipping paths in .pyfr-update-ignore
  7. commit on template: "chore: template v2.3.0 -> v2.5.0"
  8. run migration scripts for versions in (current, target]
  9. git merge template
 10. on a clean merge, record the new version in .pyfr-answers.yml
```

Step 5 re-renders with hooks **enabled but in regeneration mode**. The
post-generation hook does two kinds of work, and only the first may run during an
update:

| Kind | Examples | Runs during an update? |
|---|---|---|
| Structural, deterministic | prune unchosen backends, write `.pyfr-answers.yml` | yes |
| Environmental, side-effectful | `git init`, `uv sync`, install pre-commit, generate the OpenAPI baseline, print next steps | no |

The hook tells them apart by the `PYFR_REGENERATE` environment variable, which
`just update` sets. Disabling hooks altogether is not an option: pruning happens
there, and an unpruned regeneration would try to re-add every backend the project
does not use.

**Why deletions behave correctly.** Every team deletes the example `Order` slice in
its first week. On update, git compares three states: the merge base has `Order`,
the template side has not touched it, your side deleted it. Only one side changed,
so git keeps it deleted — no conflict, no prompt. A patch-based updater instead
tries to apply the template's later edits to files that are no longer there and
fails on every one. This difference shows up in every single update, and is the
main reason for choosing this mechanism.

### 11.4 What is never updated

`.pyfr-update-ignore` lists paths the update leaves exactly as the project has
them. They are skipped in step 6, so the template side never changes them and git
never forms an opinion about them. The generated default:

```
.pyfr-answers.yml        # written directly by just update, in step 10
README.md                # yours from the first day
CHANGELOG.md
migrations/              # your schema; never template-owned
schema.sql
openapi.json             # an artifact of your code, not the template's
docs/adr/                # your decisions
src/*/domain/            # the example slice, then your business model
src/*/service/
src/*/api/v1/
```

Everything else is template-owned and updates by default: the CI workflows, both
Dockerfiles, `compose.yaml`, the `justfile`, the ruff and mypy configuration, the
pre-commit configuration, `ops/**` (dashboards and alert rules), `scripts/**`, the
observability wiring, and `api/health.py`, `api/errors.py` and `api/middleware.py`.

One rule decides the split: **template-owned files are infrastructure a team
rarely edits and benefits from receiving fixes to; project-owned files are the ones
a team rewrites immediately.** Teams add their own paths as they diverge.

### 11.5 Migration scripts

Some template changes cannot be expressed as a merge. If v3.0 moves `settings.py`
to `config/settings.py`, the merge sees an unrelated deletion and addition, and a
team loses its edits.

The template therefore ships versioned scripts, run in order at step 8 for every
version greater than the project's current one and not greater than the target:

```
updates/
  v3.0.0/
    before.py   # runs on your working tree before the merge
    after.py    # runs after the merge
```

`before.py` typically performs `git mv` so the merge lines up; `after.py` rewrites
file contents. Both are ordinary Python run with `uv run`, and both must be
idempotent, because a failed update is re-run.

### 11.6 Knowing that an update exists

`just update-check` compares the recorded version against the newest template tag
and exits non-zero when the project is behind.

A scheduled workflow in every generated service runs it weekly, then does one of
two things — because a pull request cannot carry conflict markers:

- **Clean merge** — open a pull request titled
  `chore: update template v2.3.0 -> v2.5.0` with the template's changelog entries
  in the body. CI runs the full suite on it, so a template update is reviewed and
  verified exactly like any other change.
- **Conflicting merge** — open an issue instead, naming the conflicting paths and
  linking the changelog, telling the team to run `just update` locally.

This is the automation Renovate provides for libraries, applied to the template
itself.

### 11.7 Backstage compatibility

Backstage handles creation only. Its maintainers closed the request to update
components generated from software templates as *not planned*, so updates were
never going to live in the portal whichever engine PyFr used.

That matters here in one specific way. The Backstage scaffolder's cookiecutter
action runs `cookiecutter`, and a publish action then creates the repository with a
single initial commit — anything the hook did to local git history is discarded.
The mechanism above survives that untouched, because it needs only two things,
both of which hold:

1. `.pyfr-answers.yml` exists in the repository — the hook writes it as an ordinary
   file, not as git state.
2. The first commit is unmodified template output — exactly what the publish action
   creates.

A service created through Backstage is therefore updatable on the same terms as
one created from the command line, with no portal plugin work at all.

### 11.8 Engines considered and rejected

| Option | Why not |
|---|---|
| **cruft** | Purpose-built for this, and the least code to write. Rejected because its last release was 2024-12-25, roughly twenty months before this design — too dormant to carry a long-lived capability. It also applies patches rather than merging, so it fails on precisely the deleted example files every project has. |
| **Copier** | The healthiest of the three engines, with updates and cross-version migrations built in. Rejected because Backstage's only Copier action is an unpublished third-party plugin last touched in February 2024, so portal self-service would mean owning forked TypeScript, whereas cookiecutter's Backstage module is first-party and actively released. |
| **Manual diff procedure** | Documented regeneration and hand-application does not scale past a few services, and teams skip it in practice. |

---

## 12. Additional features included

**Runtime correctness — small code, prevents real incidents.**

1. **Health endpoints split three ways.** `/healthz` (liveness) checks only that
   the process is alive and **never** checks the database — if it did, a brief
   database problem would make Kubernetes restart every pod at once, turning a
   small outage into a large one. `/readyz` (readiness) checks database, cache and
   storage with short timeouts and removes the pod from load balancing when they
   fail. `/startupz` covers slow first starts.
2. **RFC 9457 Problem Details** — the IETF standard JSON error shape (`type`,
   `title`, `status`, `detail`, `instance`) with one handler mapping domain errors
   onto it.
3. **Correlation identifiers** — middleware reading the W3C `traceparent` header or
   `X-Request-ID`, binding it into structlog context variables and the
   OpenTelemetry span, and echoing it in the response.
4. **Graceful shutdown** on SIGTERM: stop accepting new requests, finish in-flight
   ones under a deadline, close pools. Without it every rolling deployment drops
   live requests.
5. **Outbound HTTP policy** — one shared `httpx` client with explicit connect and
   read timeouts, bounded retries with backoff, and a circuit breaker. A missing
   timeout is the most common way one slow dependency freezes a whole service.
6. **Log redaction** — a structlog processor masking configured field names, so
   `password` or `card_number` cannot reach Loki by accident. It sits in the shared
   processor chain (section 7.6), so it covers third-party records too.
7. **Fail-fast settings** and `just config-check` (section 5.1).

**Supply chain and security.** Dependency vulnerability scanning (`pip-audit`),
Trivy image scanning failing on high-severity findings, a CycloneDX SBOM produced
at build time, Renovate configuration for automated dependency updates, and a
hardened image: non-root user, no shell tools in the final stage,
`uv sync --locked` for reproducible installs, multi-architecture build so Apple
Silicon laptops and cloud servers share one image.

**Developer experience.** A `justfile` as the single entry point per task, so CI
runs the same commands a developer runs and "works locally, fails in CI" becomes
rare. Architecture Decision Records in `docs/adr/` with a template. A Backstage
`catalog-info.yaml`, which makes the README's existing integration claim true. A
seed-data command giving a working local environment on first `just up`.

---

## 13. Explicitly out of scope

| Excluded | Reason |
|---|---|
| A published runtime library | D1 — extract after real services exist |
| MySQL, MongoDB, Memcached, GCS, Azure Blob adapters | D8 — `docs/how-to/add-a-backend.md` covers writing them |
| Pact consumer-driven contracts | Needs consumer-team buy-in and a broker; unused scaffolding otherwise |
| A production observability platform | Section 7.1 — teams already have one |
| Message queues (Kafka, RabbitMQ, NATS) | A large subsystem deserving its own design round after v1 |
| Authentication and authorisation | Too organisation-specific to guess; a documented extension point instead |
| Multi-tenancy | Same reason |
| Kubernetes manifests / Helm, devcontainer, idempotency keys, rate limiting, k6 load tests | Deferred to M9 |
| cruft and Copier as update engines | Section 11.8 — dormancy and Backstage support respectively |

---

## 14. Milestones

Each milestone ends with something that runs and is tested. M0–M6 build the
reference service in plain Python, M7 converts it into the template, and M8 makes
generated projects updatable.

| # | Milestone | What exists at the end |
|---|---|---|
| **M0** | Walking skeleton | FastAPI app factory and lifespan, Pydantic Settings, structured logging in full (section 7.6: the standard-library bridge, the field-name contract, structured tracebacks, the replacement access log, configurable per-logger levels, and the console renderer for local work), the three health endpoints, Problem Details, correlation IDs, graceful shutdown, one example domain slice on an in-memory repository, unit tests with Hypothesis, `justfile`, ruff, mypy, import-linter, pre-commit, Dockerfile, compose. `just up` serves a working API. |
| **M1** | Persistence | golang-migrate end to end, the migrations image, SQLAlchemy async models and the PostgreSQL adapter, Testcontainers integration tests, all four schema gates. |
| **M2** | Observability | OpenTelemetry SDK and auto-instrumentation, trace-to-log correlation, the `o11y` compose profile, three dashboards, SLO recording rules and burn-rate alerts. |
| **M3** | Contract and test depth | `openapi.json` with its drift gate, Schemathesis, oasdiff plus the version cross-check, the outbound httpx client, VCR cassettes, mutmut configured. |
| **M4** | Cache and object storage | Redis adapter, S3 adapter over aioboto3, MinIO in compose, integration tests for both. |
| **M5** | Docs and release | MkDocs Material with the Diátaxis structure, the generated configuration reference, ADRs, runbook, all four hygiene checks, Commitizen and the release workflow, GitHub Pages, `catalog-info.yaml`, README rewritten (section 1.2). |
| **M6** | Supply chain | pip-audit, Trivy, SBOM, Renovate, multi-architecture builds, `uv sync --locked`, log redaction, `just config-check`, seed data. |
| **M7** | Templatise (Phase B) | Everything moves under `{{cookiecutter.project_slug}}/`; `cookiecutter.json` and both hooks; the `{% raw %}` and `_copy_without_render` passes; pytest-cookies generation tests across all 8 combinations; full-suite tests on 3; the golden diff; the template repository's own CI and release. Also `.pyfr-answers.yml`, written by the post-generation hook, and `_template_version` baked into `cookiecutter.json` — so no service is ever generated without the means to update itself later, even before M8 exists. **PyFr becomes a usable template here.** |
| **M8** | Template updates | The vendor branch and its reconstruction rule, `just update` and `just update-check`, `.pyfr-update-ignore` with the default split, the migration script runner, the weekly update workflow that opens a pull request or an issue, `docs/how-to/update-from-template.md`, and template-repository tests that generate at one version, edit the project the way a real team would, update to the next version, and assert the merge behaves — including that a deleted example slice stays deleted. |
| **M9** | Extras — out of scope for the first plan | Kubernetes manifests or Helm behind a flag, devcontainer, idempotency keys, rate limiting, k6 load tests. |

**M0 is deliberately usable on its own.** A service with no database, cache or
storage is a real thing people generate — an API gateway, an aggregator — so the
walking skeleton is a shipping product, not scaffolding.

---

## 15. Risks and mitigations

| Risk | Mitigation |
|---|---|
| Template and reference service drift apart | Golden diff test in CI (section 8.3); the template is the sole source of truth from Phase C |
| Jinja syntax collides with shipped file formats | `{% raw %}` and `_copy_without_render` (section 3.4), plus a generation test asserting no `{{` survives |
| CI runtime grows until people ignore it | Sample 3 of 8 combinations for full-suite runs; mutation testing on changed files only; slow work moves to nightly |
| VCR cassettes silently rot | `record_mode=none` in CI, weekly re-record job (section 8.1) |
| Path-coupling warnings become noise during refactors | Warnings by default, documented switch to hard failure per team (section 10.3) |
| A dirty migration blocks a deployment at a bad hour | Runbook entry and a dedicated how-to guide (section 6.4) |
| A migration numbered below the current version is silently skipped | Sequential numbering plus a CI collision check (section 6.4) |
| Alembic present but unused for migrations confuses readers | Prominent comments in `pyproject.toml` and the drift test explaining its single purpose (section 6.5) |
| The 14-feature scope stalls before anything ships | M0 is independently useful; each milestone ends runnable and tested |
| Someone hand-edits the `template` branch and breaks future merges | `just update` refuses to advance a branch carrying commits it did not create; the branch can always be rebuilt from the repository's first commit (section 11.2) |
| A squashed or rewritten history destroys the pristine first commit, so the branch cannot be reconstructed | `just update-check` detects it and points to a documented manual re-point procedure in `docs/how-to/update-from-template.md` |
| Teams that diverged heavily hit conflicts on every update and stop updating | The `.pyfr-update-ignore` default (section 11.4) keeps the frequently-rewritten paths out of the merge entirely; the weekly job opens an issue rather than an unmergeable pull request |
| Non-deterministic regeneration produces spurious diffs on the template branch | Regeneration mode suppresses the side-effectful half of the post-generation hook (section 11.3); the golden diff test already pins template output byte-for-byte |
| OTLP log export left enabled in production alongside a platform agent, doubling ingest volume and cost | Off by default; a comment on the setting and an explicit warning in the generated configuration reference (section 7.6) |
| A log field with unbounded distinct values overwhelms the log backend | The access log records `http.route` templates rather than raw paths, and health endpoints are excluded by default (section 7.6) |
| A third-party library logs a secret that call-site redaction would miss | Redaction is a processor in the shared chain, so it also covers standard-library records bridged from third-party code (section 7.6) |

---

## 16. Glossary

| Term | Meaning |
|---|---|
| ADR | Architecture Decision Record — a one-page note recording a decision, its context and consequences |
| ASGI | Asynchronous Server Gateway Interface — lets tests call the app directly with no network |
| Burn rate | How fast an error budget is consumed relative to the rate that would exactly exhaust it |
| Composition root | The single place where an application constructs and wires its dependencies |
| Conventional Commits | A commit message format (`feat:`, `fix:`, `feat!:`) machines can read to decide version bumps |
| Copier | A template engine with project updates built in; considered and rejected in section 11.8 |
| cruft | A tool adding update support to cookiecutter templates; considered and rejected in section 11.8 |
| Diátaxis | A documentation framework separating tutorials, how-to guides, reference and explanation |
| Drift gate | A CI check that fails when a generated artifact no longer matches the code that produces it |
| Entity | An object with an identity that persists through change |
| Error budget | The amount of failure an SLO permits, for example 0.1% of requests over 30 days |
| gitleaks | A scanner that blocks commits containing secrets |
| High cardinality | A field with an unbounded number of distinct values (a raw URL path, a user id); the usual way a metrics or log backend is overwhelmed |
| Init container | A container that runs to completion before the main application container starts |
| Log agent | A process run by the platform that reads containers' standard output and forwards it to a log store; Grafana Alloy, Fluent Bit and Promtail are examples |
| Merge base | The most recent commit two branches share; the "before" state a three-way merge compares both sides against |
| Mutation testing | Introducing small deliberate bugs to check whether tests actually catch them |
| oasdiff | A tool comparing two OpenAPI specifications, classifying changes as breaking or not |
| OTLP | OpenTelemetry Protocol — the wire format for traces, metrics and logs |
| Port and adapter | An interface owned by the domain (port) and a technology-specific implementation (adapter) |
| `ProcessorFormatter` | The structlog component installed on the standard library's root log handler so third-party records pass through the same processor chain |
| Property-based testing | Generating many random inputs to check a rule holds, rather than testing fixed examples |
| Protocol | Python's structural interface — satisfied by having the right methods, with no inheritance |
| RED metrics | Rate, Errors, Duration — the three signals a request-serving service needs |
| Repository | An interface for loading and saving entities, expressed in domain terms |
| Saturation | How full a limited resource is, such as a connection pool; predicts outages |
| SBOM | Software Bill of Materials — a machine-readable inventory of everything inside a built artifact |
| Semantic conventions | Agreed standard names for telemetry attributes, so dashboards work across languages |
| SemVer | Semantic Versioning — `MAJOR.MINOR.PATCH`, where major means a breaking change |
| SLI | Service Level Indicator — a measured number describing user-visible quality |
| SLO | Service Level Objective — the target for an SLI over a window |
| sqlfluff | A linter and formatter for SQL files |
| structlog | The structured logging library; each record is key/value data rendered at the end, not a pre-formatted string |
| Testcontainers | A library that starts real dependencies in Docker for the duration of a test run |
| Three-way merge | A merge using three inputs — the merge base, their version and yours — so a tool can tell "they changed it" apart from "you changed it" |
| Trivy | A scanner finding known vulnerabilities in container images |
| Use case | One business operation; orchestrates domain objects and holds no business rules itself |
| uv | A fast Python package and project manager written in Rust |
| Value object | An object defined only by its values, with no identity |
| Vendor branch | A branch holding pristine upstream (here, template) output and nothing else, merged in to receive upstream changes |
| VCR / cassette | Recording real HTTP responses to a file and replaying them in later test runs |
| Walking skeleton | A thin but complete end-to-end implementation, proving the architecture before adding features |
