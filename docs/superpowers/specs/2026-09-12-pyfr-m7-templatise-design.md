# PyFr M7 — Templatise (Phase B)

**Date:** 2026-09-12
**Extends:** [`2026-08-28-pyfr-cookiecutter-template-design.md`](2026-08-28-pyfr-cookiecutter-template-design.md)
— sections 3 (layout and phases), 8.3 (the template's own tests), 9 (the
generation interface), 10 (release, documentation, CI), 11.1 (what creation
records) and the M7 row of section 14.
**Status:** approved design, ready for an implementation plan.

M0–M6 built `examples/reference-service/` as ordinary Python, with no
template syntax anywhere. M7 converts that tree into the cookiecutter
template, makes the template the only source of truth, and proves it with a
golden diff. **PyFr becomes a usable template at the end of M7.**

---

## 1. Definition of done

M7 is done when all of the following are true on `main`:

1. `uvx cookiecutter gh:EmadMokhtar/pyfr` produces a project whose `just
   check` passes, for every one of the eight backend combinations, with no
   step in between.
2. `just regen --check` at the repository root passes: rendering the
   template with `tests/reference-answers.yaml` reproduces
   `examples/reference-service/` byte for byte, `uv.lock` excepted
   (section 4.3).
3. The eight-combination generation tests and the golden diff run on every
   push; the three-combination full-suite tests run on every merge to `main`
   and nightly.
4. A generated project carries its own `.github/` (CI, nightly, release,
   Dependabot, docs), its own MkDocs site, and all four documentation
   hygiene mechanisms (D10).
5. `docs/` describes PyFr — how to generate a service — and links to the
   reference service's generated site, built and deployed by the same
   workflow.
6. The roadmap marks M7 done and the release is `v0.7.0`, which is also the
   `_template_version` every generated project records.

---

## 2. Decisions fixed by this document

The 2026-08-28 specification's decisions D1–D15 stand. M7 adds the following.
Where one departs from that specification, the row says so and why.

| # | Decision | Rationale |
|---|---|---|
| M7-1 | **Move, templatise, regenerate.** `examples/reference-service/` is `git mv`'d to `{{cookiecutter.project_slug}}/` and templatised in place; `just regen` recreates `examples/reference-service/` from it. From the first M7 pull request the example is output, never edited by hand. | History follows the files; the template and the example cannot drift for even one pull request; every template change appears in review as a diff of real files. This is the specification's Phase C, applied from the first pull request rather than after the last. |
| M7-2 | **Twelve prompts; Python is fixed at 3.13; the two SLO prompts are dropped.** Section 9.1's list minus `python_version`, `slo_availability_target` and `slo_latency_ms`. *Departs from the specification.* | The service is built and tested on 3.13 only — `.python-version`, ruff's target, the Docker base image. A 3.12 prompt would double the full-suite matrix for a choice nobody has asked for. Adding the prompt later breaks no generated project. The SLO target and latency are threaded through `slo.py`, `otel.py`'s bucket boundaries, `slo.yml`, `slo_test.yml`, the copied-verbatim `slo.json` and two unit-test assertions — eight files of Jinja arithmetic for two prompts. The observability reference documents how to change the objective instead. |
| M7-3 | **The API contract is the same in every combination.** `object_storage=none` keeps `GET /orders/{id}/receipt` on the in-memory receipt store, exactly as `database=none` keeps the orders API on the in-memory repository (ADR 0005). Pruning removes adapters and their infrastructure, never endpoints. | `openapi.json` and `openapi.baseline.json` carry one substitution — the `title` is `{{ cookiecutter.project_slug }}`, because the app titles the document with `settings.service_name` — and no conditional, so the generation tests can assert they are byte-identical across all eight renders. A conditional JSON document was the riskiest file in the conversion. |
| M7-4 | **`uv.lock` is not template content.** The template ships no lock file. The golden diff excludes it; `uv lock --check` in the reference service's pre-commit configuration and CI keeps the committed lock consistent with the regenerated `pyproject.toml`. | A lock is the resolver's output for one dependency set, and pruning produces eight dependency sets. A lock cannot be a Jinja document. |
| M7-5 | **`.pyfr-answers.yml` is a rendered template file,** not written by the post-generation hook. *Departs from section 11.1's wording; the file's content is unchanged.* | Regeneration then covers it, and the release's bump commit — which moves `_template_version` — regenerates the example so the golden diff on `main` stays green. |
| M7-6 | **Two documentation sites, one deploy.** Pages about the service move into the template body; pages about PyFr stay at the root. PyFr's `docs.yml` builds both and deploys them as one site, the generated one under `reference-service/`. | One source for every page. Every deploy proves the generated site builds `--strict`. No mirror tree to maintain. |
| M7-7 | **Five staged pull requests.** Each leaves `main` runnable with the golden diff green; the roadmap marks M7 done only after the last. | The full conversion is roughly three times M6. A single pull request would be a fifteen-to-twenty-thousand-line review in which a late mistake costs the whole branch. |
| M7-8 | **Grafana dashboards are copied verbatim and identical in every combination.** A panel for a backend that is not present shows no data. | The dashboards select by the `$service` variable and contain Grafana's own `${...}` syntax; rendering them through Jinja for the sake of removing panels would trade a harmless empty panel for a fragile JSON template. |
| M7-9 | **The generated service's Commitizen is its own.** Commitizen moves from PyFr's root `dev` group to the generated `pyproject.toml`'s `dev` group; PyFr's root keeps its own copy for its own release. | A generated project has its own version, its own tags and its own release workflow, and the tool that decides its version must be in its own lock file (ADR 0014). |
| M7-10 | **`just adopt` copies Dependabot's edits back into the template.** Dependabot keeps pointing at `examples/reference-service/`; `scripts/regen.py --adopt` replaces, in the template file that renders it, each changed line of the example. The `golden` job runs it first on Dependabot pull requests; `adopt.yml` commits the same result to `main` after the merge. | Dependabot cannot parse Jinja. Pin lines never contain Jinja, so the replacement is literal; any other shape of change fails loudly and is made by hand. |

