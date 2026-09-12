# PyFr M7 PR 1 — Template Skeleton Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the reference service into the cookiecutter template body, substitute the identity answers throughout it, regenerate `examples/reference-service/` from it, and gate the two against each other with a golden diff — so that from this pull request on, the template is the only source of truth.

**Architecture:** `git mv examples/reference-service '{{cookiecutter.project_slug}}'` so history follows the files; `cookiecutter.json` with the twelve prompts minus the three backend choices (those arrive with pruning in PR 2); a `pre_gen_project.py` that validates answers and a `post_gen_project.py` whose pruning half selects the licence file and whose side-effect half (`git init`, `uv sync`, hooks, first commit) is skipped under `PYFR_REGEN`; `scripts/regen.py` that renders with `tests/reference-answers.yaml` and syncs, checks, or adopts; a root `.pre-commit-config.yaml` that owns the repository's hooks now that the service's config is project-relative; two CI additions (`golden`, `precommit`) and one workflow (`adopt.yml`) that copies Dependabot's pin changes from the rendered example back into the template.

**Tech Stack:** cookiecutter (Python API and CLI), pytest-cookies, Jinja2 (`{% raw %}`, `_copy_without_render`), uv, just, pre-commit, GitHub Actions.

**Spec:** [`docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md`](../specs/2026-09-12-pyfr-m7-templatise-design.md) — sections 3 (layout), 4 (regeneration and golden diff), 5 (prompts and hooks), 7 (collision pass), 12 (the PR 1 row), 13 (error handling); and the parent [`2026-08-28-pyfr-cookiecutter-template-design.md`](../specs/2026-08-28-pyfr-cookiecutter-template-design.md) sections 3.3–3.4 and 9. Task 1 amends the M7 spec with the three decisions taken while planning (below).

---

## Decisions taken while planning (Task 1 writes them into the spec)

| # | Decision | Why |
|---|---|---|
| M7-2 (amended) | **Twelve prompts. The two SLO prompts are dropped from M7.** The target and latency are threaded through `slo.py` (constants with deliberate rounding), `otel.py` (the `0.3` histogram bucket), `slo.yml`, `slo_test.yml`, the copied-verbatim `slo.json` (two `0.999` thresholds) and two unit tests that assert `ERROR_BUDGET == 0.001`. | Eight files of Jinja arithmetic, including test assertions and a hook patching JSON, for two prompts. The observability reference gains a "changing the objective" section instead (Task 12). |
| M7-3 (amended) | `openapi.json` carries the one substitution `"title": "{{ cookiecutter.project_slug }}"` (the app titles the document with `settings.service_name`); it carries no conditional. Byte-identical across the eight combinations for the same identity answers. | The title is a prompt value. "No template syntax" was too strong. |
| M7-10 (new) | **`just adopt` copies Dependabot's edits back into the template.** Dependabot's `directory` entries keep pointing at `examples/reference-service/` — it cannot parse Jinja. `scripts/regen.py --adopt` replaces, in the template file that renders it, each changed line of the example (pin lines never contain Jinja, so the replacement is literal; any other shape of change fails loudly). The `golden` job runs it first on Dependabot pull requests; `adopt.yml` commits the same result to `main` after the merge. | Without it every Dependabot pull request fails the golden diff, and the template's pins go stale. |
| licence (amended) | Choices are `Apache-2.0 | MIT | MPL-2.0 | Proprietary`; the reference answers choose `MPL-2.0`. The licence files are four template files `LICENSE.<choice>`; the hook keeps the chosen one as `LICENSE`. | The example lives in an MPL-2.0 repository and should carry its licence. Four files and a rename avoid Jinja whitespace control across two hundred lines of Apache text. |
| `_template_version` | Arrives in PR 2 with `.pyfr-answers.yml`, not in PR 1. | Nothing reads it before the answers file exists, and PR 5 wires its bump. |
| `.gitignore` | The template body gains a `.gitignore`. The service never had one; the repository's root file covered it. | The hook's first commit would otherwise commit `.venv/`. |
| Image names | Published images become `ghcr.io/<org>/<project_slug>` and `…-migrations`; for the reference answers that is `ghcr.io/emadmokhtar/reference-service`, no longer `…/pyfr-reference-service`. | The name must derive from prompts. The GHCR packages under the new names must be made public once, as `contributing.md` already says for the old ones. |
| Repository links inside the example | `https://github.com/{{ github_org }}/{{ project_slug }}` renders to `https://github.com/EmadMokhtar/reference-service`, which does not exist. Inside the example this appears only in the two `Dockerfile` labels. | Inherent in "the example is a generated project named reference-service". Lychee checks `docs/**` and the root README only. PR 4 adds a lychee exclusion when the example's docs arrive. |

## Global Constraints

Every task's requirements implicitly include these.

- **Python `>=3.13`** everywhere; `.python-version` says `3.13`. The template body's `.python-version` is copied as is.
- **uv for everything Python.** `uv sync`, `uv run`, `uv lock`, `uv add`. No pip. Root dev tools run through `uv run --group dev`.
- **Two Python projects, never synced together.** The root `pyproject.toml` is the toolchain (docs, Commitizen, and now cookiecutter, pytest-cookies, pre-commit). `{{cookiecutter.project_slug}}/pyproject.toml` is the service's, and `examples/reference-service/pyproject.toml` is its render.
- **The template is the source of truth from Task 6 on.** After Task 6, nothing under `examples/reference-service/` is edited by hand — every change is made in `{{cookiecutter.project_slug}}/` and followed by `just regen`. `uv.lock` is the one exception (spec M7-4).
- **Substitution, not conditionals.** PR 1 adds `{{ cookiecutter.<key> }}` substitutions and `{% raw %}` guards only. The single `{% if %}` in this PR is none: the licence is chosen by the hook, not by Jinja.
- **Every render must be free of `{{` and `{%`.** Task 8's test enforces it.
- **The render is a pure function of template and answers under `PYFR_REGEN`.** No network, no git, no virtual environment.
- **The example's own gates keep passing.** After regeneration, `just check` in `examples/reference-service/` passes exactly as before this PR; `just gates`, `contract-gates`, `o11y-gates` too. The contract does not change: `openapi.json`'s bytes after rendering with the reference answers equal today's bytes.
- **Conventional Commits** for every commit; Commitizen checks the message through the root pre-commit hook.
- **Line length 88** in Python; the hooks, `scripts/regen.py` and the root tests pass `ruff check` and `ruff format --check` run with the root's own ruff (`just lint`). The root gains a ruff pin of its own in Task 2: between Task 3 and Task 6 the example has no `pyproject.toml`, so nothing at the root may depend on the example's environment.
- **Unit tests never need Docker.** Every test this plan adds runs without Docker and without network. `pytest-cookies` renders into `tmp_path`.
- **A generated file is never hand-edited.** `.env.example` and `docs/reference/configuration.md` are regenerated by the example's `just config-docs` where the plan says so.
- **Work on a branch named `claude/m7-pr1-template-skeleton` from `origin/main`**, in a worktree. Open a tracking issue first and link the PR to it. Assign the PR to `EmadMokhtar` (bare login).

## Verified facts

Checked in this repository while planning, or by reading the tools' documentation. An implementer who finds one false stops and says so.

1. `pre-commit` changes directory to the git root before running hooks and resolves `--config` and `--files` relative to the *original* working directory. That is why the service's config today uses root-relative paths and `--project examples/reference-service`, and why a project-relative config cannot run for a tree nested inside another repository (service `.pre-commit-config.yaml`, comment at lines 15–20; M6 plan Verified Fact 11).
2. The installed git hook in this clone runs `pre-commit` with `--config=examples/reference-service/.pre-commit-config.yaml` (`.git/hooks/pre-commit`). After the move that path no longer exists, so Task 2 installs the root config **before** Task 3 moves the tree.
3. Cookiecutter renders the hook scripts through Jinja before running them, so `"{{ cookiecutter.license }}"` inside a hook is a literal at run time. It runs `post_gen_project.py` with the generated project as the working directory. A hook exiting non-zero aborts generation and removes the output directory.
4. `_copy_without_render` is a list of glob patterns matched (with `fnmatch`, where `*` also matches `/`) against paths relative to the generated project; matched files are copied byte for byte, and their *names* are still rendered.
5. Cookiecutter's Jinja environment keeps trailing newlines and does not trim blocks; `{% raw %}…{% endraw %}` may be used inline within a line.
6. `sys.stdlib_module_names` exists on Python 3.10+ and contains `email`, `types`, `test`, `json` and the rest of the standard library's top-level names.
7. `git ls-files` run from `examples/reference-service/` lists paths relative to that directory and includes `uv.lock`.
8. `pytest-cookies` exposes a `cookies` fixture whose `bake(extra_context=...)` returns a result with `exit_code`, `exception` and `project_path`; a failing hook gives `exit_code == -1` with `exception` set. It renders the template found at the `--template` option's path, default `.`, relative to pytest's root directory.
9. Pushes made with the workflow's `GITHUB_TOKEN` do not start new workflow runs. `release.yml` already lives with this for its bump commit; `adopt.yml` inherits the same behaviour and the same token requirements `contributing.md` describes.
10. On a `push` event, `github.event.head_commit.author.name` is `dependabot[bot]` for a squash-merged Dependabot pull request (commit `733256a` on `main`: author `dependabot[bot]`). On a `pull_request` event from Dependabot, `github.actor` is `dependabot[bot]` and `github.event.head_commit` is absent.
11. The reference service's `README.md` mentions "reference service" as prose twice and its identifiers many times; outside the README, prose mentions are seven lines in six files (`seed.py`, `__init__.py`, `pyproject.toml`, `slo.yml`, `compose.yaml`, `.pre-commit-config.yaml`). Two tests assert the port: `tests/unit/test_settings.py:15` and `tests/unit/test_config_docs.py:386`.
12. `ops/grafana/provisioning/dashboards/pyfr-dashboards.yaml` contains no prompt value; only its comment contains `{{ }}`. It can be copied verbatim with the dashboards.
13. The root `docs` CI job already runs the root `just check` (`docs-build` and `test`), so root tests added by this plan run in CI without a new job; `golden` is added as its own job for a clear failure name.

---

## File structure

**Created**

| Path | Responsibility |
|---|---|
| `cookiecutter.json` | Prompts, derived defaults, `_copy_without_render` |
| `hooks/pre_gen_project.py` | Reject bad answers before anything is written |
| `hooks/post_gen_project.py` | Keep the chosen licence; then, unless `PYFR_REGEN`, set the project up |
| `{{cookiecutter.project_slug}}/` | The template body (moved) |
| `{{cookiecutter.project_slug}}/.gitignore` | Ignore rules for a generated project |
| `{{cookiecutter.project_slug}}/LICENSE.{Apache-2.0,MIT,MPL-2.0,Proprietary}` | Licence texts; the hook keeps one |
| `tests/reference-answers.yaml` | The answers the example is rendered from |
| `scripts/regen.py` | Render; sync, check, or adopt |
| `tests/test_hooks.py` | Hook behaviour through `pytest-cookies` |
| `tests/test_generation.py` | Render invariants for the default and reference answers |
| `tests/test_regen.py` | `compare`, `sync` and `adopt` on a tiny fake template |
| `tests/test_golden.py` | `regen.py --check` exits 0 |
| `.pre-commit-config.yaml` (root) | The repository's hooks, root-relative |
| `.github/workflows/adopt.yml` | After a Dependabot merge, adopt and commit |
| `docs/adr/0017-the-template-is-the-source-of-truth.md` | The decision behind the golden diff |

**Modified**

