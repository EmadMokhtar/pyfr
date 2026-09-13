# PyFr M7 PR 2 — Backend Prompts and Pruning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add the three backend prompts (`database`, `cache`, `object_storage`) and make every one of the eight combinations render a project with no trace of the backends it did not choose — no dependency, no import, no setting, no compose service, no recipe, no test that needs it — proven by a generation-test matrix that runs on every push.

**Architecture:** Two pruning mechanisms with one invariant (spec §6). Jinja `{%- if %}` blocks remove lines *inside* mixed files — `pyproject.toml`, `compose.yaml`, `settings.py`, `container.py`, `main.py`, `otel.py`, `metrics.py`, `justfile`, `.importlinter`, `.pre-commit-config.yaml`, `.trivyignore.yaml`, `.env.example`, and the tests that mix backends. `hooks/post_gen_project.py` deletes whole files and directories that belong to one backend, from a table keyed by the three answers. `tests/test_generation.py` becomes a matrix over the eight combinations and asserts the invariant precisely: the chosen backends' dependencies, imports, settings groups, compose services and files are present; the unchosen ones are absent; `ruff check` and `ruff format --check` are clean on every render (an unused import left by a conditional fails `F401`); no Jinja survives; `openapi.json` is identical across the matrix. The everything-on render stays byte-identical to the example (`just regen-check`), which is what makes each conditional safe to add one at a time. `.pyfr-answers.yml` and `_template_version` arrive with the prompts.

**Tech Stack:** cookiecutter, Jinja2 (left-strip block tags `{%- if %}`), pytest-cookies, ruff (run from the root environment on each render), pyyaml, tomllib, configparser.