---

## 3. Repository layout after M7

```
pyfr/
  cookiecutter.json                   prompts, defaults, _copy_without_render, _template_version
  hooks/
    pre_gen_project.py                validate answers; exit 1 with a message before anything is written
    post_gen_project.py               prune; then, unless PYFR_REGEN is set: git init, uv sync,
                                      pre-commit install, first commit, next steps
  {{cookiecutter.project_slug}}/      the template body — today's examples/reference-service/
  examples/reference-service/         generated output for tests/reference-answers.yaml; committed;
                                      never hand-edited
  tests/
    reference-answers.yaml            the fixed answers: everything on, name "reference-service"
    test_generation.py                eight combinations, pruning invariants, hook behaviour
    test_generated_service.py         three combinations: generate, uv sync, run the generated suite
    test_golden.py                    render with the reference answers == the committed example
  scripts/regen.py                    `just regen` and `just regen --check`
  docs/                               PyFr's own site (section 9)
  justfile  pyproject.toml  uv.lock   root: docs toolchain, Commitizen, cookiecutter, pytest-cookies
  .github/workflows/{ci,docs,nightly,release,full-suite}.yml
  .github/dependabot.yml
  README.md  LICENSE  CHANGELOG.md
```

Cookiecutter renders only the directory whose name is a template variable.
`examples/`, `tests/`, `docs/`, `scripts/` and the root tool files are never
part of a generated project. A generated project is exactly one tree, named
by `project_slug`, with `package_name` as the package inside `src/`.

The example domain slice — the `Order` entity, its repository, service and
endpoints, and the receipt that hangs off it — lives inside the template
body and so *does* travel into every generated project. That is by design:
it is the worked example a team starts from and the first thing they delete
(section 11.4 of the original specification).

---

## 4. The regeneration loop and the golden diff

### 4.1 `scripts/regen.py`

`just regen` runs `scripts/regen.py`, which:

1. Reads `tests/reference-answers.yaml`.
2. Sets `PYFR_REGEN=1` in the environment and calls cookiecutter's Python
   API — `cookiecutter(".", no_input=True, extra_context=answers,
   output_dir=<temporary directory>)`. The render is a pure function of the
   template and the answers: the post-generation hook prunes and stops
   (section 5.3), so no `git init`, no `uv sync`, no network.