| Path | Change |
|---|---|
| `pyproject.toml` (root) | `cookiecutter`, `pytest-cookies`, `pre-commit` in `dev` |
| `justfile` (root) | `regen`, `regen-check`, `adopt`, `precommit` recipes; `check` includes `regen-check` |
| `{{cookiecutter.project_slug}}/**` | Identity, port, org and image-name substitutions; `{% raw %}` guards; project-relative pre-commit config; nesting-aware `precommit` recipe; README title |
| `examples/reference-service/**` | Regenerated (Task 6); `uv.lock` kept |
| `.github/workflows/ci.yml` | `golden` and `precommit` jobs |
| `.github/workflows/release.yml` | Image names |
| `docs/contributing.md`, `docs/reference/commands.md`, `docs/reference/supply-chain.md`, `docs/reference/observability.md`, `docs/adr/0015-*.md`, `docs/adr/README.md`, `docs/roadmap.md`, `mkdocs.yml` | Section 9.4 of the spec, minus what waits for PR 4 |
| `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md` | The amendments above |

---

### Task 1: Branch, issue, and the spec amendments

**Files:**
- Modify: `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md`

- [ ] **Step 1: Create the worktree and branch**

```bash
git fetch origin
git worktree add -b claude/m7-pr1-template-skeleton .claude/worktrees/m7-pr1 origin/main
cd .claude/worktrees/m7-pr1
```

- [ ] **Step 2: Open the tracking issue**

```bash
gh issue create --assignee EmadMokhtar \
  --title "feat: m7 pr 1 — move the reference service into the template body and add the golden diff" \
  --body "$(cat <<'EOF'
First of the five M7 pull requests (spec: docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md, section 12).

Lands: the template body under `{{cookiecutter.project_slug}}/` (git mv), `cookiecutter.json` with the identity, port and licence prompts, both hooks, the Jinja collision pass, `scripts/regen.py` with `just regen` / `regen-check` / `adopt`, the reference answers, the golden diff test, a root pre-commit configuration, the `golden` and `precommit` CI jobs and `adopt.yml`.

Not yet: backend prompts and pruning (PR 2), generated `.github/` (PR 3), the docs split (PR 4), full-suite tests and `_template_version` (PR 5).
EOF
)"
```

Record the issue number; the PR body in Task 14 closes it.

- [ ] **Step 3: Amend the spec**

In `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md`:

1. Section 2, row M7-2: replace the Decision cell with:
   `**Twelve prompts; Python is fixed at 3.13; the two SLO prompts are dropped.** Section 9.1's list minus `python_version`, `slo_availability_target` and `slo_latency_ms`. *Departs from the specification.*` and append to the Rationale cell: ` The SLO target and latency are threaded through `slo.py`, `otel.py`'s bucket boundaries, `slo.yml`, `slo_test.yml`, the copied-verbatim `slo.json` and two unit-test assertions — eight files of Jinja arithmetic for two prompts. The observability reference documents how to change the objective instead.`
2. Section 2, row M7-3: replace `openapi.json` and `openapi.baseline.json` stay plain JSON with no template syntax, and` with `openapi.json` and `openapi.baseline.json` carry one substitution — the `title` is `{{ cookiecutter.project_slug }}`, because the app titles the document with `settings.service_name` — and no conditional, so`.
3. Section 2: add after M7-9:
   `| M7-10 | **`just adopt` copies Dependabot's edits back into the template.** Dependabot keeps pointing at `examples/reference-service/`; `scripts/regen.py --adopt` replaces, in the template file that renders it, each changed line of the example. The `golden` job runs it first on Dependabot pull requests; `adopt.yml` commits the same result to `main` after the merge. | Dependabot cannot parse Jinja. Pin lines never contain Jinja, so the replacement is literal; any other shape of change fails loudly and is made by hand. |`
4. Section 5.1: delete the two `slo_*` lines from the prompt block; change the `license` line to `license                   Apache-2.0 | MIT | MPL-2.0 | Proprietary`; change "Private keys, never prompted: `_template_version` (bumped by the release, section 4.4), `_copy_without_render` (section 7)." to "Private keys, never prompted: `_copy_without_render` (section 7) from PR 1; `_template_version` (bumped by the release, section 4.4) from PR 2."
5. Section 5.2: delete the `slo_latency_ms` bullet.
6. Section 5.3, "Pruning" paragraph: append `In PR 1 the only pruning is the licence: four `LICENSE.<choice>` files ship in the template body and the hook keeps the chosen one as `LICENSE`.`
7. Section 7, the `ops/prometheus/rules/slo.yml` row: replace `the SLO target and latency come from prompts` with `the file must render because the service name in its annotations is a prompt value`. Add `ops/grafana/provisioning/dashboards/*.yaml` to the dashboards row (it already lists it) and change its Contains cell to `Grafana `${service}` variable syntax; a comment containing `{{ }}``.
8. Section 8: replace `The generated project's `LICENSE` and the licence classifier in `pyproject.toml` follow the `license` prompt: the Apache-2.0 and MIT texts with the author's name and the year, or a one-paragraph proprietary notice.` with `The generated project's `LICENSE` follows the `license` prompt from PR 1 onward: the Apache-2.0, MIT or MPL-2.0 text, or a one-paragraph proprietary notice, with the author's name and no year — a year would change the reference render every January.`
9. Section 12, PR 1 row: replace `the identity, port, SLO and licence substitutions throughout the tree` with `the identity, port, organisation and licence substitutions throughout the tree; a `.gitignore` for generated projects; `just adopt` and `adopt.yml` (M7-10); a root `.pre-commit-config.yaml`` and the Prompts cell with `identity, `http_port`, `license``. Delete `_template_version` from `cookiecutter.json` in that row's mention: change `` `cookiecutter.json`;`` to `` `cookiecutter.json` (without `_template_version`, which arrives with `.pyfr-answers.yml`);``.
10. Section 14: add the row `| Dependabot edits the rendered example | `just adopt` in the `golden` job and `adopt.yml` after the merge (M7-10); a change `adopt` cannot express fails with the file name and is made in the template by hand |`.
11. Section 16: add `| Adopt | Copying a line changed in the rendered example back into the template file that renders it — the reverse direction, used only for Dependabot's pin changes |`.

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md
git commit -m "docs(pyfr): amend the m7 spec with the pr 1 planning decisions"
```

---

### Task 2: Root toolchain and the repository's own pre-commit configuration

**Files:**
- Modify: `pyproject.toml` (root), `uv.lock` (root)
- Create: `.pre-commit-config.yaml` (root), `ruff.toml` (root)
- Modify: `justfile` (root), and whatever `just lint` finds in `scripts/` and `tests/`

**Interfaces:**
- Produces: root `dev` group with `cookiecutter`, `pytest-cookies`, `pre-commit`, `ruff`; root recipes `precommit` and `lint`.

- [ ] **Step 1: Add the dependencies**

```bash
uv add --group dev "cookiecutter>=2.6,<3" "pytest-cookies>=0.7" "pre-commit>=4.0" "ruff>=0.7"
uv run --group dev cookiecutter --version
uv run --group dev pre-commit --version
uv run --group dev ruff --version
```

Expected: all three print a version. Then open `pyproject.toml` and add a comment above the three new lines, in the style of the existing ones:

```toml
    # The template's own tests render it (pytest-cookies wraps cookiecutter's
    # Python API) and scripts/regen.py renders it for the golden diff. Both
    # run from this group so the version that renders the example is the
    # version in uv.lock.
    "cookiecutter>=2.6,<3",
    "pytest-cookies>=0.7",
    # The repository's git hooks (.pre-commit-config.yaml at the root). Until
    # M7 the reference service's configuration doubled as the repository's;
    # now the service's is written for a generated project and cannot run
    # nested inside this repository (Verified Fact 1 of the M7 PR 1 plan).
    "pre-commit>=4.0",
    # The root has Python of its own -- hooks/, scripts/, tests/ -- and its
    # hooks must not depend on the example's environment, which does not
    # exist between the move and the first regeneration. A second ruff pin,
    # in a second lock, for a second project: the exception ADR 0014 lists.
    "ruff>=0.7",
```

Then create `ruff.toml` at the root — the service's rules, for the root's own files:

```toml
# The root's own Python: hooks/, scripts/ and tests/. The same rules as the
# reference service's ruff.toml, so a file reads the same on either side of
# the template boundary. ruff picks the nearest ruff.toml per file, so the
# root's hooks lint examples/reference-service/ with that project's copy.
line-length = 88
target-version = "py313"
src = ["scripts", "tests"]
# The template body is Jinja, not Python; it is linted as its render, in
# examples/reference-service/. The example lints itself with its own copy.
extend-exclude = ["{{cookiecutter.project_slug}}", "examples"]

[lint]
select = [
    "E", "W",   # pycodestyle
    "F",        # pyflakes
    "I",        # isort
    "B",        # flake8-bugbear
    "S",        # bandit security
    "UP",       # pyupgrade
    "ASYNC",    # flake8-async
    "RUF",      # ruff-specific
]

[lint.per-file-ignores]
# assert is how tests assert; the regen tests drive git through subprocess
# with fixed literal argument lists.
"tests/*" = ["S101", "B017", "S603", "S607"]
# scripts/regen.py and the hooks shell out to git and uv, resolved through
# PATH so they work on any contributor's machine; every argument list is a
# fixed literal, never input.
"scripts/*" = ["S603", "S607"]
"hooks/*" = ["S603", "S607"]

[lint.isort]
known-first-party = [
    "regen",
    "check_doc_examples",
    "check_docs_freshness",
    "check_docs_updated",
]
```

`extend-exclude` keeps `just lint` (below) out of the example and the template body; the pre-commit hooks pass explicit file names with `--force-exclude`, so the same exclusion holds there, and the example is linted by its own `just check`.

- [ ] **Step 2: Write the root pre-commit configuration**

Copy the service's file and adjust it. Create `.pre-commit-config.yaml` at the repository root:

```yaml
# The repository's hooks. The reference service's own .pre-commit-config.yaml
# is written for a generated project and runs only when that project is its
# own git repository; inside this repository the file at
# examples/reference-service/ is rendered output and inert (M7 PR 1 plan,
# Verified Fact 1).
#
# pre-commit only installs the git hook types it is told to. Without this,
# `pre-commit install` wires up the `pre-commit` stage only - the commitizen
# hook below runs at the `commit-msg` stage and would never fire.
default_install_hook_types: [pre-commit, commit-msg]

# The template body is Jinja, not Python, YAML or TOML: its files render into
# those languages and are checked there, in examples/reference-service/.
exclude: ^\{\{cookiecutter\.project_slug\}\}/