**Spec:** [`docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md`](../specs/2026-09-12-pyfr-m7-templatise-design.md) — sections 5.1 (prompts), 5.3 (the hook's pruning half), 5.4 (`.pyfr-answers.yml`), 6 (pruning rules), 10.1 (generation tests), 12 (the PR 2 row); decisions M7-3 (one contract for every combination) and M7-8 (dashboards copied verbatim). Task 1 amends §6 with what this plan found in the code. GitHub issue: opened by Task 1.

---

## Decisions taken while planning (Task 1 writes them into the spec)

| # | Decision | Why |
|---|---|---|
| Whitespace | Block tags stand on their own line in the **left-strip** form — `{%- if … %}`, `{%- elif … %}`, `{%- else %}`, `{%- endif %}` — never `{% if %}` and never `-%}`. Verified in cookiecutter's own `StrictEnvironment`: the tag and the newline before it vanish, the content keeps its indentation, and the inline `{% raw %}` guards in the justfile are unaffected. | Cookiecutter's environment does not trim blocks; a bare `{% if %}` leaves a blank line in the render, and the everything-on render must equal the example byte for byte. `trim_blocks` would also eat the newline after the justfile's inline `{% endraw %}`. |
| The invariant, precisely | "Its name appears nowhere" (spec §6) is refined to what a machine can check without templating prose: for an unchosen backend, no dependency in `pyproject.toml`, no `import`/`from … import` of its libraries in any `.py`, no `infrastructure.<db\|cache\|storage>` reference, no `APP_<DATABASE\|CACHE\|STORAGE>__` variable in `.env.example` or any `.py`, no compose service, no recipe, none of its files; plus `ruff check` and `ruff format --check` clean on the render. A comment or a test string that mentions "postgres is down" is prose and stays. | Templating every prose mention would spread Jinja into places that gain nothing; the checks above are what a wrong conditional actually breaks. |
| Prompt defaults | `database: ["postgres", "none"]`, `cache: ["redis", "none"]`, `object_storage: ["s3", "none"]` — the first choice is cookiecutter's default, so a `--no-input` render is the everything-on project, the same shape as the example. | A default of "everything on" matches what the documentation describes. |
| `object_storage=none` keeps the receipt feature | On the in-memory store, as M7-3 decided; only `infrastructure/storage/`, its integration test, its settings group, its compose services and its recipes go. | The contract is identical across the matrix; the generation tests assert it. |
| `database=none` keeps the migrations *runner* image out entirely | `Dockerfile.migrations`, `migrations/`, `schema.sql`, `.sqlfluff`, the `migrate` compose service and the `migrate-*`/`schema-snapshot`/`psql` recipes, the sqlfluff hook, the migrations-image entries in `.trivyignore.yaml`, the `-migrations` image in `justfile`'s build/scan/sbom/publish recipes. | Nothing runs migrations without a database. |
| `README.md` stays untouched in this PR | Its prose names all three backends; PR 4 rewrites it for a generated project. The invariant excludes it. | Two PRs editing the same prose is churn; PR 4 owns it. |

## Global Constraints

Every task's requirements implicitly include these.

- **The template is the source of truth.** Edit `{{cookiecutter.project_slug}}/`, run `just regen`, commit the example's regenerated files with the template edit. `just regen-check` must be green at every commit. Never edit `examples/reference-service/` by hand.
- **The everything-on render is the example.** With `tests/reference-answers.yaml` (which Task 1 extends with `database: postgres`, `cache: redis`, `object_storage: s3`) the render must equal the example byte for byte, `uv.lock` excepted. So every conditional added must render to *nothing extra* when its backend is on — the left-strip convention above.
- **Block tags on their own line, left-strip form only.** `{%- if cookiecutter.database == "postgres" %}` … `{%- endif %}`. Inline conditionals inside a line are forbidden in Python, YAML and TOML files (they defeat `ruff format` and readers); allowed only where a single token differs inside one line of a shell recipe, and then written `{% if … %}…{% endif %}` without dashes.
- **Substitution and conditionals only; no new logic in the template body.** A conditional wraps code that already exists; it never introduces code the everything-on render lacks.
- **`hooks/post_gen_project.py` deletes whole files and directories**; Jinja removes lines. A path that belongs entirely to one backend is deleted by the hook, never emptied by Jinja.
- **No `{{`/`{%` survives any render** (the existing test), and **`ruff check` + `ruff format --check` are clean on all eight renders** (this plan's matrix test).
- **`openapi.json` and `openapi.baseline.json` are byte-identical across all eight renders** (M7-3).
- **Python `>=3.13`; uv for everything; line length 88; root `just lint` clean; root tests never need Docker or network** (renders happen in `tmp_path` under `PYFR_REGEN`; ruff runs from the root environment).
- **Conventional Commits.** Branch `claude/m7-pr2-pruning` from `origin/main` (339dfb5 or later) in this worktree. Open a tracking issue first; the PR closes it. Assign the PR to `EmadMokhtar` (bare login). Push over HTTPS with `git -c credential.helper='!gh auth git-credential' push https://github.com/EmadMokhtar/pyfr.git <branch>` if the SSH agent is still refusing to sign.
- **Commits by a sub-agent carry that agent's attribution line**; the controller's commits carry `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.

## Verified facts

1. In cookiecutter's `StrictEnvironment` (no `trim_blocks`), `a\n{%- if x %}\nb\n{%- endif %}\nc\n` renders to `a\nb\nc\n` when `x` is true and `a\nc\n` when false; an indented `    {%- if %}` line vanishes entirely and the content keeps its own indentation; `{% raw %}{{name}}{% endraw %}` mid-line is unaffected. (Checked 2026-09-13 with the root environment's cookiecutter.)
2. Cookiecutter reads a list-valued prompt as a choice list whose first element is the default.
3. The template body already branches on the settings at runtime: `container.py` (`if settings.database is None`, `if settings.cache is not None`, `if settings.storage is not None`), `main.py` (`instrument_redis` called unconditionally, `instrument_database` only with an engine), `metrics.py` (`_register_pool_metrics` only with an engine). The conditionals in this plan wrap exactly those blocks and their imports.
4. Third-party backend imports (from a grep of the template body): `sqlalchemy`/`asyncpg`/`alembic` in `container.py`, `infrastructure/db/*`, `observability/metrics.py`, `observability/otel.py`, `tests/integration/conftest.py`, `tests/integration/test_db_instrumentation.py`, `test_order_repository.py`, `test_schema_drift.py`, `tests/unit/test_container.py`, `tests/unit/test_metrics.py`; `redis` in `container.py`, `infrastructure/cache/*`, `observability/otel.py`, `tests/integration/conftest.py`, `test_cached_order_repository.py` (unit and integration), `test_redis_instrumentation.py`, `tests/unit/test_container.py`; `aioboto3`/`botocore` in `infrastructure/storage/*` only (the container imports the store's builders; `tests/integration/conftest.py` and `test_receipt_store.py` import `infrastructure.storage`).
5. Internal `infrastructure.(db|cache|storage)` imports: `container.py` (all three), `infrastructure/db/mappers.py` and `order_repository.py` (db), `tests/api/test_errors.py` (db — builds a real `PostgresOrderRepository` for one error-mapping test), `tests/integration/conftest.py` (all three), the per-backend integration tests, `tests/unit/test_container.py` (all three), `tests/unit/test_db_mappers.py`, `test_engine.py`, `test_order_repository.py` (db), `tests/unit/test_cached_order_repository.py` (cache).
6. Settings groups: `DatabaseSettings` (`settings.database`, `APP_DATABASE__*`), `CacheSettings` (`settings.cache`, `APP_CACHE__*`), `StorageSettings` (`settings.storage`, `APP_STORAGE__*`), each `| None = None` on `Settings`. `tests/unit/test_settings.py:204`, `test_config_check.py:59` and `test_config_docs.py:166-167` reference `APP_DATABASE__DSN`/`APP_CACHE__DSN`.
7. `pyproject.toml` dependencies: `sqlalchemy[asyncio]`, `asyncpg`, `opentelemetry-instrumentation-sqlalchemy` (database); `redis`, `opentelemetry-instrumentation-redis` (cache); `aioboto3` (object storage); dev: `alembic` (database), `testcontainers[postgres,redis,minio]` (the extras follow the backends; the package stays while any backend is on and goes when all are off — no other test uses it). No `opentelemetry-instrumentation-botocore` (a comment explains why). Corrected during execution: `testcontainers` stays in every render — `tests/integration/test_observability_stack.py` imports it; the invariant asserts its extras equal the chosen backends.
8. `compose.yaml` services: `postgres`, `migrate` (database); `redis` (cache); `minio`, `minio-bootstrap` (object storage); `app` (`depends_on` the chosen ones), `seed`, `payment-stub`, `lgtm` (profile `o11y`), `trivy` (profile `tools`); volumes `postgres-data`, `minio-data`, `seed-state`, `trivy-cache`. `tests/unit/test_compose_images.py:9` lists the pinned services `postgres`, `redis`, `minio`, `lgtm`, `trivy`, `payment-stub`.
9. `justfile` backend recipes: `schema-snapshot`, `migrate`, `migrate-new`, `migrate-manifest`, `migrate-down`, `migrate-version`, `migrate-force`, `psql` (database); `redis-cli` (cache); `minio-console` (object storage); the `-migrations` image appears in `build-images`, `build-multiarch`, `scan`, `sbom`, `publish-images`, `scan-published`, `promote-latest` and in `gates`/`check-all` compositions — read the file before editing.
10. `.importlinter` lists `sqlalchemy`, `asyncpg`, `redis`, `aioboto3` twice (two contracts). `.pre-commit-config.yaml` has the `sqlfluff-lint` hook (`files: ^migrations/.*\.sql$`). `.trivyignore.yaml`'s entries all target `usr/local/bin/migrate` in the migrations image.
11. `ops/prometheus/prometheus.yaml:54-57` drops `postgresql.*` labels — prose-level configuration, harmless without a database; left alone. `ops/grafana/**` is copied verbatim (M7-8).
12. `scripts/generate_config_docs.py` maps `PostgresDsn`/`RedisDsn` to labels — a generic table that stays.
13. The root `dev` group has `ruff`; `uv run --group dev ruff check <dir>` on a render picks the render's own `ruff.toml` (nearest config). `tests/test_generation.py` already runs it at the 25-character cap through `subprocess` with `sys.executable -m ruff` (or `shutil.which("ruff")`) — reuse that helper.
14. `main` on 2026-09-13 (`339dfb5`) carries PR 1. The `Release` workflow has failed on every push since #24 because the repository ruleset on `main` requires a pull request and the workflow token has no bypass; no tag beyond `v0.6.0` exists. Not this PR's concern, but do not expect a release to run.

---

## File structure

**Created**
| Path | Responsibility |
|---|---|
| `{{cookiecutter.project_slug}}/.pyfr-answers.yml` | Records the answers and `_template_version` for M8 (spec §5.4) |

**Modified**
| Path | Change |
|---|---|
| `cookiecutter.json` | `database`, `cache`, `object_storage` choice prompts; `_template_version` |
| `hooks/post_gen_project.py` | The pruning table and its deletion loop |
| `tests/reference-answers.yaml` | The three backend answers |
| `tests/test_generation.py` | The eight-combination matrix and the invariant |
| `tests/test_hooks.py` | Pruning-table behaviour |
| `{{cookiecutter.project_slug}}/**` | `{%- if %}` blocks in the mixed files listed per task |
| `examples/reference-service/**` | Regenerated (`.pyfr-answers.yml` appears) |
| `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md` | §6 corrected to the code; the whitespace convention |
| `docs/contributing.md`, `docs/roadmap.md`, `docs/getting-started.md`? (no — PR 4), `docs/reference/commands.md` | The convention, the matrix test, the M7 row |

---

### Task 1: Branch, issue, spec amendments, and the prompts (no pruning yet)

**Files:**
- Modify: `cookiecutter.json`, `tests/reference-answers.yaml`, `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md`
- Create: `{{cookiecutter.project_slug}}/.pyfr-answers.yml`
- Modify: `tests/test_generation.py` (the matrix fixture and two tests)
- Regenerate: `examples/reference-service/.pyfr-answers.yml`

**Interfaces:**
- Produces: prompt keys `database` ∈ {`postgres`,`none`}, `cache` ∈ {`redis`,`none`}, `object_storage` ∈ {`s3`,`none`}; `COMBINATIONS` and `render(cookies, **answers)` in `tests/test_generation.py`; `_template_version` (`0.6.0` — the last tag; PR 5 wires the bump).

- [ ] **Step 1: Branch and issue**

```bash
git checkout -b claude/m7-pr2-pruning origin/main
gh issue create --assignee EmadMokhtar \
  --title "feat: m7 pr 2 — backend prompts and pruning across the eight combinations" \
  --body "Second of the five M7 pull requests (spec §12): the database, cache and object_storage prompts; Jinja and hook pruning per spec §6; the eight-combination generation tests; .pyfr-answers.yml and _template_version. Plan: docs/superpowers/plans/2026-09-13-pyfr-m7-pr2-pruning.md."
```

Record the issue number for Task 7.

- [ ] **Step 2: Amend the spec**

In `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md`:

1. Section 6, first paragraph, after "The post-generation hook removes *whole* files and directories.", add: "Block tags stand on their own line in Jinja's left-strip form — `{%- if … %}` … `{%- endif %}` — so a tag vanishes with its line and the everything-on render stays byte-identical to the example; cookiecutter's environment does not trim blocks, and `trim_blocks` would swallow the newline after the justfile's inline `{% endraw %}` guards."
2. Section 6, the "**Invariant, enforced by the generation tests:**" paragraph: replace "its name (`postgres`, `asyncpg`, `sqlalchemy`, `redis`, `minio`, `aioboto3`, `s3`) appears nowhere outside the documentation's "what is deliberately excluded" wording" with "no `import` of its libraries (`sqlalchemy`, `asyncpg`, `alembic`, `redis`, `aioboto3`, `botocore`) and no `infrastructure.<db|cache|storage>` reference remains in any `.py`, no `APP_DATABASE__`/`APP_CACHE__`/`APP_STORAGE__` variable remains in `.env.example` or any `.py`, no compose service and no recipe of it remains, `ruff check` and `ruff format --check` pass on the render (an import a conditional left behind fails `F401`)".
3. Section 6 table, `database` row, "The hook deletes" cell: replace the list with `migrations/`, `schema.sql`, `Dockerfile.migrations`, `.sqlfluff`, `src/<pkg>/infrastructure/db/`, `tests/unit/test_db_mappers.py`, `test_engine.py`, `test_migration_files.py`, `test_order_repository.py`, `tests/integration/test_order_repository.py`, `test_db_instrumentation.py`, `test_schema_drift.py`, `test_schema_gates.py`. In its `{% if %}` cell add `main.py`, `observability/otel.py` (the SQLAlchemy instrumentor), `observability/metrics.py` (pool metrics), `tests/api/test_errors.py` (one test builds a `PostgresOrderRepository`), `tests/unit/test_container.py`, `tests/unit/test_metrics.py`, `tests/unit/test_settings.py`, `tests/unit/test_config_check.py`, `tests/unit/test_config_docs.py`, `tests/unit/test_compose_images.py`, `tests/integration/conftest.py`; remove "ADR 0004, the migrations guide content" and "the runbook's dirty-migration procedure, `add-a-backend.md`" (documentation moves in PR 4).
4. `cache` row: "The hook deletes" = `src/<pkg>/infrastructure/cache/`, `tests/unit/test_cached_order_repository.py`, `tests/integration/test_cached_order_repository.py`, `test_redis_instrumentation.py`; `{% if %}` cell add `main.py` (`instrument_redis`), `observability/otel.py`, `tests/unit/test_container.py`, `tests/unit/test_config_docs.py`, `tests/unit/test_compose_images.py`, `tests/integration/conftest.py`, `tests/fakes.py` (`FakeRedis`); remove "ADR 0006" and the readiness/runbook mentions.
5. `object_storage` row: "The hook deletes" = `src/<pkg>/infrastructure/storage/`, `tests/integration/test_receipt_store.py`; `{% if %}` cell add `tests/unit/test_container.py`, `tests/unit/test_compose_images.py`, `tests/integration/conftest.py`; remove the readiness-page mention.
6. Section 6, after the table: add "`README.md` is not templated in PR 2; PR 4 rewrites it for a generated project, and the invariant excludes it until then."
7. Section 10.1: replace "The pruning invariant of section 6, in full." with "The pruning invariant of section 6, as refined there." and add the bullet "`ruff check` and `ruff format --check` pass on the render, with the render's own `ruff.toml`."
8. Section 12, PR 2 row: append "; `_template_version: 0.6.0` in `cookiecutter.json` until PR 5 wires its bump".

- [ ] **Step 3: The prompts and the answers**

`cookiecutter.json` — insert after `"github_org"`:

```json
  "database": ["postgres", "none"],
  "cache": ["redis", "none"],
  "object_storage": ["s3", "none"],
```

and after `"license"`:

```json
  "_template_version": "0.6.0",
```

`tests/reference-answers.yaml` — add after `github_org`:

```yaml
database: postgres
cache: redis
object_storage: s3
```

and replace its comment's last sentence ("PR 2 adds the three backend answers when their prompts exist.") with "Everything on: the three backend answers name the adapters the example has carried since M1, M4 and M4."

- [ ] **Step 4: `.pyfr-answers.yml`**

Create `{{cookiecutter.project_slug}}/.pyfr-answers.yml`:

```yaml
# Written by PyFr when this project was generated. M8's `just update` reads
# it to re-render the template at a newer version and merge the result;
# nothing else does. Keep it committed and unedited.
_template: https://github.com/EmadMokhtar/pyfr
_template_version: "{{ cookiecutter._template_version }}"
project_name: "{{ cookiecutter.project_name }}"
project_slug: "{{ cookiecutter.project_slug }}"
package_name: "{{ cookiecutter.package_name }}"
description: "{{ cookiecutter.description }}"
author_name: "{{ cookiecutter.author_name }}"
author_email: "{{ cookiecutter.author_email }}"
github_org: "{{ cookiecutter.github_org }}"
database: "{{ cookiecutter.database }}"
cache: "{{ cookiecutter.cache }}"
object_storage: "{{ cookiecutter.object_storage }}"
http_port: "{{ cookiecutter.http_port }}"
license: "{{ cookiecutter.license }}"
```

Every value is double-quoted; `pre_gen_project.py` already refuses a double quote or a backslash in the free-text answers, so the file is always valid YAML.

- [ ] **Step 5: The matrix fixture and two tests**

In `tests/test_generation.py`, after `REFERENCE_ANSWERS`, add:

```python
BACKENDS = {
    "database": ("postgres", "none"),
    "cache": ("redis", "none"),
    "object_storage": ("s3", "none"),
}
# The eight combinations, as the extra_context dicts pytest-cookies takes.
COMBINATIONS = [
    {"database": db, "cache": cache, "object_storage": storage}
    for db in BACKENDS["database"]
    for cache in BACKENDS["cache"]
    for storage in BACKENDS["object_storage"]
]
EVERYTHING_ON = COMBINATIONS[0]


def combination_id(answers: dict[str, str]) -> str:
    return "-".join(answers[key] for key in ("database", "cache", "object_storage"))


def render(cookies, **answers: str):
    result = cookies.bake(extra_context=answers)
    assert result.exit_code == 0, result.exception
    return result.project_path
```

Then two tests:

```python
@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_every_combination_renders_and_records_its_answers(cookies, answers) -> None:
    root = render(cookies, **answers)
    recorded = yaml.safe_load((root / ".pyfr-answers.yml").read_text())
    assert recorded["_template_version"] == "0.6.0"
    assert recorded["_template"] == "https://github.com/EmadMokhtar/pyfr"
    for key, value in answers.items():
        assert recorded[key] == value
    assert recorded["package_name"] == "my_service"


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_the_contract_is_the_same_in_every_combination(cookies, answers) -> None:
    root = render(cookies, **answers)
    reference = render(cookies, **EVERYTHING_ON)
    for name in ("openapi.json", "openapi.baseline.json"):
        assert (root / name).read_bytes() == (reference / name).read_bytes()
```

Also change the existing `test_no_template_syntax_survives_the_default_render` into a matrix test: parametrise it over `COMBINATIONS` (same ids) and render with `render(cookies, **answers)` instead of `cookies.bake()`; keep its body. Rename it `test_no_template_syntax_survives_any_combination`.

- [ ] **Step 6: Regenerate, run, commit**

```bash
just regen
git add examples/reference-service
uv run --group dev pytest tests -q
just lint && just regen-check
```

Expected: the example gains `.pyfr-answers.yml` and nothing else changes; every test passes (24 matrix cases render — pruning does nothing yet, so every combination is the everything-on tree). Commit:

```bash
git add cookiecutter.json tests/reference-answers.yaml '{{cookiecutter.project_slug}}/.pyfr-answers.yml' tests/test_generation.py docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md examples/reference-service
git commit -m "feat(template): add the backend prompts, .pyfr-answers.yml and the generation matrix"
```

---

### Task 2: The invariant test and the hook's pruning table

**Files:**
- Modify: `tests/test_generation.py` (the invariant), `hooks/post_gen_project.py` (the table), `tests/test_hooks.py`

**Interfaces:**
- Produces: `hooks/post_gen_project.py::PRUNED` — `dict[tuple[str, str], list[str]]` keyed by `(answer_key, "none")` → template-relative paths (directories end with `/`); `prune(root)` deletes them for each answer equal to `"none"`. `tests/test_generation.py::assert_invariant(root, answers)`.

- [ ] **Step 1: Write the invariant (it fails for every combination with a backend off)**

Append to `tests/test_generation.py`:

```python
import subprocess
import sys
import tomllib

PACKAGE = "my_service"

# Per backend: the libraries a render must not import, the ones .importlinter
# names, the settings group's variable prefix, the compose services, the
# justfile recipes, the dependencies and the paths the hook deletes. Only
# .py files, .env.example, .importlinter, compose.yaml, pyproject.toml and
# the justfile are inspected; prose (README.md, comments) is not.
BACKEND = {
    "database": {
        "libraries": ("sqlalchemy", "asyncpg", "alembic"),
        "importlinter": ("sqlalchemy", "asyncpg"),
        "package": "db",
        "env_prefix": "APP_DATABASE__",
        "services": ("postgres", "migrate"),
        "recipes": (
            "schema-snapshot", "migrate", "migrate-new", "migrate-manifest",
            "migrate-down", "migrate-version", "migrate-force", "psql",
        ),
        "dependencies": (
            "sqlalchemy", "asyncpg", "alembic",
            "opentelemetry-instrumentation-sqlalchemy",
        ),
        "paths": (
            "migrations/", "schema.sql", "Dockerfile.migrations", ".sqlfluff",
            f"src/{PACKAGE}/infrastructure/db/",
            "tests/unit/test_db_mappers.py", "tests/unit/test_engine.py",
            "tests/unit/test_migration_files.py",
            "tests/unit/test_order_repository.py",
            "tests/integration/test_order_repository.py",
            "tests/integration/test_db_instrumentation.py",
            "tests/integration/test_schema_drift.py",
            "tests/integration/test_schema_gates.py",
        ),
    },
    "cache": {
        "libraries": ("redis",),
        "importlinter": ("redis",),
        "package": "cache",
        "env_prefix": "APP_CACHE__",
        "services": ("redis",),
        "recipes": ("redis-cli",),
        "dependencies": ("redis", "opentelemetry-instrumentation-redis"),
        "paths": (
            f"src/{PACKAGE}/infrastructure/cache/",
            "tests/unit/test_cached_order_repository.py",
            "tests/integration/test_cached_order_repository.py",
            "tests/integration/test_redis_instrumentation.py",
        ),
    },
    "object_storage": {
        "libraries": ("aioboto3", "botocore", "boto3"),
        "importlinter": ("aioboto3",),
        "package": "storage",
        "env_prefix": "APP_STORAGE__",
        "services": ("minio", "minio-bootstrap"),
        "recipes": ("minio-console",),
        "dependencies": ("aioboto3",),
        "paths": (
            f"src/{PACKAGE}/infrastructure/storage/",
            "tests/integration/test_receipt_store.py",
        ),
    },
}
IMPORT = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE)
INFRA = re.compile(r"infrastructure\.(db|cache|storage)\b")


def python_files(root: Path) -> list[Path]:
    return [p for p in files_under(root) if p.suffix == ".py"]


def imported_top_levels(path: Path) -> set[str]:
    return {m.group(1).split(".")[0] for m in IMPORT.finditer(path.read_text())}


def compose_services(root: Path) -> set[str]:
    return set(yaml.safe_load((root / "compose.yaml").read_text())["services"])


def dependency_names(root: Path) -> set[str]:
    data = tomllib.loads((root / "pyproject.toml").read_text())
    names = set()
    groups = [data["project"]["dependencies"], *data.get("dependency-groups", {}).values()]
    for group in groups:
        for spec in group:
            if isinstance(spec, str):
                names.add(re.split(r"[\[<>=!~; ]", spec, maxsplit=1)[0].lower())
    return names


def recipe_names(root: Path) -> set[str]:
    return {
        m.group(1)
        for m in re.finditer(r"^([A-Za-z_][\w-]*)(?:\s+[^:\n]*)?:(?!=)", (root / "justfile").read_text(), re.M)
    }


def ruff(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # The root environment's ruff (a dependency of the `dev` group); run in
    # the render, so ruff picks the render's own ruff.toml.
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args, "."],
        cwd=root,
        capture_output=True,
        text=True,
    )


def assert_invariant(root: Path, answers: dict[str, str]) -> None:
    services = compose_services(root)
    dependencies = dependency_names(root)
    recipes = recipe_names(root)
    env_example = (root / ".env.example").read_text()
    importlinter = (root / ".importlinter").read_text()
    for key, spec in BACKEND.items():
        on = answers[key] != "none"
        for path in spec["paths"]:
            assert (root / path).exists() == on, (key, path, on)
        for service in spec["services"]:
            assert (service in services) == on, (key, service, on)
        for recipe in spec["recipes"]:
            assert (recipe in recipes) == on, (key, recipe, on)
        for dependency in spec["dependencies"]:
            assert (dependency in dependencies) == on, (key, dependency, on)
        assert (spec["env_prefix"] in env_example) == on, (key, "env")
        for library in spec["importlinter"]:
            assert (library in importlinter) == on, (key, library, ".importlinter")
        if on:
            continue
        for path in python_files(root):
            text = path.read_text()
            imports = imported_top_levels(path)
            assert not imports & set(spec["libraries"]), (key, path.relative_to(root))
            assert not any(
                m.group(1) == spec["package"] for m in INFRA.finditer(text)
            ), (key, path.relative_to(root))
            assert spec["env_prefix"] not in text, (key, path.relative_to(root))
    # Cross-cutting: nothing empty, nothing unformatted, nothing unused.
    for directory in (p for p in root.rglob("*") if p.is_dir()):
        assert any(directory.iterdir()), f"empty directory {directory.relative_to(root)}"
    check = ruff(root, "check")
    assert check.returncode == 0, check.stdout + check.stderr
    fmt = ruff(root, "format", "--check")
    assert fmt.returncode == 0, fmt.stdout + fmt.stderr
    # testcontainers is needed by exactly the integration tests the chosen
    # backends keep; with every backend off it has no user.
    any_on = any(answers[key] != "none" for key in BACKEND)
    assert ("testcontainers" in dependencies) == any_on


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_a_render_carries_only_the_backends_it_chose(cookies, answers) -> None:
    assert_invariant(render(cookies, **answers), answers)
```

Reconcile the `ruff` helper with the one Task 6 of PR 1 already added for the cap test (`test_a_package_name_at_the_cap_is_format_clean`): keep one helper, used by both.

- [ ] **Step 2: Run it**

```bash
uv run --group dev pytest tests/test_generation.py -q -k carries_only
```

Expected: `postgres-redis-s3` PASSES (everything on: every path exists, every service and dependency present, ruff clean — the example passes its own `just lint`); the other seven FAIL on the first `paths` assertion (`(key, path, on)` with `on=False` and the path present). If `postgres-redis-s3` fails, the invariant's tables disagree with the tree — fix the table, not the tree.

- [ ] **Step 3: The hook's pruning table**

In `hooks/post_gen_project.py`, add after `LICENCE_FILES`:

```python
DATABASE = "{{ cookiecutter.database }}"
CACHE = "{{ cookiecutter.cache }}"
OBJECT_STORAGE = "{{ cookiecutter.object_storage }}"
PACKAGE = "{{ cookiecutter.package_name }}"

# Whole files and directories that belong to one backend. Jinja removes lines
# inside mixed files; everything here is deleted outright when its answer is
# "none". Directories end with "/". tests/test_generation.py carries the same
# table and asserts that each path exists exactly when its backend is chosen.
PRUNED: dict[str, list[str]] = {
    "database": [
        "migrations/",
        "schema.sql",
        "Dockerfile.migrations",
        ".sqlfluff",
        f"src/{PACKAGE}/infrastructure/db/",
        "tests/unit/test_db_mappers.py",
        "tests/unit/test_engine.py",
        "tests/unit/test_migration_files.py",
        "tests/unit/test_order_repository.py",
        "tests/integration/test_order_repository.py",
        "tests/integration/test_db_instrumentation.py",
        "tests/integration/test_schema_drift.py",
        "tests/integration/test_schema_gates.py",
    ],
    "cache": [
        f"src/{PACKAGE}/infrastructure/cache/",
        "tests/unit/test_cached_order_repository.py",
        "tests/integration/test_cached_order_repository.py",
        "tests/integration/test_redis_instrumentation.py",
    ],
    "object_storage": [
        f"src/{PACKAGE}/infrastructure/storage/",
        "tests/integration/test_receipt_store.py",
    ],
}
ANSWERS = {"database": DATABASE, "cache": CACHE, "object_storage": OBJECT_STORAGE}


def prune_backends(root: Path) -> None:
    for key, answer in ANSWERS.items():
        if answer != "none":
            continue
        for relative in PRUNED[key]:
            path = root / relative.rstrip("/")
            if not path.exists():
                # The table and the tree have diverged; fail loudly so the
                # generation tests catch it before a user does.
                sys.exit(f"pruning: {relative} is missing from the template body")
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
```

Add `import shutil`. Call `prune_backends(root)` in `main()` after `keep_chosen_licence(root)` and before `remove_empty_directories(root)`.

- [ ] **Step 4: Hook tests**

In `tests/test_hooks.py` add:

```python
@pytest.mark.parametrize(
    ("answers", "gone", "kept"),
    [
        (
            {"database": "none"},
            ("migrations", "schema.sql", "src/my_service/infrastructure/db"),
            ("src/my_service/infrastructure/memory", "src/my_service/infrastructure/cache"),
        ),
        (
            {"cache": "none"},
            ("src/my_service/infrastructure/cache",),
            ("src/my_service/infrastructure/db",),
        ),
        (
            {"object_storage": "none"},
            ("src/my_service/infrastructure/storage", "tests/integration/test_receipt_store.py"),
            ("src/my_service/infrastructure/memory/receipt_store.py",),
        ),
    ],
)
def test_the_hook_deletes_an_unchosen_backend_whole(cookies, answers, gone, kept) -> None:
    result = cookies.bake(extra_context=answers)
    assert result.exit_code == 0, result.exception
    for path in gone:
        assert not (result.project_path / path).exists(), path
    for path in kept:
        assert (result.project_path / path).exists(), path
```

- [ ] **Step 5: Run, lint, commit**

```bash
uv run --group dev pytest tests/test_hooks.py -q
uv run --group dev pytest tests/test_generation.py -q -k carries_only
just lint && just regen-check
```

Expected: hook tests pass; the invariant now fails the seven combinations on `services`/`dependencies`/imports rather than on `paths` (the Jinja half is Tasks 3–5); `regen-check` clean (the hook does nothing for the reference answers).

```bash
git add hooks/post_gen_project.py tests/test_hooks.py tests/test_generation.py
git commit -m "feat(hooks): delete an unchosen backend's files, and assert the pruning invariant"
```

---

### Task 3: Database pruning (`{%- if cookiecutter.database == "postgres" %}`)

**Files:**
- Modify in `{{cookiecutter.project_slug}}/`: `pyproject.toml`, `compose.yaml`, `justfile`, `.importlinter`, `.pre-commit-config.yaml`, `.trivyignore.yaml`, `.env.example`, `src/<pkg>/settings.py`, `container.py`, `main.py`, `observability/otel.py`, `observability/metrics.py`, `tests/api/test_errors.py`, `tests/unit/test_container.py`, `test_metrics.py`, `test_settings.py`, `test_config_check.py`, `test_config_docs.py`, `test_compose_images.py`, `tests/integration/conftest.py`
- Regenerate: `examples/reference-service/**` (no change expected)

**Interfaces:**
- Consumes: the invariant's `database` entry (Task 2) — it defines done.

- [ ] **Step 1: See the four database-off combinations fail**

```bash
uv run --group dev pytest tests/test_generation.py -q -k "carries_only and none-" 2>&1 | tail -20
```

Read the first assertion of `none-redis-s3`: it names the first surface to fix.

- [ ] **Step 2: Wrap the database lines, file by file**

Rule for every edit: the block tag on its own line, left-strip form, wrapping only lines that exist today. Read each file before editing; the list below says *what* to wrap, the file says *where*.

| File | Wrap |
|---|---|
| `pyproject.toml` | `"sqlalchemy[asyncio]…"`, `"asyncpg…"`, `"opentelemetry-instrumentation-sqlalchemy…"` with their comment lines; in `dev`: `"alembic…"` with its comment. `testcontainers[postgres,redis,minio]`: the extras follow the answers. Wrap the line (and its comment) in `{%- if cookiecutter.database == "postgres" or cookiecutter.cache == "redis" or cookiecutter.object_storage == "s3" %}` … `{%- endif %}` and render the extras with one inline expression: `"testcontainers[{{ ((['postgres'] if cookiecutter.database == 'postgres' else []) + (['redis'] if cookiecutter.cache == 'redis' else []) + (['minio'] if cookiecutter.object_storage == 's3' else [])) | join(',') }}]>=4.15",`. A `{%- set %}` would also work but must not be the file's first line (a block tag's trailing newline survives, and a leading blank line breaks the golden diff). Verify on renders: exactly `"testcontainers[postgres,redis,minio]>=4.15",` for everything on, `"testcontainers[postgres]>=4.15",` for postgres only, absent for everything off. Any tool-config section naming SQLAlchemy (mypy overrides, mutmut paths) — wrap the lines. |
| `compose.yaml` | The `postgres:` and `migrate:` services (whole blocks including comments); in `app:` → `depends_on:` the `postgres`/`migrate` entries; the `postgres-data` volume. Mind YAML: a removed `depends_on` must not leave an empty mapping — if `app.depends_on` would become empty with every backend off, wrap the `depends_on:` key itself in `{%- if … or … or … %}` covering all three (Task 5 finishes it). Check with `yaml.safe_load` on renders. |
| `justfile` | The recipes in Verified Fact 9; the `migrate`/`schema` calls inside `gates`, `check-all` and any composition recipe; the `-migrations` image lines in `build-images`, `build-multiarch`, `scan`, `sbom`, `publish-images`, `scan-published`, `promote-latest` (some are single tokens inside a line — allowed inline, no dashes); the `migrations=` recipe parameter default in `scan`/`sbom` signatures (inline). Render and read the justfile for `database=none` afterwards: `just --list` must parse (`just --list -f <render>/justfile`). |
| `.importlinter` | The `sqlalchemy` and `asyncpg` lines in both contracts. |
| `.pre-commit-config.yaml` | The whole `sqlfluff` repo block. |
| `.trivyignore.yaml` | Read the file's shape first (a top-level `vulnerabilities:` list). Every entry targets the migrations image, so: `{%- if cookiecutter.database == "postgres" %}` the key with today's entries and their comments `{%- else %}` `vulnerabilities: []` `{%- endif %}` — the key must exist in both renders with a list value, because Trivy rejects a null value; check `yaml.safe_load` on both renders. |
| `.env.example` | The `APP_DATABASE__*` block with its comments. |
| `settings.py` | `class DatabaseSettings` and the `database:` field on `Settings` with their comments; any import only they use (`PostgresDsn`). |
| `container.py` | The `sqlalchemy`/`db` imports; `engine` field and its comment; the `if settings.database is None … else …` block becomes: with the database on, exactly today's code; with it off, `orders = InMemoryOrderRepository()` — write this as `{%- if … == "postgres" %}` today's `if/else` `{%- else %}` the one-line in-memory assignment `{%- endif %}` so the on-render is unchanged; the readiness registration block; `close_container`'s engine disposal. |
| `main.py` | The `instrument_database` import and its call block. |
| `otel.py` | The `SQLAlchemyInstrumentor` and `AsyncEngine` imports; `instrument_database`. |
| `metrics.py` | The `sqlalchemy` imports; `_register_pool_metrics`; the `engine` parameter and its `if engine is not None` block in `register_runtime_metrics` — keep the function's signature valid for callers in both renders (grep the callers). |
| `tests/api/test_errors.py` | The one test that builds `PostgresOrderRepository`, with its imports. |
| `tests/unit/test_container.py`, `test_metrics.py`, `test_settings.py` (the `APP_DATABASE__DSN` test), `test_config_check.py` (the `APP_DATABASE__DSN` test), `test_config_docs.py` (the `APP_DATABASE__DSN` assertion), `test_compose_images.py` (`"postgres"` in the tuple — inline), `tests/integration/conftest.py` (the postgres container fixture and its imports) | Wrap the database-only tests, fixtures and imports. |

After each file: `just regen && just regen-check` (must stay clean — the on-render is unchanged) and re-run the failing test to see the next assertion.

- [ ] **Step 3: Done when**

```bash
uv run --group dev pytest tests/test_generation.py -q -k "carries_only and (none-redis-s3 or none-none-none)"
```

`none-redis-s3` passes. `none-none-none` still fails on cache/storage (Tasks 4–5). Also:

```bash
uv run --group dev pytest tests -q && just lint && just regen-check
```

- [ ] **Step 4: Commit**

```bash
git add '{{cookiecutter.project_slug}}' examples/reference-service
git commit -m "feat(template): prune the database when database=none"
```

---

### Task 4: Cache pruning (`{%- if cookiecutter.cache == "redis" %}`)

**Files:** `pyproject.toml`, `compose.yaml`, `justfile`, `.importlinter`, `.env.example`, `settings.py`, `container.py`, `main.py`, `observability/otel.py`, `tests/fakes.py`, `tests/unit/test_container.py`, `test_config_docs.py`, `test_compose_images.py`, `tests/integration/conftest.py`

- [ ] **Step 1: See it fail** — `-k "carries_only and postgres-none-s3"`.
- [ ] **Step 2: Wrap** — `redis`, `opentelemetry-instrumentation-redis` deps (and the long comment above them); the `redis` compose service and `app.depends_on: redis`; `redis-cli`; `.importlinter`'s `redis` lines; `APP_CACHE__*` in `.env.example`; `CacheSettings` + the `cache:` field; in `container.py` the `redis` imports, the `redis` field, the `if settings.cache is not None` block, the cache readiness block, the close; in `main.py` the `instrument_redis` import and call (and its comment); in `otel.py` `RedisInstrumentor` and `instrument_redis`; `FakeRedis` in `tests/fakes.py` (check who imports it — if only the pruned tests, wrap the class); the cache tests/fixtures/imports in the unit and integration files; `"redis"` in `test_compose_images.py`'s tuple.
- [ ] **Step 3: Done when** `postgres-none-s3` and `none-none-s3` pass; full root suite, `just lint`, `just regen-check` clean.
- [ ] **Step 4: Commit** — `feat(template): prune the cache when cache=none`.

---

### Task 5: Object-storage pruning (`{%- if cookiecutter.object_storage == "s3" %}`)

**Files:** `pyproject.toml`, `compose.yaml`, `justfile`, `.importlinter`, `.env.example`, `settings.py`, `container.py`, `tests/unit/test_container.py`, `test_compose_images.py`, `tests/integration/conftest.py`; finish `compose.yaml`'s `app.depends_on` for the all-off render and `testcontainers` for all-off.

- [ ] **Step 1: See it fail** — `-k "carries_only and postgres-redis-none"`.
- [ ] **Step 2: Wrap** — `aioboto3` dep (and the botocore comment block); `minio` + `minio-bootstrap` services, `app.depends_on: minio-bootstrap`, the `minio-data` volume; `minio-console`; `.importlinter`'s `aioboto3` lines; `APP_STORAGE__*`; `StorageSettings` + `storage:` field; in `container.py` the storage imports, the `s3_store` block (the in-memory store assignment stays), the storage readiness block; the storage tests/fixtures/imports; `"minio"` in `test_compose_images.py`. The receipt feature (`domain/receipts.py`, `services/receipt.py`, `api` route, `infrastructure/memory/receipt_store.py`, `tests/api/test_receipts.py`, `tests/unit/test_get_receipt.py`) stays in every render.
- [ ] **Step 3: Done when** all eight combinations pass `test_a_render_carries_only_the_backends_it_chose`; full root suite, `just lint`, `just regen-check` clean.
- [ ] **Step 4: Commit** — `feat(template): prune object storage when object_storage=none`.

---

### Task 6: The sampled renders pass their own gates (manual verification)

Not a test in this PR (PR 5 makes it CI); a verification that the matrix's structural checks translate into working projects.

- [ ] **Step 1: Three renders with the hook live**

For each of `database=postgres cache=redis object_storage=s3`, `database=none cache=none object_storage=none`, `database=postgres cache=none object_storage=none`:

```bash
rm -rf /tmp/pyfr-m7 && mkdir /tmp/pyfr-m7
uv run --group dev cookiecutter . --no-input -o /tmp/pyfr-m7 project_name="Demo Service" database=<…> cache=<…> object_storage=<…>
cd /tmp/pyfr-m7/demo-service && just check; cd -
```

Expected for each: `lint`, `typecheck`, `imports` and `precommit` pass; `test` fails only on `tests/unit/test_config_docs.py`'s two documented tests (PR 4). Any other failure — an import-linter contract naming a package that is gone, a mypy error from a pruned type, a test importing a pruned module — is a pruning gap: fix it in the template, extend the invariant so the matrix would have caught it, regen, re-run.

- [ ] **Step 2: Docker gates on the all-on render and on `postgres-none-none`**

In `/tmp/pyfr-m7/demo-service` for those two: `just gates` (schema gates), `just o11y-gates`. For the example: `just gates && just contract-gates && just o11y-gates` (unchanged, must stay green).

- [ ] **Step 3: Record** the results in the PR body; clean up `/tmp/pyfr-m7`.

---

### Task 7: Documentation and the pull request

**Files:** `docs/contributing.md`, `docs/roadmap.md`, `docs/reference/commands.md`

- [ ] **Step 1: `contributing.md`** — in "Working on the template", add a subsection **"Backends and pruning"**: the three prompts; the two mechanisms (hook table in `hooks/post_gen_project.py`, `{%- if %}` blocks); the left-strip convention with a four-line example; the rule "a conditional wraps code that already exists"; how to see a combination (`uv run --group dev cookiecutter . --no-input -o /tmp/x database=none …`); and that `tests/test_generation.py` renders all eight on every push and runs ruff on each. Bump `last_reviewed`.
- [ ] **Step 2: `roadmap.md`** — the M7 row: PR 2 done — "the three backend prompts, pruning across the eight combinations, `.pyfr-answers.yml`"; "Still to come:" drops the backend line. Keep the config-docs limitation sentence.
- [ ] **Step 3: `commands.md`** — no new recipe; in the root `just test` row mention the eight-render matrix if the row describes what the tests cover.
- [ ] **Step 4: Verify and open the PR**

```bash
just check && just precommit && just docs-build
git push -u origin claude/m7-pr2-pruning   # or the HTTPS form from Global Constraints
gh pr create --base main --assignee EmadMokhtar --title "feat: add the backend prompts and prune the unchosen backends (m7 pr 2)" --body "Closes #<issue>  … (what, the invariant, the sampled-render results from Task 6, the known PR 4 limitation, 🤖 line)"
```

---

## Self-review

**Spec coverage.** §5.1 prompts — Task 1. §5.3 pruning half — Task 2. §5.4 `.pyfr-answers.yml` — Task 1. §6 rules — Tasks 2–5, table corrected in Task 1. §10.1 generation tests — Tasks 1–2 (matrix, invariant, `.pyfr-answers.yml`, contract identity, no Jinja; `pyproject.toml` parses via `tomllib`; `compose.yaml` parses via `yaml`; `.importlinter` checked by content — a `configparser` parse is a cheap extra assertion, add it in Task 2 if time allows). §12 PR 2 row — all. M7-3 — the contract test. M7-8 — dashboards untouched.

**Type consistency.** `BACKEND[...]["paths"]` in the test and `PRUNED[...]` in the hook list the same paths (the test's use `my_service`, the hook's use `{{ cookiecutter.package_name }}` — the test renders with the default name). `render(cookies, **answers)` returns `Path`. `combination_id` ids are `db-cache-storage` in that order — the `-k` expressions in Tasks 3–5 rely on it.

**Known limit.** The invariant is structural plus ruff; type errors (mypy) and import-linter contracts on a pruned render are checked by Task 6 by hand and by PR 5's full-suite job in CI.