3. Syncs the render into `examples/reference-service/` with deletion, but
   leaves git-ignored paths alone (`.venv`, `.mypy_cache`, `.ruff_cache`,
   `.pytest_cache`, `.hypothesis`, `.import_linter_cache`) and does not touch
   `uv.lock` (section 4.3).

`just regen --check` renders and compares instead of writing. It fails
listing missing files, extra files and differing files, with a unified diff
of the first differing file, and exits 1. `tests/test_golden.py` and the
`golden` CI job call it.

`cookiecutter` and `pytest-cookies` join the root `dev` dependency group so
the script and the tests run through `uv run --group dev`. The root project
remains a toolchain, not a package.

### 4.2 The rule for contributors

**Edit the template, then `just regen`. Never edit
`examples/reference-service/` directly.** `contributing.md` says so; the
`golden` job enforces it: a hand edit to the example fails the build with a
diff showing exactly which file departed from the template.

### 4.3 What the golden diff excludes

One file: `examples/reference-service/uv.lock`. The template ships no lock
(M7-4). In a fresh project the post-generation hook's `uv sync` creates one.
The reference service keeps its committed lock, and the `uv lock --check`
pre-commit hook and CI job that already exist keep it consistent with the
regenerated `pyproject.toml`.

Everything else is template content and is compared — including the three
generated files `openapi.json`, `.env.example` and
`docs/reference/configuration.md`. `openapi.json` carries only the title
substitution (M7-3). `.env.example` and the configuration reference carry
`{% if %}` blocks per backend, and each is drift-gated *inside* the generated
project by the gate that already exists (`just config-docs-check`), so a
wrong conditional fails the full-suite run rather than shipping.

### 4.4 Regeneration in the release

`.github/workflows/release.yml` gains one step between `cz bump` and the
commit: `just regen`. Commitizen's `version_files` lists
`cookiecutter.json:_template_version` alongside `pyproject.toml`, so the bump
moves the template version, the regen writes the new version into the
example's `.pyfr-answers.yml`, and the bump commit carries both — the same
pattern that already promotes the contract baseline in that commit.

*Amended in PR 5.* `cz bump` writes the version files and commits in one
command, so no workflow step can sit between the two. The step is
Commitizen's `pre_bump_hooks` (`["just regen"]` in `pyproject.toml`), which
runs after `version_files` are written and before the bump commit; the
workflow's own `just regen` line went, and `cz bump` is passed
`--check-consistency` so a version it cannot find in `cookiecutter.json`
fails the release. `tests/test_release_bump.py` proves the order.

---

## 5. Prompts and hooks

### 5.1 Prompts

```
project_name              "My Service"
project_slug              derived: my-service
package_name              derived: my_service
description               one line
author_name
author_email
github_org
database                  postgres | none
cache                     redis | none
object_storage            s3 | none
http_port                 8000
license                   Apache-2.0 | MIT | MPL-2.0 | Proprietary
```

Private keys, never prompted: `_copy_without_render` (section 7) from PR 1;
`_template_version` (bumped by the release, section 4.4) from PR 2.

A prompt exists only once the template can honour it (section 12): the
three backend prompts arrive in the pruning pull request, not before.

### 5.2 `pre_gen_project.py`

Rejects, with one plain sentence each, before any file is written:

- `project_slug` not matching `^[a-z][a-z0-9-]*$`.
- `package_name` that is not a Python identifier, is a keyword, or is in
  `sys.stdlib_module_names` — a package named `email` or `types` breaks in
  ways that are confusing to debug.
- `http_port` outside 1–65535.

Exit code 1 with the message on standard error. Cookiecutter then writes
nothing.

### 5.3 `post_gen_project.py`

Two halves.

**Pruning** always runs. It deletes the files and directories the chosen
backends do not need (section 6) and then removes any directory left empty.
In PR 1 the only pruning is the licence: four `LICENSE.<choice>` files ship
in the template body and the hook keeps the chosen one as `LICENSE`.

