# Roadmap

PyFr is built in nine milestones, M0 through M8. Every milestone ends with
something that runs and is tested — there is no stage where the project is
half-converted and nothing works.

**M0 is done.** Everything on this site describes code that exists today.

The last row of the table, M9, is not one of the nine. It is a holding place
for extras deliberately deferred out of the first plan, with no schedule
attached.

| | Milestone | State | What exists at the end |
| --- | --- | --- | --- |
| **M0** | Walking skeleton | **Done** | The application factory and lifespan, validated settings, structured logging, three health endpoints, Problem Details errors, correlation identifiers, graceful shutdown, one example domain slice on an in-memory repository, unit tests with property-based testing, the `justfile`, ruff, mypy, import-linter, pre-commit, the Dockerfile and compose. `just up` serves a working API. |
| **M1** | Persistence | Planned | Database migrations end to end, SQLAlchemy async models, the PostgreSQL adapter, integration tests against a real database in Docker, and four schema governance gates. |
| **M2** | Observability | Planned | OpenTelemetry and automatic instrumentation, trace-to-log correlation, a local Grafana stack behind a compose profile, three dashboards, and service level objective alerts. |
| **M3** | Contract and test depth | Planned | A committed OpenAPI document with a drift gate, generated conformance testing, a breaking-change gate, the shared outbound HTTP client, recorded HTTP cassettes, and mutation testing. |
| **M4** | Cache and object storage | Planned | The Redis adapter, the S3-compatible adapter, MinIO in compose, and integration tests for both. |
| **M5** | Docs and release | Planned | The Diátaxis documentation structure, a *generated* configuration reference, decision records, an on-call runbook, all four documentation hygiene checks, and automated releases. |
| **M6** | Supply chain | Planned | Dependency and image vulnerability scanning, a software bill of materials, automated dependency updates, multi-architecture builds, log redaction, and seed data. |
| **M7** | Templatise | Planned | The reference service becomes the template. Generation tests across all eight backend combinations, and the golden diff. **PyFr becomes a usable template here.** |
| **M8** | Template updates | Planned | A generated project can pull in later template versions through a git merge, with a weekly job that opens a pull request when one is available. |
| **M9** | Extras | Deferred, not one of the nine | Kubernetes manifests or Helm, a devcontainer, idempotency keys, rate limiting, load tests. |

## Why M0 ships on its own

A service with no database, cache, or object storage is a real thing people
build — an API gateway, an aggregator, a webhook receiver. The walking
skeleton is a product, not scaffolding.

A *walking skeleton* is a thin but complete end-to-end implementation: it
proves the architecture works before any features are added to it.

## The three phases

The milestones group into three phases, and the order is deliberate.

**Phase A (M0–M6)** builds `examples/reference-service/` as ordinary Python.
No template placeholders anywhere. Every hard problem is solved as a normal
engineering problem, in a codebase you can run and debug.

**Phase B (M7)** converts that tree into the template in one focused pass.

**Phase C** (after M7, permanently) makes the template the source of truth.
The reference service is regenerated from it, and the build fails if the
result differs from what is committed.

The rule behind this: **never debug Jinja and Python at the same time.**
More on that in [Why a template, not a
framework](explanation/why-a-template.md#the-build-order).

## What is deliberately excluded

Not "later" — decided against, with a reason.

| Excluded | Why |
| --- | --- |
| A published runtime library | Extract one after real services exist, when the right boundaries are visible rather than guessed. |
| MySQL, MongoDB, Memcached, GCS, Azure Blob adapters | A narrow set that is genuinely finished beats a long list that is half-working. [Add a backend](guides/add-a-backend.md) covers writing your own. |
| Consumer-driven contract testing | Pays off only with consumer-team buy-in and a hosted broker. Unused scaffolding otherwise. |
| A production observability platform | Teams already have one. PyFr emits standard telemetry and stops there. |
| Message queues | A large subsystem that deserves its own design round. |
| Authentication and authorisation | Too organisation-specific to guess. A documented extension point instead. |
| Multi-tenancy | Same reason. |

## Where the detail lives

The full design specification and the milestone implementation plans are in
[`docs/superpowers/`](https://github.com/EmadMokhtar/pyfr/tree/main/docs/superpowers)
in the repository. They are the reasoning behind the decisions this site
describes.

They are deliberately **not** published here. They are working documents
written for whoever is building a milestone at that moment, they run to
thousands of lines, and they go out of date by design once the milestone
lands. This site describes what is true now.