repos:
  # ruff, uv and Commitizen run from the environments uv.lock pins -- the
  # ONE place their versions live (ADR 0014). `language: system` runs the
  # command as-is and the command resolves the tool through uv.
  #
  # pre-commit runs every hook from the repository ROOT with root-relative
  # paths. ruff runs from the root's own environment and finds each file's
  # nearest ruff.toml, so the example is linted with its own rules; the
  # uv-lock hook selects the example's project WITHOUT changing directory.
  - repo: local
    hooks:
      - id: ruff-check
        name: ruff check
        entry: uv run --group dev ruff check --force-exclude
        language: system
        types_or: [python, pyi]
        require_serial: true
      - id: ruff-format
        name: ruff format --check
        entry: uv run --group dev ruff format --check --force-exclude
        language: system
        types_or: [python, pyi]
        require_serial: true
      - id: uv-lock
        name: uv lock --check (reference service)
        entry: uv lock --check --project examples/reference-service
        language: system
        pass_filenames: false
        files: ^examples/reference-service/(pyproject\.toml|uv\.lock)$
      - id: uv-lock-root
        name: uv lock --check (repository)
        entry: uv lock --check
        language: system
        pass_filenames: false
        files: ^(pyproject\.toml|uv\.lock)$
      # The root project owns this repository's Commitizen (root pyproject).
      - id: commitizen
        name: commitizen check
        entry: uv run --locked --group dev cz check --allow-abort --commit-msg-file
        language: system
        stages: [commit-msg]

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks

  - repo: https://github.com/sqlfluff/sqlfluff
    rev: 4.3.0
    hooks:
      - id: sqlfluff-lint
        files: ^examples/reference-service/migrations/.*\.sql$

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict
```

Copy the `rev:` values from the service's current file if they differ from the above — the service's file is the source, and Dependabot's `pre-commit` entry for the root (Task 11) will keep the root's moving.

- [ ] **Step 3: Install the root hooks and add the recipe**

```bash
uv run --group dev pre-commit install
```

Expected: `pre-commit installed at .git/hooks/pre-commit` and `.../commit-msg`. In the root `justfile`, after the `test` recipe:

```just
# The repository's git hooks over every tracked file. The reference service's
# own precommit recipe skips itself when it finds it is nested inside this
# repository; this recipe is the one that covers that tree here.
precommit:
    uv run --group dev pre-commit run --all-files

# ruff over the root's own Python -- hooks/, scripts/, tests/. ruff.toml's
# extend-exclude keeps it out of the template body and the example.
lint:
    uv run --group dev ruff check .
    uv run --group dev ruff format --check .