**Side effects** run only when `PYFR_REGEN` is not set: `git init`, `uv
sync`, `uv run pre-commit install`, an initial commit, then a next-steps
message naming `just up` and the documentation. Every network step is
best-effort: a failed `uv sync` or `pre-commit install` prints the exact
command to run later and the hook still exits 0. An offline laptop must not
receive a half-deleted project, and a generation that has already pruned
must not be reported as failed for a reason unrelated to the template.

### 5.4 `.pyfr-answers.yml`

A rendered file at the generated project's root, content as section 11.1 of
the original specification (minus `python_version`), with
`_template_version` rendered from `cookiecutter.json`. M8 reads it to update
the project; nothing in M7 reads it.

---

## 6. Pruning rules

Two mechanisms, one invariant. Jinja `{% if %}` removes lines *inside* a
file. The post-generation hook removes *whole* files and directories.
Block tags stand on their own line in Jinja's left-strip form — `{%- if … %}`
… `{%- endif %}` — so a tag vanishes with its line and the everything-on
render stays byte-identical to the example; cookiecutter's environment does
not trim blocks, and `trim_blocks` would swallow the newline after the
justfile's inline `{% endraw %}` guards.
Conditionals are placed at file granularity wherever a whole module belongs
to one backend, so that line-level `{% if %}` appears only in the files that
mix backends: `pyproject.toml`, `compose.yaml`, `settings.py`,
`container.py`, `justfile`, `.importlinter`, `.pre-commit-config.yaml`,
`.trivyignore.yaml`, `.env.example`, the configuration reference, the
workflows, and the documentation pages that describe more than one backend.

**Invariant, enforced by the generation tests:** in a render with a backend
off, no file for that backend exists, no empty directory remains, no
dependency for it remains in `pyproject.toml`, no `import` of its libraries
(`sqlalchemy`, `asyncpg`, `alembic`, `redis`, `aioboto3`, `botocore`) and no
`infrastructure.<db|cache|storage>` reference remains in any `.py`, no
`APP_DATABASE__`/`APP_CACHE__`/`APP_STORAGE__` variable remains in
`.env.example` or any `.py`, no compose service and no recipe of it remains,
`ruff check` and `ruff format --check` pass on the render (an import a
conditional left behind fails `F401`), and no `{{` or `{%` survives
anywhere.

| Prompt = `none` | The hook deletes | `{% if %}` removes lines from |
|---|---|---|
| `database` | `migrations/`, `schema.sql`, `Dockerfile.migrations`, `.sqlfluff`, `src/<pkg>/infrastructure/db/`, `tests/unit/test_db_mappers.py`, `test_engine.py`, `test_migration_files.py`, `test_order_repository.py`, `tests/integration/test_order_repository.py`, `test_db_instrumentation.py`, `test_schema_drift.py`, `test_schema_gates.py` | `pyproject.toml` (sqlalchemy, asyncpg, alembic, the migrate tooling), `compose.yaml` (postgres, migrate, the migrations build), `settings.py`, `container.py`, `justfile` (`migrate-*`, `schema-snapshot`, `psql`, the schema gates in `gates`), `.importlinter`, `.pre-commit-config.yaml` (sqlfluff), `.trivyignore.yaml` (migrations image entries), `.env.example`, the configuration reference, `ci.yml` (schema and integration jobs), `dependabot.yml`, `main.py`, `observability/otel.py` (the SQLAlchemy instrumentor), `observability/metrics.py` (pool metrics), `tests/api/test_errors.py` (one test builds a `PostgresOrderRepository`), `tests/unit/test_container.py`, `tests/unit/test_metrics.py`, `tests/unit/test_settings.py`, `tests/unit/test_config_check.py`, `tests/unit/test_config_docs.py`, `tests/unit/test_compose_images.py`, `tests/integration/conftest.py` |
| `cache` | `src/<pkg>/infrastructure/cache/`, `tests/unit/test_cached_order_repository.py`, `tests/integration/test_cached_order_repository.py`, `test_redis_instrumentation.py` | `pyproject.toml` (redis), `compose.yaml` (redis), `settings.py`, `container.py`, `justfile` (`redis-cli`), `.importlinter`, `.env.example`, the configuration reference, `ci.yml`, `main.py` (`instrument_redis`), `observability/otel.py`, `tests/unit/test_container.py`, `tests/unit/test_config_docs.py`, `tests/unit/test_compose_images.py`, `tests/integration/conftest.py`, `tests/fakes.py` (`FakeRedis`) |
| `object_storage` | `src/<pkg>/infrastructure/storage/`, `tests/integration/test_receipt_store.py` | `pyproject.toml` (aioboto3), `compose.yaml` (minio, minio-bootstrap), `settings.py`, `container.py` (the S3 branch; the in-memory store remains), `justfile` (`minio-console`), `.importlinter`, `.env.example`, the configuration reference, `ci.yml`, `tests/unit/test_container.py`, `tests/unit/test_compose_images.py`, `tests/integration/conftest.py` |

