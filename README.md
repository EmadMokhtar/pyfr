# PyFr

PyFr is a project template for Python microservices. You answer a short list of
prompts — service name, database, cache, object storage — and get a repository
that runs, is tested, is observable, and releases itself. The generated code is
owned entirely by the team that generated it; there is no PyFr package to import
and no runtime dependency on this repository.

It is influenced by [GoFr](https://gofr.dev), but it is not a port of it. GoFr is
a framework you import. PyFr is a template you generate from.

## Status

**Early. The template does not exist yet.**

What exists today is the design it will be built from, and the first milestone of
the service it will generate:

| | |
|---|---|
| [`examples/reference-service/`](examples/reference-service/) | A FastAPI walking skeleton. Runs, 102 tests pass, no database yet. |
| [Design specification](docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md) | The full design, M0–M8, with the decisions and their reasons. |
| [M0 implementation plan](docs/superpowers/plans/2026-08-28-pyfr-m0-walking-skeleton.md) | The task-by-task plan the reference service was built from. |

Cookiecutter prompts, generation hooks and the pruning logic arrive at M7. Until
then, the reference service is something you read and run, not something you
generate.

## Running the reference service

Needs [uv](https://docs.astral.sh/uv/) and Python 3.13.

```bash
cd examples/reference-service && uv run --frozen pytest
```

To serve it on <http://localhost:8000/docs>:

```bash
cd examples/reference-service && uv run --frozen uvicorn reference_service.main:create_app --factory --reload
```

Its own [README](examples/reference-service/README.md) covers the `just` recipes,
every environment variable, and the two traps worth knowing about — the
orchestrator kill deadline that silently overrides graceful shutdown, and why
pytest's `caplog` fixture captures nothing here.

### What M0 contains

The walking skeleton is a real service, not scaffolding — a gateway or an
aggregator needs no database. It has:

- A FastAPI app factory and lifespan, with settings validated at startup. Invalid
  configuration exits with code 78 and a readable message instead of failing as a
  500 later.
- Three separate health endpoints. `/healthz` never touches a dependency, so a
  brief database problem cannot make an orchestrator restart every pod at once;
  `/readyz` checks dependencies with short timeouts; `/startupz` covers slow
  first starts.
- Structured JSON logging on standard output, with the standard-library bridge,
  structured tracebacks, and an access log that records route templates
  (`/orders/{order_id}`) rather than raw paths.
- Errors as RFC 9457 Problem Details (the IETF standard JSON error shape:
  `type`, `title`, `status`, `detail`, `instance`).
- Correlation identifiers read from the W3C `traceparent` header or
  `X-Request-ID`, bound into the log context and echoed back.
- Graceful shutdown on SIGTERM, with the container's kill deadline set above the
  application's drain deadline.
- One domain slice — placing and fetching an order — on an in-memory repository,
  with property-based tests (Hypothesis generates inputs rather than you listing
  them by hand).

## How it is built

Four decisions carry most of the design. All of them are in the specification
with their full reasoning.

**A template, not a library.** Extracting a shared runtime package now would mean
guessing which abstractions are worth backward-compatibility promises before a
single real service has tested them. The extraction waits until three to five
services exist and the parts nobody ever edits are visible. The usual cost of
that choice — every fix re-applied by hand in every generated service — is paid
off by M8: a generated project pulls later template versions into itself through
a git three-way merge, so teams keep ownership of their code and still receive
template fixes.

**Reference service first, then templatise.** Every hard problem — the database
adapter, the OpenTelemetry wiring, the dashboards — is solved as ordinary Python
in `examples/reference-service/` before any Jinja templating exists, so nothing
is ever debugged through two layers at once. After the conversion the direction
reverses: the template becomes the source of truth and the reference service is
regenerated from it, which means the two cannot drift, and every pull request
shows what a template change did to real files instead of only to Jinja.

**Four layers, with the dependency rule enforced.** `domain` imports nothing but
Pydantic. `services` holds application logic. `infrastructure` is the only code
that knows a storage technology, `api` the only code that knows HTTP. The arrows
point inward, and `import-linter` fails the build when they stop doing so — the
rule is executable, not a paragraph in a style guide.

**Prompt and prune.** Cookiecutter asks per category and only the chosen adapter
is generated. A service that answered "no cache" has no Redis code, no Redis
dependency, and no empty directory where it would have gone. The generation tests
assert that no empty directory and no unused import survives.

## Roadmap

Each milestone ends with something that runs and is tested.

| | |
|---|---|
| M0 | Walking skeleton — **done** |
| M1 | Persistence — golang-migrate, SQLAlchemy async, Testcontainers, schema drift gates |
| M2 | Observability — OpenTelemetry, trace-to-log correlation, Grafana dashboards, SLO burn-rate alerts |
| M3 | Contract depth — OpenAPI drift gate, Schemathesis, breaking-change detection, outbound HTTP policy |
| M4 | Cache and object storage — Redis, S3-compatible over one adapter |
| M5 | Docs and release — MkDocs, ADRs, Commitizen, release workflow |
| M6 | Supply chain — pip-audit, Trivy, SBOM, Renovate, log redaction |
| M7 | Templatise — **PyFr becomes usable here** |
| M8 | Template updates — the vendor branch, `just update`, migration scripts |

Deliberately out of scope for v1: message queues, authentication and
authorisation, multi-tenancy, a published runtime library, and adapters beyond
PostgreSQL, Redis and S3-compatible storage. The specification records why for
each one.

## License

PyFr is licensed under the Mozilla Public License 2.0 — see [LICENSE](LICENSE).
Generated projects choose their own license when they are generated.
