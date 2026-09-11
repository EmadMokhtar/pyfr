---
last_reviewed: 2026-09-11
covers:
  - examples/reference-service/justfile
  - justfile
---

# Commands

Every task is a [`just`](https://github.com/casey/just) recipe. `just` is a
command runner: a `justfile` holds named recipes, and `just <name>` runs one.

The point is that continuous integration runs the *same* commands you run.
"Works on my machine, fails in the pipeline" becomes rare when there is only
one definition of what "lint" means.

Run `just` with no arguments to list the recipes.

## The reference service

Run these from `examples/reference-service/`.

| Command | What it does |
| --- | --- |
| `just install` | Sync dependencies from `uv.lock`. Same as `uv sync`. |
| `just dev` | Run with auto-reload on `APP_HTTP_PORT` (8000 by default). |
| `just test` | Run the test suite with pytest. |
| `just lint` | `ruff check` and `ruff format --check`. Reports; changes nothing. |
| `just fmt` | `ruff check --fix` and `ruff format`. Fixes what it can. |
| `just typecheck` | mypy. Strict on `domain/` and `services/`, lenient elsewhere. |
| `just imports` | import-linter: verify the [dependency rule](../explanation/layers.md). |
| `just precommit` | Run the pre-commit hooks over the project's tracked files. |
| `just check` | Everything above, then `git diff --exit-code`. Run this before pushing. |
| `just check-all` | Everything `just check` does, plus the container tier, all five schema gates and the configuration drift check, the SLO rule gates, and the contract gates. Needs Docker. |
| `just up` | Build the image and start the container stack. Once the API is healthy, a one-shot `seed` container creates five fixed orders through it — see [Getting started](../getting-started.md#start-with-data-in-it). |
| `just down` | Stop the stack and remove its volumes, the seed's state included. |
| `just seed` | Create the same five orders against a service on `localhost:${APP_HTTP_PORT}` (8000 by default) — for `just dev`, which the compose one-shot does not reach. Idempotent: the ids it issued are kept in `.seed-state.json` (ignored by git), and only an order that has gone missing is re-created. The compose one-shot and `just seed` keep separate state — a named volume versus `.seed-state.json` — so running `just seed` against the `just up` stack creates a second set of five orders; it is for `just dev`. |
| `just build-images` | Build both container images (the service and the migrations runner) for this machine's architecture without starting them, exactly as CI's `security` job and the release workflow do before scanning. |

## Observability

| Command | What it does |
| --- | --- |
| `just o11y` | Everything `just up` starts, plus Grafana, Prometheus, Tempo and Loki in one container, with the dashboards and SLO rules from `ops/` mounted in. Grafana is on <http://localhost:3000> with anonymous admin access — no login. |
| `just o11y-down` | Stop that stack and remove its volumes, telemetry included. |
| `just o11y-gates` | Validate the SLO rules with `promtool`: syntax first, then unit tests that feed synthetic series through the real rules and assert the numbers that come out. `promtool` runs from inside the pinned `grafana/otel-lgtm` image, so it needs no separate Prometheus install and can never drift from the version that actually evaluates the rules. The image name is read from `compose.yaml` through `docker compose config`, so the one pin there is the one the gate uses. |

See [Observability](observability.md) for what the dashboards show and how
the objectives are defined.

## The API contract

| Command | What it does |
| --- | --- |
| `just openapi` | Regenerate the committed `openapi.json` from the running app. Read the diff before committing it — it is your API change, stated completely. |
| `just test-contract` | The contract tier: generated conformance testing over ASGI (Schemathesis). Needs no Docker. The drift check runs in `just test` / `just check` instead. |
| `just contract-gates` | `just test-contract`, then the breaking-change check (`oasdiff` against `openapi.baseline.json`, cross-checked against the version in `pyproject.toml`). Needs Docker, for the `oasdiff` image. |
| `just contract-release` | Promote the current `openapi.json` to the baseline. Run this when cutting a release — never to make a red `contract-gates` pass. |

See [The API contract](contract.md) for what each of the three gates
catches and the workflow that goes with them.

## Configuration

| Command | What it does |
| --- | --- |
| `just config-docs` | Regenerate `.env.example` and the table in [Configuration](configuration.md) from `settings.py`'s `Field(description=...)`. Read the diff before committing it — it is your configuration change, stated completely. |
| `just config-docs-check` | Fail if either generated file has drifted from the settings model. Part of `just gates`. |
| `just config-check` | Print the configuration the service would start with, as one JSON object, with every `SecretStr` and every URL password masked — or exit 78 with the same message the service prints when it refuses to start. Reads `.env` as the service does. The same module runs inside the image: `docker compose run --rm app python -m reference_service.config_check`. Not a gate; a tool for [The service will not start](../runbook.md#the-service-will-not-start). |

`settings.py` is the single source of truth for every environment variable
this service reads. Hand-editing `.env.example` or the table in
[Configuration](configuration.md) instead of the model is what
`config-docs-check` exists to catch.

## Supply chain

| Command | What it does |
| --- | --- |
| `just audit` | pip-audit over every pinned version in `uv.lock`, against the PyPI advisory database. Reads a `uv export` with `--disable-pip --require-hashes`, so nothing is resolved or installed. Needs no Docker. |
| `just scan` | Trivy over both built images, for known vulnerabilities and embedded secrets. Fails on a HIGH or CRITICAL finding that has a fix; exemptions only through `.trivyignore.yaml`, and every one expires. Needs Docker, and the images from `just build-images`. |
| `just sbom` | A CycloneDX software bill of materials per image, into `sbom/` (ignored by git). Needs Docker, and the same images. |
| `just security` | `build-images`, then `audit`, `scan` and `sbom` — everything CI's `security` job runs, in the order it runs it. Needs Docker. Not part of `just check-all`, because its result changes with the advisory databases rather than with the code. |
| `just build-multiarch` | Build both images for `linux/amd64` and `linux/arm64` on a `docker-container` buildx builder, with no output — proof that both architectures still build, which is what CI's `build` job runs. Creates the builder (`pyfr`) on first use. |
| `just publish-images VERSION` | Build both platforms of both images and push them to GHCR, tagged `VERSION` and `latest`. Run by `release.yml` after `scan` has passed on the same commit's images; not something to run by hand against `ghcr.io`. |

The repository root has its own `just audit`, over the documentation
toolchain's lock — see [The documentation site](#the-documentation-site)
below. [Supply chain](supply-chain.md) says where each of these runs in CI and
what to do when one is red.

## Outbound HTTP and mutation testing

| Command | What it does |
| --- | --- |
| `just test-record` | Re-record the outbound HTTP cassettes against the local payment stub. Needs Docker, to start the stub. |
| `just mutants` | Mutation testing over `domain/` and `services/`. Slow relative to `just test`; run it when you have changed business logic and read the survivors, not the percentage. |
| `just mutants-changed` | The same, restricted to files changed against `main` — what a pull request actually needs. |
| `just mutants-gate` | Fail if the mutation score falls below the recorded floor (`pyproject.toml`'s `mutation_threshold_percent`). |

See [Outbound HTTP calls](../guides/outbound-http.md) for the retry policy,
the circuit breaker, and what the recorded cassettes do and do not prove.

## The database

These need Docker. The schema is owned by
[golang-migrate](https://github.com/golang-migrate/migrate) as plain SQL in
`migrations/`, applied by a container — nothing about applying it needs Python.

| Command | What it does |
| --- | --- |
| `just migrate` | Apply every outstanding migration. |
| `just migrate-new NAME` | Write a new `.up.sql` / `.down.sql` pair, numbered sequentially. |
| `just migrate-down N` | Roll back N steps. Defaults to one. |
| `just migrate-version` | The current version, and whether the database is dirty. |
| `just migrate-force V` | Clear a dirty flag by declaring the true version. Read the warning below first. |
| `just migrate-manifest` | Rebuild `migrations/manifest.sha256` after adding a migration. |
| `just schema-snapshot` | Regenerate the committed `schema.sql` after changing a migration. |
| `just psql` | An interactive `psql` session against the running stack. |

!!! danger "`just migrate-force` runs no SQL"

    It only overwrites the version recorded in `schema_migrations` and clears
    the dirty flag. A migration that fails partway leaves the database dirty,
    and golang-migrate then refuses every further command — correctly, because
    it cannot know how much of the failed file actually applied.

    Recovering means a human looking at the real schema, finishing or reversing
    the partial change by hand, and only then declaring the version that is
    genuinely applied. Running it first, to make the error go away, tells the
    tool a lie it will believe for the rest of the database's life.

## The cache and the object store

`just up` starts Redis and MinIO alongside PostgreSQL — neither is behind a
profile, so the containerised stack always exercises the same cached,
receipt-storing path production runs.

| Command | What it does |
| --- | --- |
| `just redis-cli` | An interactive `redis-cli` session against the running compose cache. |
| `just minio-console` | Print, and try to open, the MinIO web console at <http://localhost:9001> — log in with the local-only `minioadmin` / `minioadmin` credentials from `compose.yaml`. Use it to look at what the receipt store actually holds. |

The bucket itself is created by a one-shot `minio-bootstrap` container that
runs `mc mb` once MinIO reports healthy, because MinIO does not create a
bucket on demand and the application deliberately does not create its own —
that would need `CreateBucket` permission in production, on top of the
`GetObject`/`PutObject` the receipt store actually needs. `just up` waits for
`minio-bootstrap` to exit successfully before starting the API, the same
arrangement it already has with the migration container.

## Tests and schema gates

| Command | What it does |
| --- | --- |
| `just test` | Unit and API tests. Milliseconds, and needs no Docker. |
| `just test-integration` | The container-backed tier: real PostgreSQL, migrated by the real migrate image. |
| `just test-all` | Both tiers. |
| `just gates` | All five schema governance gates, plus `config-docs-check`. |

The five schema gates are the snapshot (`schema.sql` still matches the
migrations), reversibility (every `down.sql` truly reverses its `up.sql`),
version collisions, model drift (the SQLAlchemy models still match the real
schema), and the manifest (nobody edited a migration that has already been
applied somewhere). `config-docs-check` — the configuration reference's own
drift check, see [Configuration](#configuration) above — runs alongside them
in the same recipe, which is why editing `.env.example` by hand fails
`just gates` even though it touches no migration. They run from
`just check-all`, and CI's own `gates` job calls `just gates` directly.

### Why `just check` ends with a diff check

Several pre-commit hooks **rewrite** files: `ruff-format`, `uv-lock`,
`end-of-file-fixer`, `trailing-whitespace`. A hook that reformats your code
and then exits 0 has "passed" while leaving the tree different from what you
committed. Continuous integration would fail on the first run and pass on the
second, which teaches people to just press the button again.

`git diff --exit-code` afterwards turns any such rewrite into an explicit
failure. If `just check` fails there, run `just fmt`, commit the result, and
push again.

### Why `just precommit` uses `git ls-files`

The recipe is `pre-commit run --files $(git ls-files)`, not
`pre-commit run --all-files`. `--all-files` walks up to the *enclosing*
repository when this project sits inside one — which is exactly the situation
in this repository, where the service lives under `examples/`. It would
reformat files outside the service, including Python snippets inside Markdown
documents. `git ls-files` scopes the run to the service's own files.

In a standalone generated project the two are equivalent, so the recipe is
correct in both layouts.

## The documented examples

Run this from `examples/reference-service/`.

| Command | What it does |
| --- | --- |
| `just docs-examples` | Start the full compose stack, run every `curl` example marked in `docs/` against it, then tear the stack down — pass or fail. Needs Docker. |

This is an executable check on the documentation's own prose, not on the
code: breaking one of the documented examples, or the endpoint it calls,
fails the recipe. It is not part of `just check-all` — it runs as its own
`docs-examples` job in CI, against a stack that job starts itself.

## The documentation site

Run these from the repository root.

| Command | What it does |
| --- | --- |
| `just docs-install` | Install the documentation toolchain (`uv sync --group docs`). |
| `just docs` | Live preview on <http://127.0.0.1:8000>, rebuilding as you save. |
| `just docs-build` | Build the site into `site/` with `--strict`, exactly as CI does. |
| `just test` | Run this repository's own script tests (`tests/`) — the tests for `scripts/check_docs_freshness.py` and `scripts/check_doc_examples.py` themselves. Needs no Docker. |
| `just audit` | pip-audit over the root `uv.lock` — the documentation and release toolchain — with the same flags as the reference service's own `audit`. CI's `security` job runs both. |
| `just links` | Dead external links, via [`lychee`](https://github.com/lycheeverse/lychee). Needs the `lychee` binary locally (`brew install lychee`); CI's `links` job gets it from the action instead, against the same `lychee.toml`. |
| `just docs-freshness [base] [head]` | The **advisory** warnings only: a stale `last_reviewed` date, or a `covers:` path that changed while its page did not. Never fails. **This is not CI's `docs-freshness` job** — see [Documentation ships with the change](../contributing.md#documentation-ships-with-the-change) for which script each one runs. |
| `just changelog` | Preview the changelog entry the next release would write, from Conventional Commit history. Read-only. |
| `just next-version` | Preview the version number the next release would choose. Read-only — the release itself runs in CI (`.github/workflows/release.yml`). |
| `just check` | `docs-build` and `test`. Run before pushing a documentation or repository-tooling change. Same name as the reference service's own `just check` above, run from a different directory and checking different things — they are not interchangeable. |

`--strict` turns a warning into a failure. A link to a page that no longer
exists, a heading anchor that was renamed, an include that cannot be
resolved: each fails the build instead of printing a warning nobody reads.
Run `just docs-build` before pushing a documentation change.

!!! warning "Two different servers, one port"

    `just docs` and the service's `just dev` both default to port 8000. Stop
    one before starting the other, or set `APP_HTTP_PORT` to something else.