```

The root's tests and scripts were linted by nothing until now; `just lint` may find import-order (`I001`) or style findings in them. Fix those in this task — they are the root's files — and keep the fixes minimal.

- [ ] **Step 4: Run the hooks once**

```bash
just precommit
```

Expected: every hook passes or is skipped ("no files to check"). If `end-of-file-fixer` or `trailing-whitespace` modifies a file, look at the diff — it should be empty on a clean checkout — and revert anything they changed outside this task.

- [ ] **Step 5: Commit**

```bash
just lint
git add pyproject.toml uv.lock .pre-commit-config.yaml ruff.toml justfile scripts tests
git commit -m "build: give the repository its own pre-commit configuration, ruff and the template toolchain"
```

Expected: `just lint` clean on the existing scripts and tests before the commit; if the root's ruff finds something the service's never saw (the root tests were linted by nothing until now), fix it here.

---

### Task 3: Move the tree

**Files:**
- Move: `examples/reference-service/**` → `{{cookiecutter.project_slug}}/**`, except `uv.lock`
- Move: `{{cookiecutter.project_slug}}/src/reference_service/` → `{{cookiecutter.project_slug}}/src/{{cookiecutter.package_name}}/`

- [ ] **Step 1: Move**

```bash
git mv examples/reference-service '{{cookiecutter.project_slug}}'
mkdir -p examples/reference-service
git mv '{{cookiecutter.project_slug}}/uv.lock' examples/reference-service/uv.lock
git mv '{{cookiecutter.project_slug}}/src/reference_service' '{{cookiecutter.project_slug}}/src/{{cookiecutter.package_name}}'
git status --short | head
```

Expected: every line is `R  examples/reference-service/... -> {{cookiecutter.project_slug}}/...`, plus the lock's rename back.

`git mv` renames the directory on disk, so the untracked, ignored directories travelled with it — `.venv`, `.mypy_cache`, `.ruff_cache`, `.pytest_cache`, `.hypothesis`, `.import_linter_cache`. They are caches; a template body must not carry them, and Task 6's `uv sync` rebuilds the example's. Delete them:

```bash
for d in .venv .mypy_cache .ruff_cache .pytest_cache .hypothesis .import_linter_cache; do
  rm -rf "{{cookiecutter.project_slug}}/$d"
done
ls -a '{{cookiecutter.project_slug}}' | grep -c -E '^\.(venv|.*_cache|hypothesis)$'
```

Expected: `0`.

- [ ] **Step 2: Commit**

The root `check-yaml`/`check-toml`/ruff hooks skip the template body (the `exclude` in Task 2); `end-of-file-fixer` and `trailing-whitespace` still run over it and change nothing.

```bash
git commit -m "refactor: move the reference service into the template body"
```

---

### Task 4: `cookiecutter.json`, the hooks, and the licence files

**Files:**
- Create: `cookiecutter.json`, `hooks/pre_gen_project.py`, `hooks/post_gen_project.py`
- Create: `{{cookiecutter.project_slug}}/LICENSE.Apache-2.0`, `LICENSE.MIT`, `LICENSE.MPL-2.0`, `LICENSE.Proprietary`
- Create: `{{cookiecutter.project_slug}}/.gitignore`
- Test: `tests/test_hooks.py`

**Interfaces:**
- Produces: prompt keys `project_name`, `project_slug`, `package_name`, `description`, `author_name`, `author_email`, `github_org`, `http_port`, `license`; environment variable `PYFR_REGEN`.

- [ ] **Step 1: Write the failing hook tests**

`tests/test_hooks.py`:

```python
"""The two hooks, driven through pytest-cookies.

Every render here sets PYFR_REGEN, so the post-generation hook prunes and
stops: no git, no uv, no network. The one test of the side-effect half
points `git` and `uv` at a shim that fails, to prove best effort.
"""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest

REGEN = {"PYFR_REGEN": "1"}


@pytest.fixture(autouse=True)
def _regen_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    for key, value in REGEN.items():
        monkeypatch.setenv(key, value)


def test_default_answers_render(cookies) -> None:
    result = cookies.bake()
    assert result.exit_code == 0, result.exception
    assert result.project_path.name == "my-service"
    assert (result.project_path / "src" / "my_service" / "main.py").is_file()


@pytest.mark.parametrize(
    ("answers", "message"),
    [
        ({"project_slug": "My-Service"}, "project_slug"),
        ({"project_slug": "9lives"}, "project_slug"),
        ({"package_name": "email"}, "standard library"),
        ({"package_name": "class"}, "keyword"),
        ({"package_name": "my-service"}, "identifier"),
        ({"http_port": "0"}, "http_port"),
        ({"http_port": "70000"}, "http_port"),
        ({"http_port": "eighty"}, "http_port"),
    ],
)
def test_bad_answers_are_rejected_before_anything_is_written(
    cookies, capfd, answers: dict[str, str], message: str
) -> None:
    result = cookies.bake(extra_context=answers)
    # cookiecutter wraps a failing hook as FailedHookException("Hook script
    # failed (exit status: 1)"); the hook's own sentence is on stderr.
    assert result.exit_code != 0
    assert result.project_path is None or not result.project_path.exists()
    assert message in capfd.readouterr().err


@pytest.mark.parametrize(
    "choice", ["Apache-2.0", "MIT", "MPL-2.0", "Proprietary"]
)
def test_only_the_chosen_licence_survives(cookies, choice: str) -> None:
    result = cookies.bake(extra_context={"license": choice})
    assert result.exit_code == 0, result.exception
    licence = result.project_path / "LICENSE"
    assert licence.is_file()
    assert not list(result.project_path.glob("LICENSE.*"))
    text = licence.read_text()
    expected_first_line = {
        "Apache-2.0": "Apache License",
        "MIT": "MIT License",
        "MPL-2.0": "Mozilla Public License Version 2.0",
        "Proprietary": "Proprietary",
    }[choice]
    assert text.lstrip().startswith(expected_first_line)


def test_regen_mode_leaves_no_git_repository(cookies) -> None:
    result = cookies.bake()
    assert result.exit_code == 0, result.exception
    assert not (result.project_path / ".git").exists()
    assert not (result.project_path / ".venv").exists()
    assert not (result.project_path / "uv.lock").exists()


def test_side_effects_are_best_effort(
    cookies, monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capfd
) -> None:
    # A `git` and a `uv` that always fail, first on PATH. The hook must
    # still exit 0 and tell the user what to run later.
    shims = tmp_path / "shims"
    shims.mkdir()
    for name in ("git", "uv"):
        shim = shims / name
        shim.write_text("#!/bin/sh\nexit 1\n")
        shim.chmod(shim.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", f"{shims}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.delenv("PYFR_REGEN")

    result = cookies.bake()

    assert result.exit_code == 0, result.exception
    out = capfd.readouterr().out
    assert "git init" in out
    assert "uv sync" in out
```

- [ ] **Step 2: Run the tests to see them fail**

```bash
uv run --group dev pytest tests/test_hooks.py -q
```

Expected: errors — `cookiecutter.json` does not exist yet, so `cookies.bake()` fails for every test.

- [ ] **Step 3: Write `cookiecutter.json`**

```json
{
  "project_name": "My Service",
  "project_slug": "{{ cookiecutter.project_name | lower | replace(' ', '-') }}",
  "package_name": "{{ cookiecutter.project_slug | replace('-', '_') }}",
  "description": "A Python microservice generated from PyFr.",
  "author_name": "Your Name",
  "author_email": "you@example.com",
  "github_org": "your-org",
  "http_port": "8000",
  "license": ["Apache-2.0", "MIT", "MPL-2.0", "Proprietary"],
  "_copy_without_render": [
    "ops/grafana/dashboards/*.json",
    "ops/grafana/provisioning/dashboards/*.yaml"
  ]
}
```

`http_port` is a string because cookiecutter prompts are strings; the hook validates it as an integer.

- [ ] **Step 4: Write `hooks/pre_gen_project.py`**

```python
"""Reject bad answers before cookiecutter writes a single file.

Cookiecutter renders this file through Jinja before running it, so the
three constants below are literals by the time Python sees them. A
non-zero exit aborts the generation and nothing is left on disk.
"""

from __future__ import annotations

import keyword
import re
import sys

PROJECT_SLUG = "{{ cookiecutter.project_slug }}"
PACKAGE_NAME = "{{ cookiecutter.package_name }}"
HTTP_PORT = "{{ cookiecutter.http_port }}"

SLUG_PATTERN = re.compile(r"[a-z][a-z0-9-]*")


def problems() -> list[str]:
    found: list[str] = []
    if not SLUG_PATTERN.fullmatch(PROJECT_SLUG):
        found.append(
            f"project_slug {PROJECT_SLUG!r} must match ^[a-z][a-z0-9-]*$: "
            "lower-case letters, digits and hyphens, starting with a letter."
        )
    if not PACKAGE_NAME.isidentifier():
        found.append(
            f"package_name {PACKAGE_NAME!r} is not a Python identifier: "
            "use lower-case letters, digits and underscores."
        )
    elif keyword.iskeyword(PACKAGE_NAME):
        found.append(f"package_name {PACKAGE_NAME!r} is a Python keyword.")
    elif PACKAGE_NAME in sys.stdlib_module_names:
        found.append(
            f"package_name {PACKAGE_NAME!r} shadows a standard library "
            "module; a service by that name breaks in confusing ways."
        )
    try:
        port = int(HTTP_PORT)
    except ValueError:
        found.append(f"http_port {HTTP_PORT!r} is not an integer.")
    else:
        if not 1 <= port <= 65535:
            found.append(f"http_port {port} is outside 1-65535.")
    return found


def main() -> int:
    found = problems()
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Write `hooks/post_gen_project.py`**

```python
"""Keep what the answers chose; then, outside regeneration, set the project up.

Cookiecutter runs this with the generated project as the working directory,
after rendering it through Jinja, so LICENCE below is a literal.

Two halves. Pruning always runs. The side effects -- git init, uv sync, the
pre-commit hook, a first commit -- run only when PYFR_REGEN is unset:
scripts/regen.py sets it so a render is a pure function of the template and
the answers. Every side effect is best effort: a failure prints the command
to run later and the hook still exits 0, because an offline laptop must
not receive a half-set-up project reported as a failed one.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

LICENCE = "{{ cookiecutter.license }}"
LICENCE_FILES = {
    "Apache-2.0": "LICENSE.Apache-2.0",
    "MIT": "LICENSE.MIT",
    "MPL-2.0": "LICENSE.MPL-2.0",
    "Proprietary": "LICENSE.Proprietary",
}


def keep_chosen_licence(root: Path) -> None:
    chosen = root / LICENCE_FILES[LICENCE]
    if not chosen.is_file():
        # The pruning table and the tree have diverged. Fail here, loudly,
        # so the generation tests catch it before a user does.
        sys.exit(f"pruning: {chosen.name} is missing from the template body")
    chosen.rename(root / "LICENSE")
    for name in LICENCE_FILES.values():
        path = root / name
        if path.exists():
            path.unlink()


def remove_empty_directories(root: Path) -> None:
    for directory in sorted(
        (p for p in root.rglob("*") if p.is_dir()), reverse=True
    ):
        if not any(directory.iterdir()):
            directory.rmdir()


def best_effort(command: list[str], cwd: Path) -> bool:
    try:
        subprocess.run(command, cwd=cwd, check=True)
    except (OSError, subprocess.CalledProcessError):
        print(f"Could not run `{' '.join(command)}`; run it later.")
        return False
    return True


def set_up(root: Path) -> None:
    # Each step on its own: a missing `git` must not stop `uv sync`, and a
    # failed `uv sync` (offline) must not stop the repository being made.
    initialised = best_effort(["git", "init", "-q"], root)
    best_effort(["uv", "sync"], root)
    best_effort(["uv", "run", "pre-commit", "install"], root)
    committed = (
        initialised
        and best_effort(["git", "add", "-A"], root)
        and best_effort(
            ["git", "commit", "-q", "-m", "chore: generate the project from pyfr"],
            root,
        )
    )
    if not committed:
        print("Run `git add -A && git commit` once the steps above succeed.")
    print()
    print("Next steps:")
    print(f"  cd {root.name}")
    print("  just up          # build the image and start the stack")
    print("  just check       # every fast gate")
    print("  see README.md for the rest")


def main() -> int:
    root = Path.cwd()
    keep_chosen_licence(root)
    remove_empty_directories(root)
    if os.environ.get("PYFR_REGEN"):
        return 0
    set_up(root)
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Write the four licence files and `.gitignore`**

```bash
cp LICENSE '{{cookiecutter.project_slug}}/LICENSE.MPL-2.0'
curl -fsSL https://www.apache.org/licenses/LICENSE-2.0.txt -o '{{cookiecutter.project_slug}}/LICENSE.Apache-2.0'
head -3 '{{cookiecutter.project_slug}}/LICENSE.Apache-2.0'
```

Expected: the first non-blank line of the Apache file is `Apache License`. Confirm neither file contains `{{` or `{%`:

```bash
grep -c -E '\{\{|\{%' '{{cookiecutter.project_slug}}/LICENSE.Apache-2.0' '{{cookiecutter.project_slug}}/LICENSE.MPL-2.0'
```

Expected: `0` for both. Then write `{{cookiecutter.project_slug}}/LICENSE.MIT`:

```
MIT License

Copyright (c) {{ cookiecutter.author_name }}

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

And `{{cookiecutter.project_slug}}/LICENSE.Proprietary`:

```
Proprietary

Copyright (c) {{ cookiecutter.author_name }}. All rights reserved.

This software and its source code are the confidential property of the
copyright holder. No licence is granted to use, copy, modify, distribute or
sublicense it, in whole or in part, without the copyright holder's prior
written permission.
```

And `{{cookiecutter.project_slug}}/.gitignore`:

```
# Environments and tool caches
.venv/
__pycache__/
*.py[cod]
.pytest_cache/
.mypy_cache/
.ruff_cache/
.hypothesis/
.import_linter_cache/

# Secrets and per-checkout state
.env
.seed-state.json

# Build output: `just sbom`, `just mutants`, `just docs-build`
sbom/
mutants/
site/

# Editors and operating systems
.idea/
.vscode/
.DS_Store
```

- [ ] **Step 7: Run the hook tests**

```bash
uv run --group dev pytest tests/test_hooks.py -q
```

Expected: all pass. If `test_default_answers_render` fails because a file in the template body does not render, the failure names it — that is Task 5's collision pass arriving early; fix that file as Task 5 says and continue.

- [ ] **Step 8: Lint and commit**

```bash
just lint
```

Expected: `All checks passed!` and every file already formatted. (The root's own ruff, Task 2 — the example has no environment until Task 6.)

```bash
git add cookiecutter.json hooks '{{cookiecutter.project_slug}}/LICENSE.Apache-2.0' '{{cookiecutter.project_slug}}/LICENSE.MIT' '{{cookiecutter.project_slug}}/LICENSE.MPL-2.0' '{{cookiecutter.project_slug}}/LICENSE.Proprietary' '{{cookiecutter.project_slug}}/.gitignore' tests/test_hooks.py
git commit -m "feat: add cookiecutter.json, the two hooks and the licence files"
```

---

### Task 5: The substitutions and the collision pass

**Files:**
- Modify: every file under `{{cookiecutter.project_slug}}/` that names the service, the package, the organisation, the repository or the port (96 files by the identifier forms)
- Modify: `{{cookiecutter.project_slug}}/justfile`, `ops/prometheus/rules/slo.yml`, `.sqlfluff`, `tests/integration/test_observability_stack.py` (`{% raw %}` guards)
- Modify: `{{cookiecutter.project_slug}}/.pre-commit-config.yaml` (project-relative), `justfile` (`precommit` nesting check), `README.md` (title and first sentence), `pyproject.toml` (description, authors), `ops/grafana/provisioning/dashboards/pyfr-dashboards.yaml` (comment)
- Test: `tests/test_generation.py` (Task 8 completes it; this task adds the first test)

**Interfaces:**
- Consumes: the prompt keys from Task 4.
- Produces: a template body that renders, with `tests/reference-answers.yaml` (Task 6), to today's tree.

- [ ] **Step 1: Write the first generation test — no template syntax survives**

`tests/test_generation.py`:

```python
"""What every render must satisfy, whatever the answers.

PR 1 checks the default answers and the reference answers. PR 2 makes this
a matrix over the backend combinations.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_ANSWERS = ROOT / "tests" / "reference-answers.yaml"

JINJA_MARKERS = (b"{{", b"{%")


@pytest.fixture(autouse=True)
def _regen_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYFR_REGEN", "1")


def files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


def test_no_template_syntax_survives_the_default_render(cookies) -> None:
    result = cookies.bake()
    assert result.exit_code == 0, result.exception
    offenders = [
        path.relative_to(result.project_path).as_posix()
        for path in files_under(result.project_path)
        if any(marker in path.read_bytes() for marker in JINJA_MARKERS)
        # Grafana's own {{ }} legend syntax, copied verbatim on purpose
        # (spec section 7); anything else here is a collision.
        and not path.relative_to(result.project_path).as_posix().startswith(
            "ops/grafana/"
        )
    ]
    assert offenders == []
```

- [ ] **Step 2: Run it to see it fail**

```bash
uv run --group dev pytest tests/test_generation.py -q
```

Expected: FAIL — the offenders list names `justfile`, `ops/prometheus/rules/slo.yml`, `.sqlfluff` and `tests/integration/test_observability_stack.py` at least (Jinja swallowed `{{name}}` in the justfile, so the render may also have *failed* on an undefined variable — cookiecutter's `StrictEnvironment` raises on `{{name}}`; either way the test is red).

- [ ] **Step 3: Guard the collisions with `{% raw %}`**

Apply the inline guard to every occurrence in these four files. The rule: wrap only the `{{…}}` token, on the same line.

```bash
cd '{{cookiecutter.project_slug}}'
# justfile: every {{param}} recipe interpolation
perl -pi -e 's/\{\{(name|steps|version|app|migrations|builder|registry)\}\}/{% raw %}{{$1}}{% endraw %}/g' justfile
# Prometheus annotations
perl -pi -e 's/\{\{ \$labels\.job \}\}/{% raw %}{{ \$labels.job }}{% endraw %}/g' ops/prometheus/rules/slo.yml
# The f-string's escaped braces
perl -pi -e 's/\{\{le="0\.3"\}\}/{% raw %}{{le="0.3"}}{% endraw %}/' tests/integration/test_observability_stack.py
# The .sqlfluff comment
perl -pi -e 's/interpret \{\{ \}\} and \{% %\}/interpret {% raw %}{{ }} and {% %}{% endraw %}/' .sqlfluff
grep -n -E '\{\{|\{%' justfile ops/prometheus/rules/slo.yml .sqlfluff tests/integration/test_observability_stack.py | grep -v 'raw %}' | grep -v 'cookiecutter\.'
cd ..
```

Expected: the last `grep` prints nothing — every remaining `{{` is inside a raw guard. Jinja also opens a comment at `{#`; confirm no file in the template body contains it (`git grep -l '{#' -- '{{cookiecutter.project_slug}}'` prints nothing — none did when this plan was written). Open `justfile` and check the `_buildx-builder name="pyfr"` recipe line and the two `for image in …` loops read correctly. Also update the comment in `ops/grafana/provisioning/dashboards/pyfr-dashboards.yaml`: replace the two lines

```
# This is the ONLY file in ops/grafana that M7 renders through Jinja. The
# dashboards themselves are copied verbatim — they contain Grafana's own
```

with

```
# Like the dashboards, this file is copied verbatim into a generated
# project (cookiecutter.json, _copy_without_render): nothing in it is a
# prompt value, and the dashboards contain Grafana's own
```

- [ ] **Step 4: Substitute the identifiers**

Order matters: the longest, most specific string first.

```bash
cd '{{cookiecutter.project_slug}}'
FILES=$(git ls-files | grep -v -E '^ops/grafana/|^LICENSE\.')
perl -pi -e 's{pyfr-reference-service}{\{\{ cookiecutter.project_slug \}\}}g' $FILES
perl -pi -e 's{https://github\.com/EmadMokhtar/pyfr}{https://github.com/\{\{ cookiecutter.github_org \}\}/\{\{ cookiecutter.project_slug \}\}}g' $FILES
perl -pi -e 's{ghcr\.io/emadmokhtar}{ghcr.io/\{\{ cookiecutter.github_org | lower \}\}}g' $FILES
perl -pi -e 's{reference_service}{\{\{ cookiecutter.package_name \}\}}g' $FILES
perl -pi -e 's{reference-service}{\{\{ cookiecutter.project_slug \}\}}g' $FILES
git grep -n -E 'reference[_-]service|EmadMokhtar|emadmokhtar|pyfr-reference' -- . ':!ops/grafana' ':!LICENSE.*'
cd ..
```

Expected: the final `git grep` prints nothing. (Grafana files are excluded because they are copied verbatim; the licence files contain none of these strings.)

- [ ] **Step 5: Substitute the port, description and authors**

The port appears in nine places (Verified Fact 11 and the grep below). Replace each `8000` that is the service's own port with `{{ cookiecutter.http_port }}`; do not touch any other number.

```bash
cd '{{cookiecutter.project_slug}}'
git grep -n -w 8000 -- . ':!ops/grafana' ':!openapi*.json'
```

Expected list, each to be edited by hand (a blind replace would also hit unrelated numbers):

| File | Edit |
|---|---|
| `justfile` (`dev` and `seed` recipes) | `${APP_HTTP_PORT:-8000}` → `${APP_HTTP_PORT:-{{ cookiecutter.http_port }}}` |
| `Dockerfile` | `EXPOSE 8000`; the healthcheck's `'8000'`; the `CMD`'s `:-8000` |
| `compose.yaml` | `"8000:8000"` → `"{{ cookiecutter.http_port }}:{{ cookiecutter.http_port }}"`; `http://app:8000` |
| `.env.example` | `APP_HTTP_PORT=8000` |
| `src/{{cookiecutter.package_name}}/settings.py` | `default=8000` |
| `README.md` | the three mentions (`:8000/docs`, "port 8000", the table's `` `8000` ``) |
| `tests/unit/test_settings.py:15` | `== 8000` → `== {{ cookiecutter.http_port }}` |
| `tests/unit/test_config_docs.py:386` | `APP_HTTP_PORT=8000` → `APP_HTTP_PORT={{ cookiecutter.http_port }}` |

Then in `pyproject.toml` replace `description = "PyFr reference service"` with:

```toml
description = "{{ cookiecutter.description }}"
authors = [{ name = "{{ cookiecutter.author_name }}", email = "{{ cookiecutter.author_email }}" }]
```

In `src/{{cookiecutter.package_name}}/__init__.py` replace `"""PyFr reference service."""` with `"""{{ cookiecutter.description }}"""`. In `README.md` replace the first two lines

```
# Reference Service

The PyFr reference service: the walking skeleton every generated project
starts from. It persists orders
```

with

```
# {{ cookiecutter.project_name }}

{{ cookiecutter.description }} Generated from
[PyFr](https://github.com/EmadMokhtar/pyfr). It persists orders
```

(The rest of the README is rewritten for a generated project in PR 4; its remaining "reference service" prose stays until then.)

```bash
git grep -n -w 8000 -- . ':!ops/grafana' ':!openapi*.json'
cd ..
```

Expected: nothing.

- [ ] **Step 6: Make the template's pre-commit configuration project-relative**

Rewrite `{{cookiecutter.project_slug}}/.pre-commit-config.yaml` to:

```yaml
# pre-commit only installs the git hook types it is told to; `pre-commit
# install` with no arguments wires up the `pre-commit` stage.
default_install_hook_types: [pre-commit]

repos:
  # ruff and uv run from the environment uv.lock pins -- the ONE place
  # their versions live (ADR 0014). `language: system` runs the command
  # as-is and the command resolves the tool through uv.
  - repo: local
    hooks:
      # No --fix here. `just check`'s precommit recipe runs this hook, and
      # "check" must never mutate the tree. `just lint` checks, `just fmt`
      # fixes; this hook mirrors `just lint`.
      - id: ruff-check
        name: ruff check
        entry: uv run ruff check --force-exclude
        language: system
        types_or: [python, pyi]
        require_serial: true
      - id: ruff-format
        name: ruff format --check
        entry: uv run ruff format --check --force-exclude
        language: system
        types_or: [python, pyi]
        require_serial: true
      - id: uv-lock
        name: uv lock --check
        entry: uv lock --check
        language: system
        pass_filenames: false
        files: ^(pyproject\.toml|uv\.lock)$

  - repo: https://github.com/gitleaks/gitleaks
    rev: v8.30.1
    hooks:
      - id: gitleaks

  - repo: https://github.com/sqlfluff/sqlfluff
    rev: 4.3.0
    hooks:
      - id: sqlfluff-lint
        files: ^migrations/.*\.sql$

  - repo: https://github.com/pre-commit/pre-commit-hooks
    rev: v6.0.0
    hooks:
      - id: end-of-file-fixer
      - id: trailing-whitespace
      - id: check-yaml
      - id: check-toml
      - id: check-merge-conflict
```

Keep the `rev:` values equal to the root file's. The Commitizen hook returns in PR 3 with the generated project's own Commitizen.

- [ ] **Step 7: Make the template's `precommit` recipe nesting-aware**

In `{{cookiecutter.project_slug}}/justfile`, replace the `precommit` recipe (its comment and its one command) with:

```just
# The project's own git hooks over its own tracked files.
#
# pre-commit runs from the root of the enclosing git repository and resolves
# hook commands there. When this project is generated into a subdirectory of
# an existing repository — PyFr's own examples/reference-service/ is one —
# that repository's root configuration owns the hooks and this one cannot
# run; say so and exit clean rather than fail on paths that do not resolve.
precommit:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "$(git rev-parse --show-prefix)" ]; then
        echo "precommit: nested inside another repository; its root pre-commit configuration covers this tree."
        exit 0
    fi
    uv run pre-commit run --files $(git ls-files)
```

- [ ] **Step 8: Run the generation test**

```bash
uv run --group dev pytest tests/test_generation.py tests/test_hooks.py -q
```

Expected: all pass.

- [ ] **Step 9: Commit**

```bash
git add '{{cookiecutter.project_slug}}' tests/test_generation.py
git commit -m "feat: substitute the identity answers and guard the jinja collisions in the template body"
```

---

### Task 6: `scripts/regen.py`, the reference answers, and the first regeneration

**Files:**
- Create: `scripts/regen.py`, `tests/reference-answers.yaml`
- Modify: `justfile` (root)
- Test: `tests/test_regen.py`
- Regenerate: `examples/reference-service/**`

**Interfaces:**
- Produces: `scripts/regen.py` with functions `load_answers(path) -> dict[str, str]`, `render(template_root, answers, output_dir) -> Path`, `compare(rendered, example) -> Comparison`, `sync(rendered, example) -> None`, `adopt(rendered, example, template_body, answers) -> list[str]`, and a CLI with `--check` and `--adopt`; root recipes `regen`, `regen-check`, `adopt`.

- [ ] **Step 1: Write the failing unit tests for compare, sync and adopt**

`tests/test_regen.py`:

```python
"""scripts/regen.py on a tiny fake template -- no cookiecutter, no network.

`render` is exercised by tests/test_golden.py against the real template;
here the render is a directory the test writes by hand.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import regen  # noqa: E402

ANSWERS = {"project_slug": "demo", "package_name": "demo", "license": "MIT"}
PINS_TEMPLATE = "pin = 1\nname = {{ cookiecutter.project_slug }}\n"


def git(example: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=example, check=True, capture_output=True)


@pytest.fixture
def trees(tmp_path: Path) -> tuple[Path, Path, Path]:
    template_body = tmp_path / "{{cookiecutter.project_slug}}"
    package = template_body / "src" / "{{cookiecutter.package_name}}"
    package.mkdir(parents=True)
    (template_body / "pins.txt").write_text(PINS_TEMPLATE)
    (package / "a.py").write_text("X = 1\n")
    (template_body / "LICENSE.MIT").write_text("MIT\n")
    (template_body / "LICENSE.MPL-2.0").write_text("MPL\n")

    rendered = tmp_path / "rendered" / "demo"
    (rendered / "src" / "demo").mkdir(parents=True)
    (rendered / "pins.txt").write_text("pin = 1\nname = demo\n")
    (rendered / "src" / "demo" / "a.py").write_text("X = 1\n")
    (rendered / "LICENSE").write_text("MIT\n")

    example = tmp_path / "example"
    example.mkdir()
    git(example, "init", "-q")
    git(example, "config", "user.email", "t@example.com")
    git(example, "config", "user.name", "t")
    return template_body, rendered, example


def commit_all(example: Path) -> None:
    git(example, "add", "-A")
    git(example, "commit", "-q", "-m", "x")


def test_compare_reports_missing_extra_and_differing(trees) -> None:
    _, rendered, example = trees
    (example / "pins.txt").write_text("pin = 2\nname = demo\n")
    (example / "stale.txt").write_text("gone from the template\n")
    (example / "uv.lock").write_text("resolver output\n")
    commit_all(example)

    comparison = regen.compare(rendered, example)

    assert comparison.missing == ["LICENSE", "src/demo/a.py"]
    assert comparison.extra == ["stale.txt"]
    assert comparison.differing == ["pins.txt"]
    assert not comparison.clean


def test_sync_writes_the_render_and_removes_tracked_leftovers(trees) -> None:
    _, rendered, example = trees
    (example / "stale.txt").write_text("gone\n")
    (example / "uv.lock").write_text("resolver output\n")
    commit_all(example)
    # Untracked, like a virtual environment: never the render's to remove.
    (example / ".venv").mkdir()
    (example / ".venv" / "keep").write_text("ignored, untracked\n")

    regen.sync(rendered, example)

    assert (example / "src" / "demo" / "a.py").read_text() == "X = 1\n"
    assert (example / "LICENSE").read_text() == "MIT\n"
    assert not (example / "stale.txt").exists()
    assert (example / "uv.lock").read_text() == "resolver output\n"
    assert (example / ".venv" / "keep").exists()
    # sync writes files and leaves staging to the caller, as `just regen`
    # does: stage the deletion and the new files, then the check is clean.
    git(example, "add", "-u")
    git(example, "add", "--", "src", "LICENSE")
    assert regen.compare(rendered, example).clean


def test_adopt_copies_a_changed_line_back_into_the_template(trees) -> None:
    template_body, rendered, example = trees
    regen.sync(rendered, example)
    commit_all(example)
    (example / "pins.txt").write_text("pin = 2\nname = demo\n")

    adopted = regen.adopt(rendered, example, template_body, ANSWERS)

    assert adopted == ["pins.txt"]
    expected = PINS_TEMPLATE.replace("pin = 1", "pin = 2")
    assert (template_body / "pins.txt").read_text() == expected


def test_adopt_maps_rendered_paths_back_to_template_paths(trees) -> None:
    template_body, rendered, example = trees
    regen.sync(rendered, example)
    commit_all(example)
    (example / "src" / "demo" / "a.py").write_text("X = 2\n")
    (example / "LICENSE").write_text("MIT, amended\n")

    adopted = regen.adopt(rendered, example, template_body, ANSWERS)

    assert adopted == ["LICENSE", "src/demo/a.py"]
    package = template_body / "src" / "{{cookiecutter.package_name}}"
    assert (package / "a.py").read_text() == "X = 2\n"
    assert (template_body / "LICENSE.MIT").read_text() == "MIT, amended\n"


def test_adopt_refuses_a_change_it_cannot_express(trees) -> None:
    template_body, rendered, example = trees
    regen.sync(rendered, example)
    commit_all(example)
    # An inserted line, not a replaced one.
    (example / "pins.txt").write_text("pin = 1\nextra = true\nname = demo\n")

    with pytest.raises(regen.AdoptError, match="pins.txt"):
        regen.adopt(rendered, example, template_body, ANSWERS)


def test_adopt_refuses_a_line_that_is_not_unique_in_the_template(trees) -> None:
    template_body, rendered, example = trees
    (template_body / "pins.txt").write_text("pin = 1\n" + PINS_TEMPLATE)
    (rendered / "pins.txt").write_text("pin = 1\npin = 1\nname = demo\n")
    regen.sync(rendered, example)
    commit_all(example)
    (example / "pins.txt").write_text("pin = 2\npin = 1\nname = demo\n")

    with pytest.raises(regen.AdoptError, match="exactly once"):
        regen.adopt(rendered, example, template_body, ANSWERS)
```

- [ ] **Step 2: Run them to see them fail**

```bash
uv run --group dev pytest tests/test_regen.py -q
```

Expected: `ModuleNotFoundError: No module named 'regen'`.

- [ ] **Step 3: Write `scripts/regen.py`**

```python
#!/usr/bin/env python3
"""Regenerate examples/reference-service from the template -- or check it, or
adopt its edits back.

The template body, {{cookiecutter.project_slug}}/, is the only source of
truth; examples/reference-service/ is rendered from it with the answers in
tests/reference-answers.yaml (spec M7-1). Three modes:

  regen.py            render and sync the render into the example
  regen.py --check    render and compare; exit 1 on any difference
  regen.py --adopt    copy each line changed in the example back into the
                      template file that renders it, then check

`--adopt` exists for Dependabot (spec M7-10): it edits the rendered example
because it cannot parse Jinja. A pin line never contains Jinja, so the
replacement is literal; any other shape of change is refused with the file
name, and is made in the template by hand.

The render runs with PYFR_REGEN set, so the post-generation hook prunes and
stops: no git init, no uv sync, no network. uv.lock is the one file outside
the comparison -- resolver output, not template content (spec M7-4).
"""

from __future__ import annotations

import argparse
import difflib
import os
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from jinja2 import Environment

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE_BODY = ROOT / "{{cookiecutter.project_slug}}"
EXAMPLE = ROOT / "examples" / "reference-service"
ANSWERS_FILE = ROOT / "tests" / "reference-answers.yaml"

# Resolver output, not template content (spec M7-4).
EXCLUDED = frozenset({"uv.lock"})

# The post-generation hook keeps the chosen LICENSE.<choice> as LICENSE, so
# that one rendered path maps back to a template path the answers decide.
LICENCE_FILES = {
    "Apache-2.0": "LICENSE.Apache-2.0",
    "MIT": "LICENSE.MIT",
    "MPL-2.0": "LICENSE.MPL-2.0",
    "Proprietary": "LICENSE.Proprietary",
}


class AdoptError(Exception):
    """A change in the example that --adopt cannot express in the template."""


@dataclass
class Comparison:
    missing: list[str] = field(default_factory=list)  # in the render, not tracked
    extra: list[str] = field(default_factory=list)  # tracked, not in the render
    differing: list[str] = field(default_factory=list)

    @property
    def clean(self) -> bool:
        return not (self.missing or self.extra or self.differing)


def load_answers(path: Path = ANSWERS_FILE) -> dict[str, str]:
    with path.open() as handle:
        answers = yaml.safe_load(handle)
    return {key: str(value) for key, value in answers.items()}


def render(
    template_root: Path, answers: dict[str, str], output_dir: Path
) -> Path:
    # Imported here so the unit tests of compare/sync/adopt need no
    # cookiecutter at all.
    from cookiecutter.main import cookiecutter

    os.environ["PYFR_REGEN"] = "1"
    return Path(
        cookiecutter(
            str(template_root),
            no_input=True,
            extra_context=answers,
            output_dir=str(output_dir),
        )
    )


def files_under(root: Path) -> set[str]:
    return {
        path.relative_to(root).as_posix()
        for path in root.rglob("*")
        if path.is_file()
    }


def tracked_files(example: Path) -> set[str]:
    listed = subprocess.run(
        ["git", "ls-files", "-z"],
        cwd=example,
        check=True,
        capture_output=True,
    ).stdout
    return {name for name in listed.decode().split("\0") if name}


def compare(rendered: Path, example: Path) -> Comparison:
    wanted = files_under(rendered) - EXCLUDED
    present = tracked_files(example) - EXCLUDED
    comparison = Comparison(
        missing=sorted(wanted - present),
        extra=sorted(present - wanted),
    )
    for name in sorted(wanted & present):
        if (rendered / name).read_bytes() != (example / name).read_bytes():
            comparison.differing.append(name)
    return comparison


def sync(rendered: Path, example: Path) -> None:
    wanted = files_under(rendered) - EXCLUDED
    for name in wanted:
        target = example / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes((rendered / name).read_bytes())
    # Only tracked leftovers go: untracked and ignored files (.venv, the
    # caches, uv.lock) are never the render's to remove.
    for name in tracked_files(example) - EXCLUDED - wanted:
        stale = example / name
        if stale.exists():
            stale.unlink()
        parent = stale.parent
        while parent != example and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent


def template_paths(template_body: Path, answers: dict[str, str]) -> dict[str, str]:
    """Rendered relative path -> template relative path."""
    env = Environment(keep_trailing_newline=True)
    mapping: dict[str, str] = {}
    for name in files_under(template_body):
        rendered_name = env.from_string(name).render(cookiecutter=answers)
        mapping[rendered_name] = name
    for choice, file_name in LICENCE_FILES.items():
        mapping.pop(file_name, None)
        if answers.get("license") == choice:
            mapping["LICENSE"] = file_name
    return mapping


def adopt(
    rendered: Path,
    example: Path,
    template_body: Path,
    answers: dict[str, str],
) -> list[str]:
    comparison = compare(rendered, example)
    if comparison.missing or comparison.extra:
        raise AdoptError(
            "adopt handles changed files only; "
            f"missing={comparison.missing} extra={comparison.extra}"
        )
    mapping = template_paths(template_body, answers)
    adopted: list[str] = []
    for name in comparison.differing:
        template_file = template_body / mapping[name]
        old_lines = (rendered / name).read_text().splitlines(keepends=True)
        new_lines = (example / name).read_text().splitlines(keepends=True)
        text = template_file.read_text()
        matcher = difflib.SequenceMatcher(None, old_lines, new_lines, autojunk=False)
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            if tag == "equal":
                continue
            if tag != "replace":
                raise AdoptError(
                    f"{name}: lines were {tag}d, not replaced; "
                    "make this change in the template by hand"
                )
            old = "".join(old_lines[i1:i2])
            new = "".join(new_lines[j1:j2])
            if text.count(old) != 1:
                raise AdoptError(
                    f"{name}: the changed lines must appear exactly once in "
                    f"{mapping[name]} (found {text.count(old)}); "
                    "make this change in the template by hand"
                )
            text = text.replace(old, new)
        template_file.write_text(text)
        adopted.append(name)
    return adopted


def report(comparison: Comparison, rendered: Path, example: Path) -> None:
    for name in comparison.missing:
        print(f"missing from the example: {name}")
    for name in comparison.extra:
        print(f"tracked in the example but not in the template: {name}")
    for name in comparison.differing:
        print(f"differs: {name}")
    if comparison.differing:
        first = comparison.differing[0]
        diff = difflib.unified_diff(
            (example / first).read_text().splitlines(keepends=True),
            (rendered / first).read_text().splitlines(keepends=True),
            fromfile=f"examples/reference-service/{first}",
            tofile=f"rendered/{first}",
        )
        sys.stdout.writelines(diff)
    print()
    print("The template is the source of truth: edit {{cookiecutter.project_slug}}/")
    print("and run `just regen`. Never edit examples/reference-service/ by hand.")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--check", action="store_true", help="compare; do not write")
    mode.add_argument(
        "--adopt",
        action="store_true",
        help="copy the example's changed lines into the template, then compare",
    )
    args = parser.parse_args(argv)

    answers = load_answers()
    with tempfile.TemporaryDirectory() as scratch:
        rendered = render(ROOT, answers, Path(scratch))
        if args.adopt:
            adopted = adopt(rendered, EXAMPLE, TEMPLATE_BODY, answers)
            for name in adopted:
                print(f"adopted into the template: {name}")
            again = Path(scratch) / "again"
            again.mkdir()
            rendered = render(ROOT, answers, again)
        if args.check or args.adopt:
            comparison = compare(rendered, EXAMPLE)
            if comparison.clean:
                print("examples/reference-service matches the template.")
                return 0
            report(comparison, rendered, EXAMPLE)
            return 1
        sync(rendered, EXAMPLE)
        print("examples/reference-service regenerated.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
```

`pyyaml` and `jinja2` are already in the root environment (`pyyaml` in `dev`; `jinja2` arrives with cookiecutter). Add `"jinja2>=3.1"` to the root `dev` group with a one-line comment (`# scripts/regen.py renders template paths with it directly (adopt)`) so the import is declared, then `uv lock`.

- [ ] **Step 4: Run the unit tests**

```bash
uv run --group dev pytest tests/test_regen.py -q
just lint
```

Expected: 6 passed; ruff clean.

- [ ] **Step 5: Write the reference answers and the recipes**

`tests/reference-answers.yaml`:

```yaml
# The answers examples/reference-service/ is rendered from. Everything on;
# the names the reference service has carried since M0. PR 2 adds the three
# backend answers when their prompts exist.
project_name: Reference Service
project_slug: reference-service
package_name: reference_service
description: The PyFr reference service.
author_name: Emad Mokhtar
author_email: 311636+EmadMokhtar@users.noreply.github.com
github_org: EmadMokhtar
http_port: "8000"
license: MPL-2.0
```

Root `justfile`, after `precommit`:

```just
# Regenerate examples/reference-service from the template with the answers in
# tests/reference-answers.yaml. The template is the source of truth; run this
# after every change to {{cookiecutter.project_slug}}/ and commit the result.
regen:
    uv run --group dev python scripts/regen.py

# The golden diff: render and compare, writing nothing. CI's `golden` job.
regen-check:
    uv run --group dev python scripts/regen.py --check

# Copy Dependabot's edits to the rendered example back into the template,
# then check. Only for line-for-line replacements (a pin bump); anything else
# fails with the file name and is made in the template by hand.
adopt:
    uv run --group dev python scripts/regen.py --adopt
```

And change `check: docs-build test` to `check: docs-build test regen-check`.

- [ ] **Step 6: Regenerate, and read the diff**

```bash
just regen
git status --short | grep -v '^R' | head -40
git diff --stat -- examples/reference-service | tail -3
```

Expected: `examples/reference-service/` is re-created. In `git status`, the moved files reappear as modifications or additions under `examples/reference-service/`, and the only *content* differences from the pre-move tree are the ones this PR intends. Check them explicitly:

```bash
git diff origin/main -- examples/reference-service --stat
git diff origin/main -- examples/reference-service | grep '^[+-]' | grep -v '^[+-][+-]' | grep -v -E 'LICENSE|\.gitignore' | head -60
```

Expected content changes, and no others:

- `LICENSE` (new, MPL-2.0 text) and `.gitignore` (new).
- `README.md`: the title and first sentence.
- `pyproject.toml`: `description` and `authors`.
- `src/reference_service/__init__.py`: the docstring.
- `.pre-commit-config.yaml`: the project-relative rewrite.
- `justfile`: the `precommit` recipe; image names `pyfr-reference-service` → `reference-service`; the registry default's case is unchanged (`ghcr.io/emadmokhtar`).
- `Dockerfile`, `Dockerfile.migrations`: the `image.source` label → `https://github.com/EmadMokhtar/reference-service`.
- `ops/grafana/provisioning/dashboards/pyfr-dashboards.yaml`: the comment.
- `.sqlfluff`: nothing (the raw guard renders back to the original comment).

If anything else differs, the substitution in Task 5 was wrong there; fix it in the template body and `just regen` again. `openapi.json` must show **no** change.

- [ ] **Step 7: Prove the example still passes its own gates**

```bash
cd examples/reference-service
uv sync
just check
cd ../..
```

Expected: lint, typecheck, imports and tests pass, then `precommit: nested inside another repository; …` and exit 0, then the `git diff --exit-code` inside `check` passes. `uv sync` must report the lock is unchanged (`pyproject.toml`'s dependency set did not change; `description`/`authors` do not affect the lock — if `uv sync` rewrites `uv.lock`, stop: something in `pyproject.toml` moved that should not have).

- [ ] **Step 8: Add the golden test**

`tests/test_golden.py`:

```python
"""The golden diff: rendering the template with the reference answers
reproduces examples/reference-service/ byte for byte (uv.lock excepted).

The same command CI's `golden` job runs. It fails with the list of files
and a unified diff of the first, so a hand edit to the example is caught
with its location, not a bare "mismatch".
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_the_example_matches_the_template() -> None:
    completed = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "regen.py"), "--check"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
```

`compare` reads the example's *tracked* files (`git ls-files`), so the regenerated tree must be staged before the check sees it:

```bash
git add examples/reference-service
uv run --group dev pytest tests/test_golden.py -q
just regen-check
```

Expected: `1 passed`; `examples/reference-service matches the template.`

- [ ] **Step 9: Commit**

```bash
git add scripts/regen.py tests/test_regen.py tests/reference-answers.yaml tests/test_golden.py justfile pyproject.toml uv.lock examples/reference-service
git commit -m "feat: regenerate the reference service from the template and gate it with a golden diff"
```

---

### Task 7: Root generation test for the reference answers

**Files:**
- Modify: `tests/test_generation.py`

- [ ] **Step 1: Add the reference-answers render checks**

Append to `tests/test_generation.py`:

```python
def test_the_reference_answers_render_the_reference_names(cookies) -> None:
    answers = yaml.safe_load(REFERENCE_ANSWERS.read_text())
    result = cookies.bake(extra_context={k: str(v) for k, v in answers.items()})
    assert result.exit_code == 0, result.exception
    assert result.project_path.name == "reference-service"
    package = result.project_path / "src" / "reference_service"
    assert (package / "main.py").is_file()
    pyproject = (result.project_path / "pyproject.toml").read_text()
    assert 'name = "reference-service"' in pyproject
    assert "Emad Mokhtar" in pyproject
    assert (result.project_path / "LICENSE").read_text().startswith(
        "Mozilla Public License Version 2.0"
    )


def test_a_custom_port_reaches_every_place_the_port_lives(cookies) -> None:
    result = cookies.bake(extra_context={"http_port": "9000"})
    assert result.exit_code == 0, result.exception
    root = result.project_path
    assert "EXPOSE 9000" in (root / "Dockerfile").read_text()
    assert '"9000:9000"' in (root / "compose.yaml").read_text()
    assert "APP_HTTP_PORT=9000" in (root / ".env.example").read_text()
    assert "default=9000" in (root / "src" / "my_service" / "settings.py").read_text()
    assert "== 9000" in (root / "tests" / "unit" / "test_settings.py").read_text()


def test_dashboards_are_copied_verbatim(cookies) -> None:
    result = cookies.bake()
    assert result.exit_code == 0, result.exception
    for name in ("runtime.json", "service-health.json", "slo.json"):
        rendered = result.project_path / "ops" / "grafana" / "dashboards" / name
        source = ROOT / "{{cookiecutter.project_slug}}" / "ops" / "grafana" / "dashboards" / name
        assert rendered.read_bytes() == source.read_bytes()
```

- [ ] **Step 2: Run, lint, commit**

```bash
uv run --group dev pytest tests -q
just lint
git add tests/test_generation.py
git commit -m "test: check the reference answers, a custom port and verbatim dashboards"
```

Expected: every root test passes; ruff clean.

---

### Task 8: CI — the `golden` and `precommit` jobs, and `release.yml`'s image names

**Files:**
- Modify: `.github/workflows/ci.yml`, `.github/workflows/release.yml`

- [ ] **Step 1: Add the two jobs to `ci.yml`**

After the `check` job:

```yaml
  golden:
    # The template is the source of truth and examples/reference-service/ is
    # rendered from it (M7 spec, M7-1). This job fails when the two disagree,
    # with the list of files and a diff of the first -- see
    # docs/contributing.md, "Edit the template, then just regen".
    #
    # Dependabot edits the rendered example, not the template: it cannot
    # parse Jinja. On its pull requests -- and on the push that merges one --
    # adopt its pin changes into the template first (M7-10). adopt.yml then
    # commits the same result to main.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Install uv
        uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true

      - name: Install just
        uses: extractions/setup-just@v4

      - name: Install the toolchain
        run: uv sync --group dev

      - name: Adopt Dependabot's pins into the template
        if: github.actor == 'dependabot[bot]' || github.event.head_commit.author.name == 'dependabot[bot]'
        run: just adopt

      - name: Render and compare
        run: just regen-check

  precommit:
    # The repository's own hooks over every tracked file, from the root
    # configuration. The `check` job's `just check` inside the example runs
    # the example's precommit recipe, which skips itself when nested; this
    # is the job that covers that tree, and the root's own files.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Install uv
        uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true

      - name: Install just
        uses: extractions/setup-just@v4

      - name: Install the toolchain
        # ruff runs from the root's environment; `uv lock --check --project`
        # needs no environment; the remote hooks bring their own.
        run: uv sync --group dev

      - name: Run every hook
        run: just precommit
```

Copy the exact `uses:` versions from the existing `check` job if they differ from the above.

- [ ] **Step 2: Rename the images in `release.yml`**

Replace the two occurrences of `ghcr.io/emadmokhtar/pyfr-reference-service` with `ghcr.io/emadmokhtar/reference-service` (lines 339–340 today). Read the comment at line 287 and the `sbom` step; adjust any other mention of `pyfr-reference-service` the grep finds:

```bash
grep -rn 'pyfr-reference-service' .github docs README.md
```

Every hit outside `docs/` is changed in this task; the `docs/` hits are Task 12's.

- [ ] **Step 3: Validate the workflow files and commit**

```bash
uv run --group dev pre-commit run check-yaml --files .github/workflows/ci.yml .github/workflows/release.yml
git add .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "ci: add the golden diff and root pre-commit jobs; publish images under the rendered name"
```

---

### Task 9: `adopt.yml`

**Files:**
- Create: `.github/workflows/adopt.yml`

- [ ] **Step 1: Write the workflow**

```yaml
# After a Dependabot pull request merges, copy its pin changes from the
# rendered example into the template (M7 spec, M7-10). The pull request's
# `golden` job already ran `just adopt` and proved the result renders back
# clean, so this commit is that proven result, not a new experiment.
#
# The push uses the workflow token, so it starts no new CI run -- the same
# arrangement release.yml has for its bump commit, and the same token
# requirements docs/contributing.md lists (write permission; branch
# protection that lets the actions bot push).
name: Adopt Dependabot pins

on:
  push:
    branches: [main]

permissions:
  contents: write

jobs:
  adopt:
    if: github.event.head_commit.author.name == 'dependabot[bot]'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Install uv
        uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true

      - name: Install just
        uses: extractions/setup-just@v4

      - name: Install the toolchain
        run: uv sync --group dev

      - name: Adopt into the template
        run: just adopt

      - name: Commit and push the template change
        run: |
          if git diff --quiet -- '{{cookiecutter.project_slug}}'; then
            echo "Nothing to adopt: the template already matches."
            exit 0
          fi
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"
          git add -- '{{cookiecutter.project_slug}}'
          git commit -m "build(deps): adopt dependabot's pins into the template"
          git push
```

- [ ] **Step 2: Validate and commit**

```bash
uv run --group dev pre-commit run check-yaml --files .github/workflows/adopt.yml
git add .github/workflows/adopt.yml
git commit -m "ci: adopt dependabot's pins into the template after each merge"
```

---

### Task 10: Dependabot for the root's pre-commit configuration

**Files:**
- Modify: `.github/dependabot.yml`

- [ ] **Step 1: Add the root `pre-commit` entry**

The root `.pre-commit-config.yaml` now carries `rev:` pins of its own. Next to the existing `pre-commit` entry for `/examples/reference-service`, add one for `/`, copying its `schedule` and `commit-message` blocks exactly:

```yaml
  - package-ecosystem: "pre-commit"
    directory: "/"
    # The repository's own hooks (root .pre-commit-config.yaml). The entry
    # above keeps the reference service's -- which is the template's, through
    # `just adopt` (M7-10).
```

followed by the same `schedule:` and `commit-message:` lines the sibling entry uses.

- [ ] **Step 2: Validate and commit**

```bash
uv run --group dev pre-commit run check-yaml --files .github/dependabot.yml
git add .github/dependabot.yml
git commit -m "ci(dependabot): watch the repository's own pre-commit configuration"
```

---

### Task 11: ADR 0017

**Files:**
- Create: `docs/adr/0017-the-template-is-the-source-of-truth.md`
- Modify: `docs/adr/README.md`, `mkdocs.yml`

- [ ] **Step 1: Write the record**

Follow `docs/adr/template.md`'s headings exactly (read it first). Content:

```markdown
---
last_reviewed: 2026-09-12
covers:
  - scripts/regen.py
  - tests/reference-answers.yaml
---

# 0017 The template is the source of truth, and a golden diff proves it

## Status

Accepted — M7, PR 1.

## Context

Phase A built `examples/reference-service/` as ordinary Python so that no
one ever debugged Jinja and Python at the same time (ADR 0002, the
original specification's section 3.3). Phase B turns that tree into the
template body, `{{cookiecutter.project_slug}}/`. From then on two trees
describe one service, and the question is which one a contributor edits and
what stops the other from drifting.

Two alternatives were rejected. Keeping the example hand-maintained and
adding the golden diff only at the end of M7 leaves four pull requests in
which the trees can disagree with nothing enforcing agreement. Deriving the
template from the example mechanically cannot express pruning or the
`{% raw %}` guards.

## Decision

The template body is the only source of truth from the first M7 pull
request. `examples/reference-service/` is rendered from it by
`scripts/regen.py` with the fixed answers in `tests/reference-answers.yaml`,
under `PYFR_REGEN` so the render has no side effects, and is committed as
output. `just regen-check` — the `golden` CI job and `tests/test_golden.py` —
fails when the render and the committed example differ by a byte.

One file is outside the comparison: `uv.lock`. A lock is resolver output
for one dependency set, and pruning produces eight; it cannot be a Jinja
document. The example's lock is kept and checked against its regenerated
`pyproject.toml` by `uv lock --check`.

Dependabot edits the rendered example because it cannot parse Jinja. `just
adopt` copies each changed line back into the template file that renders
it; a change that is not a line-for-line replacement is refused and made by
hand.

## Consequences

- Contributors edit `{{cookiecutter.project_slug}}/` and run `just regen`;
  a hand edit to the example fails the build with the file named.
- Every pull request that touches the template shows its effect on the
  example as an ordinary file diff.
- The example's `git blame` restarts at this decision; the history of its
  files continues in the template body, where `git mv` carried it.
- `ruff`, `mypy` and `import-linter` cannot run on the template body. They
  run on the example on every push, and — from PR 5 — on three sampled
  renders on merge.
```

- [ ] **Step 2: Register it**

In `docs/adr/README.md`, add the row `| 0017 | [The template is the source of truth, and a golden diff proves it](0017-the-template-is-the-source-of-truth.md) | M7 |` after 0016, matching the table's columns exactly. In `mkdocs.yml`, under `Decisions:`, add `- 0017 The template is the source of truth: adr/0017-the-template-is-the-source-of-truth.md` after the 0016 line.

- [ ] **Step 3: Build and commit**

```bash
just docs-build
git add docs/adr/0017-the-template-is-the-source-of-truth.md docs/adr/README.md mkdocs.yml
git commit -m "docs(adr): record that the template is the source of truth"
```

---

### Task 12: The root documentation

**Files:**
- Modify: `docs/contributing.md`, `docs/reference/commands.md`, `docs/reference/supply-chain.md`, `docs/reference/observability.md`, `docs/adr/0015-images-are-published-on-release-under-the-repository-version.md`, `docs/roadmap.md`, `docs/index.md`

- [ ] **Step 1: `contributing.md`**

1. "Repository layout": add the lines `  cookiecutter.json  hooks/       the template's prompts and hooks` and `  {{cookiecutter.project_slug}}/  the template body — the source of truth` above `examples/reference-service/`, and change that line's description to `rendered from the template; never edited by hand`.
2. "Working on the reference service": rename the section **"Working on the template"** and replace its first two code blocks and the paragraph between them with:

   ```markdown
   From the repository root:

   ```bash
   uv sync --group dev && uv run pre-commit install
   ```

   Edit `{{cookiecutter.project_slug}}/`, then:

   ```bash
   just regen
   ```

   That renders the template with `tests/reference-answers.yaml` into
   `examples/reference-service/` and is the only way that directory changes.
   `just regen-check` (CI's `golden` job) fails the build when the two
   disagree, naming the files. Then run the example's own gates:

   ```bash
   cd examples/reference-service && just check
   ```

   The example's `just precommit` steps aside inside this repository — the
   root's `.pre-commit-config.yaml` owns the hooks here, and `just precommit`
   at the root runs them over every tracked file.
   ```
   Keep the `just security` paragraph and the rest of the section.
3. Add a subsection **"Dependabot and the template"** after it:

   ```markdown
   Dependabot's `directory` entries point at `examples/reference-service/`
   because it cannot parse Jinja. Its pull requests therefore change the
   rendered example, not the template. The `golden` job runs `just adopt`
   first on those pull requests, and `.github/workflows/adopt.yml` commits
   the same result to `main` after the merge. `adopt` copies a replaced
   line back into the template file that renders it; a change of any other
   shape — an inserted hook, a new dependency — fails with the file name,
   and you make it in the template by hand.
   ```
4. "Seven settings live in the GitHub interface": change to "Eight", and add the bullet `- **`adopt.yml` pushes to `main`** under the same write permission and branch-protection exemption as `release.yml`.` after the branch-protection bullet. In the GHCR bullet, replace `pyfr-reference-service` and `pyfr-reference-service-migrations` with `reference-service` and `reference-service-migrations`, and add: `The names changed in M7 — an image is named for the generated project, and the reference answers name it `reference-service`.`
5. Bump `last_reviewed` to `2026-09-12` and add `scripts/regen.py` to `covers:`.

- [ ] **Step 2: `commands.md`**

In the root recipes table add rows for `just precommit`, `just regen`, `just regen-check` and `just adopt`, one sentence each, copied from the recipes' comments in Task 2 and Task 6. Change the `just check` (root) row to `docs-build`, `test` and `regen-check`. In the service's `just precommit` row, add: `Inside this repository it skips itself and says so; the root's `just precommit` covers the tree.` Bump `last_reviewed`.

- [ ] **Step 3: Image names in `supply-chain.md` and ADR 0015**

```bash
grep -n 'pyfr-reference-service' docs/reference/supply-chain.md docs/adr/0015-*.md docs/runbook.md docs/guides/run-in-a-container.md
```

Replace every `pyfr-reference-service` with `reference-service` and every `pyfr-reference-service-migrations` with `reference-service-migrations`. In `supply-chain.md`, where the publishing section names the images, add one sentence: `The image name is the generated project's `project_slug`; the reference answers name it `reference-service`.` Bump `last_reviewed` on each page touched.

- [ ] **Step 3b: ADR 0014 — the second ruff pin**

`docs/adr/0014-dependabot-and-one-pin-per-tool.md` lists the known remaining exceptions to "one pin per tool". Add one entry in that list's own format: `ruff is pinned in both locks — the root's, for `hooks/`, `scripts/` and `tests/`, and the reference service's, which is the template's. Two projects, two locks, and Dependabot's `uv` entries move both.` Bump its `last_reviewed`.

- [ ] **Step 4: `observability.md` — changing the objective**

Add a section at the end, before any glossary or "see also":

```markdown
## Changing the objective

The objective — 99.9% of requests succeed, and 99.9% finish within 300 ms,
over a rolling 30 days — is not a prompt. It lives in five places that the
tests hold together, and changing it is an ordinary edit to all five:

| Place | What it holds |
|---|---|
| `src/reference_service/observability/slo.py` | `SLO_AVAILABILITY_TARGET`, `SLO_LATENCY_THRESHOLD_SECONDS`, the rounded `ERROR_BUDGET` |
| `src/reference_service/observability/otel.py` | `HTTP_DURATION_BUCKET_BOUNDARIES` — the latency threshold must be a bucket boundary, or the `le` matcher below counts nothing |
| `ops/prometheus/rules/slo.yml` | the `le="0.3"` matchers and the burn-rate multipliers of the error budget |
| `ops/prometheus/slo_test.yml` | the synthetic series and the alert summaries `just o11y-gates` asserts |
| `ops/grafana/dashboards/slo.json` | the two threshold values the SLO dashboard draws |

`tests/unit/test_slo.py` and `test_slo_rules.py` fail when the first three
disagree; `just o11y-gates` fails when the rules and their test disagree.
The dashboard is the one place nothing checks.
```

Bump `last_reviewed`.

- [ ] **Step 5: `roadmap.md` and `index.md`**

In `roadmap.md`, change the M7 row's State to `**In progress**` and its last cell to: `The reference service becomes the template in five pull requests. The first moved the tree under `{{cookiecutter.project_slug}}/`, added `cookiecutter.json` with the identity, port and licence prompts, both hooks, `just regen` and the golden diff that makes the template the source of truth (ADR 0017). Still to come: backend prompts and pruning, a generated project's own workflows, its own documentation site, and the full-suite tests. **PyFr becomes a usable template at the end of M7.**` Change the bold status line to `**M0, M1, M2, M3, M4, M5 and M6 are done; M7 is in progress.**`. In `index.md`, change the status admonition's title to `"Status: M0–M6 done, M7 in progress, M8 to go"`. Bump both pages' `last_reviewed`.

- [ ] **Step 6: Build, check links, run the freshness check, commit**

```bash
just docs-build
just links
just docs-freshness origin/main HEAD
git add docs mkdocs.yml
git commit -m "docs: describe the template as the source of truth and the regen, adopt and precommit recipes"
```

Expected: `--strict` build clean; lychee 0 errors; the freshness check prints no warning for a page whose `covers:` path moved without the page changing (if it names `scripts/regen.py` on a page you did not touch, touch that page).

---

### Task 13: Full verification

- [ ] **Step 1: Everything the repository checks**

```bash
just check                      # docs-build, root tests, regen-check
just precommit                  # root hooks over every tracked file
cd examples/reference-service && just check && cd ../..
```

Expected: all green. `just precommit` must not modify any file (`git status --short` empty afterwards).

- [ ] **Step 2: Generate a project that is not the reference, and run its gates**

This is definition-of-done item 1 for the everything-on configuration, with the hook's side effects live:

```bash
rm -rf /tmp/pyfr-smoke && mkdir /tmp/pyfr-smoke
uv run --group dev cookiecutter . --no-input -o /tmp/pyfr-smoke \
  project_name="Demo Service" github_org=acme http_port=9000 license=MIT
cd /tmp/pyfr-smoke/demo-service
git log --oneline
ls LICENSE .gitignore uv.lock .git >/dev/null && echo "set up"
just check
cd -
```

Expected: one commit `chore: generate the project from pyfr`; the four paths exist; `just check` passes including the real `precommit` (this project is its own git root, so the recipe runs the hooks). If `uv sync` in the hook needed network and had none, the hook printed the command; run it and `just check` again.

- [ ] **Step 3: Docker gates on the example (if Docker is available)**

```bash
cd examples/reference-service && just gates && just contract-gates && just o11y-gates && cd ../..
```

Expected: green, exactly as before this PR. `contract-gates` proves `openapi.json` did not move.

---

### Task 14: Pull request

- [ ] **Step 1: Push and open**

```bash
git push -u origin claude/m7-pr1-template-skeleton
gh pr create --base main --assignee EmadMokhtar \
  --title "feat: move the reference service into the template body and add the golden diff (m7 pr 1)" \
  --body "$(cat <<'EOF'
Closes #<issue from Task 1>

## What

First of the five M7 pull requests (spec §12). From this PR on, `{{cookiecutter.project_slug}}/` is the source of truth and `examples/reference-service/` is rendered from it.

- `git mv examples/reference-service '{{cookiecutter.project_slug}}'` — history follows the files.
- `cookiecutter.json` with the identity, `http_port` and `license` prompts (twelve prompts in all once PR 2 adds the backends; the SLO prompts were dropped — see the spec amendment).
- `hooks/pre_gen_project.py` validates; `hooks/post_gen_project.py` keeps the chosen licence, then — unless `PYFR_REGEN` — `git init`, `uv sync`, hooks, first commit, best effort.
- `{% raw %}` guards in the four colliding files; dashboards and the provisioning file copied verbatim.
- `scripts/regen.py`: `just regen`, `just regen-check` (the golden diff), `just adopt` (Dependabot, M7-10).
- Root `.pre-commit-config.yaml`; the template's is project-relative and its `precommit` recipe skips itself when nested.
- CI: `golden` and `precommit` jobs; `adopt.yml`; images renamed to `ghcr.io/emadmokhtar/reference-service[-migrations]`.
- ADR 0017; root docs updated; roadmap marks M7 in progress.

## After merging

- Re-run `uv run --group dev pre-commit install` in your clone: the hook path changed.
- Make the two GHCR packages under the new names public after the next release (contributing.md).

## Checked

Root `just check` and `just precommit`; the example's `just check`, `gates`, `contract-gates`, `o11y-gates`; a fresh `cookiecutter` render with non-default answers whose `just check` passes.

🤖 Generated with [Claude Code](https://claude.com/claude-code)
EOF
)"
gh pr view --json number,assignees,closingIssuesReferences --jq '{number, assignees: [.assignees[].login], closes: [.closingIssuesReferences[].number]}'
```

Expected: the assignee is `EmadMokhtar` and `closes` lists the issue.

---

## Self-review

**Spec coverage (section 12, PR 1 row).** `git mv` — Task 3. `cookiecutter.json` — Task 4. Both hooks with an empty pruning half — Task 4 (the pruning half selects the licence; nothing else). The collision pass — Task 5. `scripts/regen.py`, `just regen`, `tests/reference-answers.yaml`, `test_golden.py` — Task 6. Substitutions — Task 5. `cookiecutter` and `pytest-cookies` in the root `dev` group — Task 2. The `golden` CI job — Task 8. Roadmap "In progress" — Task 12. Added by the planning decisions: `.gitignore` (Task 4), `just adopt` and `adopt.yml` (Tasks 6, 9), root pre-commit (Task 2), ADR 0017 (Task 11), the spec amendments (Task 1). Section 13's error handling: `pre_gen` exit 1 with a sentence (Task 4, tested); `post_gen` best effort (Task 4, tested); a missing licence file exits 1 with the name (Task 4); `--check` lists and diffs (Task 6); a render failure surfaces cookiecutter's own message (unchanged `cookiecutter()` call).

**Type consistency.** `regen.compare` returns `Comparison` with `missing`, `extra`, `differing`, `clean` — used identically in Tasks 6 and 8. `regen.adopt(rendered, example, template_body, answers)` returns `list[str]` and raises `AdoptError` — Task 6's tests and the CLI agree. The hook's `LICENCE_FILES` and `regen.LICENCE_FILES` carry the same four names; `test_hooks.py`'s expected first lines match the four files in Task 4.

**Known limits, stated on purpose.** The example's two `Dockerfile` labels point at a repository that does not exist; PR 4 handles the docs equivalent. Commits pushed by `adopt.yml` start no CI run (Verified Fact 9). The template body cannot be linted; the example and the smoke render are.