`README.md` is not templated in PR 2; PR 4 rewrites it for a generated
project, and the invariant excludes it until then.

Never pruned: the in-memory adapters, the outbound HTTP client and its
WireMock stub, the observability stack, the receipt feature, seeding,
redaction, `config_check`, and the dashboards (M7-8).

`database=none` yields a service whose orders live in memory — an API
gateway or an aggregator, the M0 product. Its `/readyz` reports no
persistence dependency and its `ci.yml` has no schema jobs.

---

## 7. The Jinja collision pass

Cookiecutter renders every file through Jinja, which reads `{{` and `{%`
as its own syntax. Two mechanisms; one rule decides which: **does the
content need a prompt value?**

| File(s) | Contains | Handling |
|---|---|---|
| `justfile` | `{{name}}` recipe parameters | `{% raw %}` around the literal parts; the file must render because recipes are conditional on backends |
| `ops/prometheus/rules/slo.yml` | `{{ $labels.job }}` in annotations | `{% raw %}`; the file must render because the service name in its annotations is a prompt value |
| `.sqlfluff` | `{{ }}` in its templater settings | `{% raw %}` (the file is deleted when `database=none`) |
| `tests/integration/test_observability_stack.py` | `{{ }}` in query strings | `{% raw %}` |
| `.github/workflows/*.yml` (new in the template) | `${{ secrets.GITHUB_TOKEN }}`, `${{ matrix.* }}` | `{% raw %}`; the workflows are conditional on backends |
| `ops/grafana/dashboards/*.json`, `ops/grafana/provisioning/dashboards/*.yaml` | Grafana `${service}` variable syntax; a comment containing `{{ }}` | `_copy_without_render`; byte-identical in every project (M7-8) |

The generation test asserting that no `{{` or `{%` survives in any render is
what keeps this table from rotting: a future file that trips the collision
fails the fast tests, on every push.

---

## 8. A generated project's `.github/`

Derived from PyFr's root workflows by removing the PyFr-only jobs, then
templatised. A generated project's workflows are real from day one; the
reference service's copy at `examples/reference-service/.github/` is output
and inert, since GitHub runs workflows only from a repository's root.

| File | Content | Conditional on |
|---|---|---|
| `ci.yml` | The service's jobs from today's root `ci.yml`: fast gates, unit and api tests, integration, schema gates, contract gates, SLO gates, docs examples, security, image build, docs build | Schema jobs on `database`; the Redis and MinIO integration jobs on their backends |
| `nightly.yml` | Mutation testing, the link sweep, re-audit, re-scan | — |
| `release.yml` | Today's root workflow, with the bootstrap branch now *live*: a generated project starts at `0.1.0` with no tags, so its first release takes exactly the path this repository took for `v0.5.0`. Publishes images under `ghcr.io/{{ github_org }}/{{ project_slug }}` | — |
| `dependabot.yml` | The five ecosystems | — (one entry per ecosystem, per directory; nothing in it is per service) |
| `docs.yml` | Build the project's MkDocs site with `--strict` and deploy it to GitHub Pages | — |

Amended during PR 3: the table describes the end state. The
documentation-dependent jobs and `docs.yml` arrive with PR 4, together
with the site, the hygiene scripts and `lychee.toml` they read (section
12). Dependabot's `github-actions` ecosystem reads `/.github/workflows`
only, so the pins in the template's workflows are adopted from PyFr's
root workflows by `just adopt` — M7-10's mechanism, in the other
direction — and a root test holds the two equal.

