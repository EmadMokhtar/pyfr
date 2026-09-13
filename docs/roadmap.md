---
last_reviewed: 2026-09-12
---

# Roadmap

PyFr is built in nine milestones, M0 through M8. Every milestone ends with
something that runs and is tested — there is no stage where the project is
half-converted and nothing works.

**M0, M1, M2, M3, M4, M5 and M6 are done; M7 is in progress.** Everything on this site describes code that exists today.

The last row of the table, M9, is not one of the nine. It is a holding place
for extras deliberately deferred out of the first plan, with no schedule
attached.

| | Milestone | State | What exists at the end |
| --- | --- | --- | --- |
| **M0** | Walking skeleton | **Done** | The application factory and lifespan, validated settings, structured logging, three health endpoints, Problem Details errors, correlation identifiers, graceful shutdown, one example domain slice on an in-memory repository, unit tests with property-based testing, the `justfile`, ruff, mypy, import-linter, pre-commit, the Dockerfile and compose. `just up` serves a working API. |
| **M1** | Persistence | **Done** | Database migrations end to end, SQLAlchemy async models, the PostgreSQL adapter, integration tests against a real database in Docker, and four schema governance gates. |
| **M2** | Observability | **Done** | OpenTelemetry and automatic instrumentation, trace-to-log correlation, a local Grafana stack behind a compose profile, three dashboards, and service level objective alerts. |
| **M3** | Contract and test depth | **Done** | A committed OpenAPI document with a drift gate, generated conformance testing, a breaking-change gate, the shared outbound HTTP client, recorded HTTP cassettes, and mutation testing. |
| **M4** | Cache and object storage | **Done** | A fail-open Redis cache as a decorator over the order repository, an S3-compatible receipt store over aioboto3, Redis and MinIO in compose, a two-tier `/readyz` that reports optional dependencies without gating on them, `GET /orders/{id}/receipt`, and integration tests against real Redis and MinIO containers. |
| **M5** | Docs and release | **Done** | A *generated* configuration reference — `settings.py`'s `Field(description=...)` is the single source of truth for all 38 environment variables, with `docs/reference/configuration.md`'s table and `.env.example` generated from it and drift-gated in `just gates`; `lychee` external link checking, executable `curl` examples run against a live stack, and advisory warnings for stale review dates and `covers:` path coupling, alongside the `mkdocs build --strict` check that already existed; twelve architecture decision records and an on-call runbook; Commitizen, a `CHANGELOG.md` generated from history, version `0.5.0` and a release workflow; the contract gate's version comparison replaced by a Conventional Commits range check; and continuous integration for the reference service, which had none before — `ci.yml` grown from two jobs to eleven, plus a nightly workflow for mutation testing and a full link sweep. The Diátaxis structure and GitHub Pages this site already used arrived earlier, in M0-era work — M5 did not build them, only added to what they already published. |
| **M6** | Supply chain | **Done** | Dependency auditing with `pip-audit` over both lockfiles, Trivy scanning of both images failing on fixed HIGH and CRITICAL findings with expiring exemptions, a CycloneDX SBOM per image attached to every release, multi-architecture (`amd64` and `arm64`) images published to GHCR on release under the repository's version, Dependabot across five ecosystems with every duplicated tool and image pin collapsed into the one file it updates, log redaction as a processor in the shared chain, `just config-check`, and seed data so `just up` yields orders. pip is removed from the runtime image; the migrate base moved to v4.20.1. |
| **M7** | Templatise | **In progress** | The reference service becomes the template in five pull requests. The first moved the tree under `{{cookiecutter.project_slug}}/`, added `cookiecutter.json` with the identity, port and licence prompts, both hooks, `just regen` and the golden diff that makes the template the source of truth (ADR 0017). Still to come: backend prompts and pruning, a generated project's own workflows, its own documentation site, and the full-suite tests. Until the documentation site moves into the template, a generated project's `just check` fails its two configuration-reference tests, which look for `docs/reference/configuration.md` at the repository root. **PyFr becomes a usable template at the end of M7.** |
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

**Phase B (M7)** converts that tree into the template. The golden diff that
makes the template the source of truth starts with M7's first pull request
(ADR 0017): the reference service is regenerated from it, and the build
fails if the result differs from what is committed.

**Phase C** (after M7, permanently) keeps the two in step forever after.

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
| `catalog-info.yaml`, a Backstage service-catalogue file | M5's specification justified it as making the README's Backstage integration claim true, but the README rewrite removed that claim. There is nothing left to justify, no portal to register with, and no service anyone deploys to describe. If Backstage ever matters here, it is template content for M7, not documentation for M5. |
| A weekly job re-recording outbound HTTP cassettes | `just test-record` records against a committed, deterministic local WireMock stub, not a real upstream. A scheduled re-record against a stub that never changes would produce an empty diff every week, forever. |
| A distroless runtime image | No maintained free Python 3.13 distroless with pinned tags, and the start command needs a shell to expand the port. Scanning the slim image is the mitigation; see [ADR 0016](adr/0016-image-scanning-fails-on-fixed-findings-and-exemptions-expire.md). |

## Where the detail lives

The full design specification and the milestone implementation plans are in
[`docs/superpowers/`](https://github.com/EmadMokhtar/pyfr/tree/main/docs/superpowers)
in the repository. They are the reasoning behind the decisions this site
describes.

They are deliberately **not** published here. They are working documents
written for whoever is building a milestone at that moment, they run to
thousands of lines, and they go out of date by design once the milestone
lands. This site describes what is true now.