Commitizen becomes a `dev` dependency of the generated `pyproject.toml`
(M7-9), with `version_provider = "uv"` so a bump rewrites both that
file's version and the matching entry in `uv.lock`. The
`[tool.commitizen]` table, the commit-message hook in
`.pre-commit-config.yaml` and the `changelog` and `next-version` recipes move
into the template body with it.

The generated project's `LICENSE` follows the `license` prompt from PR 1
onward: the Apache-2.0, MIT or MPL-2.0 text, or a one-paragraph proprietary
notice, with the author's name and no year — a year would change the
reference render every January.

---

## 9. Documentation

### 9.1 The split

Pages move by whom they describe.

**Stays at the root — about PyFr:** `index.md`, `getting-started.md`
(rewritten: install `uv`, run `uvx cookiecutter gh:EmadMokhtar/pyfr`, answer
the prompts, `just up`), `roadmap.md`, `contributing.md` (rewritten around
the template: `just regen`, the golden diff, the generation tests, the
collision table), `glossary.md` (the PyFr terms), `explanation/why-a-template.md`,
ADRs 0002 and 0003, and a new ADR 0017 (section 9.3).

**Moves into the template body — about the generated service:**
`guides/*`, `reference/*`, `runbook.md`, `explanation/architecture.md`,
`layers.md`, `testing.md`, ADRs 0001 and 0004–0016, the service half of the
glossary. Each is templatised: the service name, the package name and the
GitHub organisation become prompt values, and sections about one backend sit
inside `{% if %}`.

The three hygiene scripts — `check_docs_updated.py`,
`check_docs_freshness.py`, `check_doc_examples.py` — and their tests move
into the template body's `scripts/` and `tests/`, because D10 gives every
generated project all four mechanisms and a generated project cannot reach
PyFr's scripts. For PyFr's own root pages, the same three checks run from
`examples/reference-service/scripts/` — generated output, identical to the
template's, with no second copy to drift. The root `tests/` then holds only
the generation, golden and full-suite tests.

### 9.2 Two sites, one deploy

The template body gains `mkdocs.yml` (Material, the Diátaxis navigation,
`site_url: !ENV [SITE_URL, "https://{{ github_org }}.github.io/{{ project_slug }}/"]`)
and a `docs` dependency group with `just docs`, `docs-build` and `links`
recipes.

PyFr's `docs.yml` builds its own site into `site/`, then builds
`examples/reference-service/` with `--strict` and
`SITE_URL=https://emadmokhtar.github.io/pyfr/reference-service/` into
`site/reference-service/`, and deploys the one directory. Root pages link
to `reference-service/` as "the documentation a generated service ships".
MkDocs resolves `!ENV` tags natively; the default keeps a generated
project's own deploy correct with nothing to set.

### 9.3 ADR 0017

*The template is the source of truth, and a golden diff proves it.* Context:
Phase A built the service as plain Python so no one debugged Jinja and
Python at once; Phase B must not let the two trees drift. Decision: M7-1 and
M7-4. Consequences: contributors edit the template and regenerate; the
example is reviewable output; `uv.lock` is the one file outside the diff.

### 9.4 Root pages that change

- `roadmap.md`: M7 "In progress" from the first pull request, **Done** in
  the last; the M7 row rewritten to what shipped.
- `README.md`: the status line and badge move to "usable template" in the
  last pull request; the quick start becomes the cookiecutter command.
- `index.md`: the status admonition; a link to the reference service's
  site.

---

## 10. Tests

All at the repository root, all run through `uv run --group dev pytest`,
with `pytest-cookies` providing the `cookies` fixture that renders into a
temporary directory.

### 10.1 Generation tests — every push, under a minute

`tests/test_generation.py`, parametrised over all eight combinations of
`database`, `cache` and `object_storage`, asserting for each render:

- The pruning invariant of section 6, as refined there.
- `pyproject.toml` parses and lists only the chosen backends' dependencies.
- `compose.yaml` parses and names only the chosen services.
- `openapi.json` and `openapi.baseline.json` are byte-identical to the
  everything-on render (M7-3).
- `.importlinter` parses and every contract names a package that exists.
- `.pyfr-answers.yml` parses and records the answers given.
- No `{{` or `{%` in any file.
- No `.git` directory, no `.venv`, no lock (the hook's side-effect half did
  not run under `PYFR_REGEN`).
- `ruff check` and `ruff format --check` pass on the render, with the
  render's own `ruff.toml`.

And, once each: every `pre_gen_project.py` rejection in section 5.2 fires
with its message and leaves no directory behind; the side-effect half
without `PYFR_REGEN` creates a git repository with one commit (network
steps mocked to fail, proving best-effort).

### 10.2 The golden diff — every push

`tests/test_golden.py` calls `scripts/regen.py --check` and asserts exit
code 0. The `golden` CI job runs the same command.

### 10.3 Full-suite tests — on merge to `main`, nightly, on demand

`tests/test_generated_service.py`, marked `full_suite` and deselected by
default, over three combinations: everything on; everything off; PostgreSQL
only. For each: render without `PYFR_REGEN` so the hook runs `uv sync`,
then run the generated project's `just check` and, because Docker is
available on the runner, `just check-all`. Three syncs and three full gate
runs are too slow for every push; on merge and nightly they prove that every
render the generation tests call well-formed is also a service that passes
its own gates.

### 10.4 What is not tested here

ruff, mypy and import-linter cannot run on the template body: it is not
valid Python until rendered. They run on the reference service on every
push, as today, and on the three sampled renders on merge. A conditional
that produces an unused import in some other combination is caught by the
section 6 invariant's import check, which is a text check, not a linter.

---

## 11. PyFr's own CI and release

`ci.yml` keeps every existing job — they run against
`examples/reference-service/` through `working-directory`, unchanged — and
adds `golden` (`just regen-check`); the generation tests run in the `docs`
job's root `just check` rather than in a job of their own, so only the
golden diff has its own job; `docs` is extended to build both sites.
`full-suite.yml` is a separate workflow: `push` to `main`, a nightly
schedule and `workflow_dispatch`.
`release.yml` gains the regen step of section 4.4. `docs.yml` is section
9.2.

One tag series, as today: `v0.7.0` is "M7 done" and is the
`_template_version` a project generated from it records. A generated
project's version is its own.

---

## 12. Delivery — five pull requests

Each leaves `main` runnable and the golden diff green.

| PR | Lands | Prompts live afterwards |
|---|---|---|
| 1 — skeleton | `git mv examples/reference-service '{{cookiecutter.project_slug}}'`; `cookiecutter.json` (without `_template_version`, which arrives with `.pyfr-answers.yml`); both hooks with an empty pruning half; the collision pass (section 7); `scripts/regen.py`, `just regen`, `tests/reference-answers.yaml`, `test_golden.py`; the identity, port, organisation and licence substitutions throughout the tree; a `.gitignore` for generated projects; `just adopt` and `adopt.yml` (M7-10); a root `.pre-commit-config.yaml`; `cookiecutter` and `pytest-cookies` in the root `dev` group; the `golden` CI job, with the generation tests in the `docs` job's root `just check`; roadmap "In progress". | identity, `http_port`, `license` |
| 2 — pruning | The three backend prompts; `{% if %}` and hook deletions per section 6; the eight-combination tests of section 10.1; `.pyfr-answers.yml`; `_template_version: 0.6.0` in `cookiecutter.json` until PR 5 wires its bump. | all twelve |
| 3 — generated `.github/` | Section 8's `ci.yml`, `nightly.yml`, `release.yml` and `dependabot.yml`, without the jobs that need the project's own documentation site (`docs`, `docs-freshness`, `docs-warnings`, `links`, `docs-examples`) — those and `docs.yml` land with the site in PR 4, so no generated workflow ever references a file the project does not have; Commitizen moves (M7-9); the reference service's `.github/` appears as output; the template's action pins follow the root's through `just adopt` (Dependabot's `github-actions` ecosystem reads `/.github/workflows` only). | — |
| 4 — docs split | Section 9 in full; `docs.yml` builds both sites; the hygiene scripts move; root pages rewritten; a generated project's `docs.yml` and the documentation jobs of its `ci.yml` and `nightly.yml`. | — |
| 5 — done | Full-suite tests and `full-suite.yml`; `_template_version` with the release's regen step; ADR 0017; roadmap **Done**; README status; `v0.7.0`. | — |

PR 1 is the largest by line count — it contains the moved tree — and the
smallest by risk: with no pruning yet, the everything-on render must equal
the tree that was moved, which the golden diff proves before any
conditional exists.

---

## 13. Error handling

| Where | Failure | Behaviour |
|---|---|---|
| `pre_gen_project.py` | An answer fails validation | Exit 1, one sentence on standard error, nothing written |
| `post_gen_project.py`, side effects | `uv sync`, `pre-commit install` or the initial commit fails | Print the exact command to run later; exit 0; the project is complete and pruned |
| `post_gen_project.py`, pruning | A path to delete does not exist | Exit 1 with the path — the pruning table and the tree have diverged, and the generation tests must catch it before a user does |
| `scripts/regen.py --check` | Any difference | Exit 1; lists missing, extra and differing files; unified diff of the first differing file |
| `scripts/regen.py` | The template does not render | Exit 1 with cookiecutter's own message unchanged — it names the file and line |
| Full-suite test | A generated project's gate fails | The test fails with that gate's output; the combination is named in the test id |

---

## 14. Risks

| Risk | Answer |
|---|---|
| Someone edits `examples/reference-service/` by hand | The `golden` job fails with the diff; `contributing.md` states the rule (section 4.2) |
| Jinja inside Python hurts readability | File-granularity pruning wherever possible; line-level `{% if %}` confined to the files section 6 lists |
| A wrong `{% if %}` in `.env.example` or the configuration reference | Parsed by the eight-combination tests; drift-gated inside the generated project by `config-docs-check`, which the full-suite run executes |
| `uv.lock` outside the golden diff | `uv lock --check` on the reference service gates it against the regenerated `pyproject.toml` on every push, as today |
| Full-suite time grows until ignored | Three of eight, on merge only; the eight render tests stay under a minute |
| Empty Grafana panels for absent backends (M7-8) | Documented in the observability reference; the alternative was a rendered JSON dashboard |
| The moved tree loses `git blame` | `git mv` preserves history through rename detection; the example's history restarts, and its files' history lives on in the template body |
| `_copy_without_render` file names still render | The dashboard and provisioning file names contain no template syntax; the generation tests would fail on a surviving `{{` if one were added |
| Dependabot edits the rendered example | `just adopt` in the `golden` job and `adopt.yml` after the merge (M7-10); a change `adopt` cannot express fails with the file name and is made in the template by hand |

---

## 15. Out of scope for M7

- Template updates for generated projects — M8, which consumes
  `.pyfr-answers.yml` and the vendor branch of section 11 of the original
  specification.
- A `python_version` prompt (M7-2).
- Kubernetes manifests, a devcontainer, and everything else in M9.
- Publishing PyFr to a template registry or Backstage; the generation
  command is `uvx cookiecutter gh:EmadMokhtar/pyfr`.
- Removing panels from the dashboards per backend (M7-8).

---

## 16. Glossary

| Term | Meaning |
|---|---|
| Template body | The directory `{{cookiecutter.project_slug}}/` — the only tree cookiecutter renders |
| Render | One run of cookiecutter over the template body with one set of answers |
| Reference answers | `tests/reference-answers.yaml`: the fixed answers the committed example is rendered from — everything on, named `reference-service` |
| Regenerate | Render with the reference answers and sync the result into `examples/reference-service/` |
| Golden diff | The check that a regeneration changes nothing — the template and the example agree byte for byte |
| Pruning | Removing the files, lines and dependencies of a backend the user did not choose |
| `PYFR_REGEN` | The environment variable that makes the post-generation hook prune and stop, with no git, network or virtual-environment side effects |
| Collision | A file whose own syntax uses `{{` or `{%`, which Jinja would otherwise interpret |
| `_copy_without_render` | Cookiecutter's list of paths copied byte for byte instead of rendered |
| Full suite | Generating a project without `PYFR_REGEN` and running its own `just check` and `just check-all` |
| Adopt | Copying a line changed in the rendered example back into the template file that renders it — the reverse direction, used only for Dependabot's pin changes |
