# M7 PR 3 — A generated project's own `.github/` — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A project generated from PyFr carries its own `.github/` — `ci.yml`, `nightly.yml`, `release.yml` and `dependabot.yml`, real from the first push — and its own Commitizen; the reference service's copy appears as rendered output, and the template's action pins follow the root's through `just adopt`.

**Architecture:** The four files are derived from PyFr's root workflows by removing the PyFr-only jobs (`golden`, `precommit`, the documentation jobs), removing `working-directory`, rendering the image names from the answers, and guarding GitHub's `${{ }}` expressions with `{% raw %}`. Jobs and comments that only make sense with a backend present are wrapped in that backend's `{%- if %}`. Commitizen moves into the generated `pyproject.toml` (M7-9); PyFr's root keeps its own copy. Because Dependabot's `github-actions` ecosystem reads `/.github/workflows` only, `scripts/regen.py --adopt` also copies the root workflows' `uses:` refs into the template's workflows and regenerates the example, and a root test holds the two equal.

**Tech Stack:** cookiecutter (Jinja), GitHub Actions, Commitizen 4.18.0 (`version_provider = "uv"`), Dependabot, pytest + pytest-cookies, PyYAML.

**Spec:** `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md` — sections 8 (a generated project's `.github/`), 2 (M7-9, M7-10), 7 (the Jinja collision pass), 10.1 (generation tests) and 12 (delivery). Amended by Task 1: the jobs that need the project's own documentation site (`docs`, `docs-freshness`, `docs-warnings`, `links`, `docs-examples`) and `docs.yml` move to PR 4, which adds the site, the hygiene scripts and `lychee.toml` they read. A workflow that references a file the project does not have is not "real from day one".

## Global Constraints

- The template body `{{cookiecutter.project_slug}}/` is the only source of truth. Never edit `examples/reference-service/` by hand. After every template edit run `just regen` and commit the regenerated example **in the same commit** as the template edit; `just regen-check` must be green at every commit.
- When the template's `pyproject.toml` changes, re-lock the example in the same commit: `cd examples/reference-service && uv lock` (the `uv-lock` pre-commit hook fails otherwise; `uv.lock` is outside the golden diff, M7-4).
- Jinja block tags stand on their own line, at column 0, with a left-strip dash: `{%- if cookiecutter.database == "postgres" %}`, `{%- else %}`, `{%- endif %}`, `{%- raw %}`, `{%- endraw %}`. The tag vanishes together with its line (Verified Fact 1). Inline `{% if %}…{% endif %}` is allowed only for a single token inside one line of the justfile, never in YAML or Python.
- GitHub Actions expressions (`${{ … }}`) live inside `{%- raw %}` … `{%- endraw %}` regions. A raw region never contains `{{ cookiecutter` or an `{%- if %}`; when one line would need both, split the line (move the expression into an `env:` value, or put the substitution on its own folded-scalar line).
- Every rendered file is valid in all eight backend combinations, and every comment in a rendered file is true in every combination (the M7 PR 2 rule): name no backend in a comment unless the comment sits inside that backend's `{%- if %}`.
- The template's workflows pin every action at the same ref the root's workflows pin it — Task 7's test enforces it.
- Action refs: `actions/checkout@v7`, `astral-sh/setup-uv@v7`, `extractions/setup-just@v4`, `docker/setup-qemu-action@v4`, `docker/login-action@v4`, `actions/upload-artifact@v7` — copied from the root workflows as they stand on the branch.
- Commit messages follow Conventional Commits, in simple English, and end with the attribution line the session gives. One commit per task unless a step says otherwise.
- The root's `just lint`, `just check` (docs-build, test, regen-check) and `just precommit` stay green at every commit; the example's `just check` stays green at every commit.
- Prose (README, docs) uses plain English; expand an acronym on first use in a page.

## Verified Facts

1. **Own-line raw tags.** In cookiecutter's `StrictEnvironment`, `a: 1\n{%- raw %}\nb: ${{ x }}\n{%- endraw %}\nc: 2\n` renders as `a: 1\nb: ${{ x }}\nc: 2` — each tag line disappears, the expression survives untouched. Inline `{% raw %}${{ x }}{% endraw %}` works too (verified 2026-09-13 with the root dev group's cookiecutter).
2. **Commitizen 4.18.0 before and at the first tag.** With `version_provider = "uv"` and `update_changelog_on_bump = true`: on a repository whose only commit is `chore: …` and which has no tag, `cz changelog --dry-run --incremental` prints `## Unreleased` and exits 0; `cz bump --dry-run` without `--yes` and without a terminal dies with `EOFError` at the question "Is this the first tag created?", while `cz bump --dry-run --yes` answers it and exits 21 (`NO_COMMITS_TO_BUMP`). After a hand-made tag `v0.1.0`, `cz changelog v0.1.0 --dry-run` prints `## v0.1.0 (date)` with an empty body and exits 0 — the bootstrap release's notes are an empty section, not an error. `cz bump --yes --changelog` from `v0.1.0` with one `feat:` commit bumps to `0.2.0`, **creates** `CHANGELOG.md` when it does not exist, and **requires `uv.lock` to exist** (it rewrites the project's own `[[package]]` entry). A generated project has a lock from the post-generation `uv sync`. `cz check --commit-msg-file` accepts `chore: generate the project from pyfr`, the post-generation hook's message.
3. **Dependabot reads workflows at the root only.** GitHub's Dependabot options reference: for `github-actions`, `directory` is `/`, and Dependabot searches `/.github/workflows` (plus a root `action.yml`). It cannot update `examples/reference-service/.github/workflows`. Hence Task 7: the template's pins are adopted from the root's workflows.
4. **Two gaps in today's root CI.** `adopt.yml` stages `{{cookiecutter.project_slug}}` only, and the `docs` job runs `just check` — which includes `regen-check` — with no adopt step, so a Dependabot pull request that edits `examples/reference-service/pyproject.toml` fails `docs` today (only `uv.lock`-only bumps have run since PR 1). Task 7 fixes both because the action-pin adoption needs both anyway.
5. **`rhysd/actionlint`'s pre-commit hook is not adopted.** It is `language: golang`; installing it on the maintainer's machine failed (`GOPROXY list is not the empty string, but contains no entries`). Static checks of the rendered workflows live in the generation tests instead: YAML parses, every `just` recipe a `run:` calls exists in that render's justfile, a pruned backend leaves no word behind, and every `uses:` ref equals the root's.
6. **`recipe_names()` and `dependency_names()`** in `tests/test_generation.py` already parse the rendered justfile's recipe headers and every dependency group of the rendered `pyproject.toml`; `just --list` in the invariant proves the rendered justfile parses.
7. **The rendered example's `.github/` is inert.** GitHub runs workflows from a repository's root only. The root's own workflows keep testing the example through `working-directory: examples/reference-service`, unchanged.

## File structure

Created in the template body (rendered by `just regen` into `examples/reference-service/`):

- `{{cookiecutter.project_slug}}/.github/workflows/ci.yml` — Task 3
- `{{cookiecutter.project_slug}}/.github/workflows/nightly.yml` — Task 4
- `{{cookiecutter.project_slug}}/.github/workflows/release.yml` — Task 5
- `{{cookiecutter.project_slug}}/.github/dependabot.yml` — Task 6

Modified in the template body: `pyproject.toml`, `.pre-commit-config.yaml`, `justfile`, `README.md` (Tasks 2 and 8).

Root: `scripts/regen.py` (action pins, Task 7), `tests/test_generation.py` (raw-guarded files, the workflow invariant, the Commitizen test), `tests/test_regen.py` (pin tests), `.github/workflows/ci.yml` and `.github/workflows/adopt.yml` (Task 7), the spec (Task 1), `docs/contributing.md`, `docs/roadmap.md`, `docs/adr/0014-…`, `docs/adr/0017-…`, `docs/reference/commands.md`, `docs/reference/supply-chain.md` (Tasks 2 and 8).

---

### Task 1: Amend the spec for what PR 3 lands

**Files:**
- Modify: `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md` (§8 after the table; §12 rows 3 and 4)

- [ ] **Step 1: §12 — rewrite rows 3 and 4 of the delivery table**

Replace the row that begins `| 3 — generated `.github/` |` with:

```markdown
| 3 — generated `.github/` | Section 8's `ci.yml`, `nightly.yml`, `release.yml` and `dependabot.yml`, without the jobs that need the project's own documentation site (`docs`, `docs-freshness`, `docs-warnings`, `links`, `docs-examples`) — those and `docs.yml` land with the site in PR 4, so no generated workflow ever references a file the project does not have; Commitizen moves (M7-9); the reference service's `.github/` appears as output; the template's action pins follow the root's through `just adopt` (Dependabot's `github-actions` ecosystem reads `/.github/workflows` only). | — |
```

Replace the row that begins `| 4 — docs split |` with:

```markdown
| 4 — docs split | Section 9 in full; `docs.yml` builds both sites; the hygiene scripts move; root pages rewritten; a generated project's `docs.yml` and the documentation jobs of its `ci.yml` and `nightly.yml`. | — |
```

- [ ] **Step 2: §8 — add one paragraph after the table (before "Commitizen becomes a `dev` dependency")**

```markdown
Amended during PR 3: the table describes the end state. The
documentation-dependent jobs and `docs.yml` arrive with PR 4, together
with the site, the hygiene scripts and `lychee.toml` they read (section
12). Dependabot's `github-actions` ecosystem reads `/.github/workflows`
only, so the pins in the template's workflows are adopted from PyFr's
root workflows by `just adopt` — M7-10's mechanism, in the other
direction — and a root test holds the two equal.
```

- [ ] **Step 3: Check the site still builds and commit**

Run: `just docs-build`
Expected: exit 0.

```bash
git add docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md
git commit -m "docs(spec): land the documentation-dependent workflow jobs of m7 pr 3 with pr 4"
```

---

### Task 2: Commitizen moves into the template (M7-9)

**Files:**
- Modify: `{{cookiecutter.project_slug}}/pyproject.toml` (the `dev` group; a new `[tool.commitizen]` table)
- Modify: `{{cookiecutter.project_slug}}/.pre-commit-config.yaml`
- Modify: `{{cookiecutter.project_slug}}/justfile` (two recipes after `promote-latest`)
- Modify: `{{cookiecutter.project_slug}}/README.md:26` and the command table (rows after `just promote-latest`)
- Modify: `tests/test_generation.py` (new test)
- Modify: `docs/contributing.md` ("Conventional Commits are required"), `docs/adr/0014-dependabot-and-one-pin-per-tool.md` (Consequences), `docs/reference/supply-chain.md` (~line 245), `docs/reference/commands.md` (the reference service's table)
- Regenerated: `examples/reference-service/**`, `examples/reference-service/uv.lock`

**Interfaces:**
- Produces: `just changelog`, `just next-version` recipes in every render; a `commitizen` hook at the `commit-msg` stage; `[tool.commitizen]` with `version_provider = "uv"` and `tag_format = "v$version"` — Task 5's `release.yml` runs `uv run --locked cz bump --yes --changelog` against this table.

- [ ] **Step 1: Write the failing test**

Append to `tests/test_generation.py`, after `test_dashboards_are_copied_verbatim`:

```python
def test_a_render_owns_its_commitizen(cookies) -> None:
    # M7-9: a generated project has its own version, tags and release
    # workflow, so the tool that decides its version is in its own lock.
    root = render(cookies)
    table = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["commitizen"]
    assert table["version_provider"] == "uv"
    assert table["tag_format"] == "v$version"
    assert table["update_changelog_on_bump"] is True
    assert table["major_version_zero"] is True
    assert "commitizen" in dependency_names(root)
    hooks = yaml.safe_load((root / ".pre-commit-config.yaml").read_text())
    assert "commit-msg" in hooks["default_install_hook_types"]
    local = next(repo for repo in hooks["repos"] if repo["repo"] == "local")
    commitizen = next(hook for hook in local["hooks"] if hook["id"] == "commitizen")
    assert commitizen["stages"] == ["commit-msg"]
    assert commitizen["entry"] == "uv run --locked cz check --allow-abort --commit-msg-file"
    assert {"changelog", "next-version"} <= recipe_names(root)
```

- [ ] **Step 2: Run it to see it fail**

Run: `uv run --group dev pytest tests/test_generation.py -q -k owns_its_commitizen`
Expected: FAIL with `KeyError: 'commitizen'`.

- [ ] **Step 3: `pyproject.toml` — the dependency and the table**

In the `dev` group, directly after `"pre-commit>=4.0",`, add:

```toml
    # Decides this project's version and writes its changelog at a release
    # (.github/workflows/release.yml), and checks every commit message
    # (.pre-commit-config.yaml). Pinned exactly, and pinned HERE only: the
    # version that numbers each release must be one version, in one file
    # Dependabot updates. Every caller runs it through `uv run --locked cz`.
    "commitizen==4.18.0",
```

After the `[tool.hatch.build.targets.wheel]` table and before `[tool.pytest.ini_options]`, add:

```toml
[tool.commitizen]
# The release workflow runs `cz bump` with this table: it reads the
# Conventional Commits since the last tag, decides the bump, writes
# CHANGELOG.md and tags. `just changelog` and `just next-version` preview
# both without changing anything.
name = "cz_conventional_commits"
# Writes BOTH [project].version above and the matching [[package]] entry in
# uv.lock. `pep621` writes only the first, which leaves the lock file stale
# and fails the uv-lock hook -- inside the release workflow, after the tag
# has already been pushed.
version_provider = "uv"
tag_format = "v$version"
update_changelog_on_bump = true
changelog_file = "CHANGELOG.md"
# Pre-1.0: a breaking change bumps the MINOR number (0.1.0 -> 0.2.0)
# rather than jumping to 1.0.0. Semver puts no compatibility promise on
# the major number below 1.0.0, and 1.0.0 should be a deliberate decision
# about stability, not a side effect of the first `feat!:`.
major_version_zero = true
```

- [ ] **Step 4: `.pre-commit-config.yaml` — the hook type and the hook**

Replace the two-line header comment and the first key with:

```yaml
# pre-commit only installs the git hook types it is told to. Without this,
# `pre-commit install` wires up the `pre-commit` stage only -- the commitizen
# hook below runs at the `commit-msg` stage and would never fire.
default_install_hook_types: [pre-commit, commit-msg]
```

Directly after the `uv-lock` hook (after its `files:` line), inside the `repo: local` block, add:

```yaml
      # Every commit message must be a Conventional Commit: the release
      # workflow derives the version and the changelog from them. Commitizen
      # comes from uv.lock, the one place its version lives.
      - id: commitizen
        name: commitizen check
        entry: uv run --locked cz check --allow-abort --commit-msg-file
        language: system
        stages: [commit-msg]
```

- [ ] **Step 5: `justfile` — two recipes**

Directly after the `promote-latest` recipe (after its `{%- endif %}` line) add:

```just

# Preview the changelog entry the next release will write. Read-only.
changelog:
    uv run --locked cz changelog --dry-run --incremental

# Preview the version the next release will choose, without doing it.
next-version:
    # The release itself runs in CI (.github/workflows/release.yml); this is
    # for answering "what will merging this produce?" before merging.
    # `--yes` answers Commitizen's "Is this the first tag created?" -- asked
    # only before the first release, when no tag exists yet -- which would
    # otherwise stop the dry run outside a terminal.
    uv run --locked cz bump --dry-run --yes
```

- [ ] **Step 6: `README.md`**

Line 26: `uv run pre-commit install  # one-time: wires up the lint hooks` → `uv run pre-commit install  # one-time: wires up the lint and commit-msg hooks`.

In the command table, directly after the `just promote-latest VERSION` row, add:

```markdown
| `just changelog` | Preview the changelog entry the next release would write from the Conventional Commits since the last tag — read-only |
| `just next-version` | Preview the version the next release would choose — read-only; the release itself runs in CI (`.github/workflows/release.yml`) |
```

- [ ] **Step 7: Regenerate, re-lock, and run the test**

```bash
just regen
(cd examples/reference-service && uv lock && uv sync)
git status --short
```

Expected: the four template files, their four rendered copies and `examples/reference-service/uv.lock` are modified — nothing else.

Run: `uv run --group dev pytest tests/test_generation.py -q -k "owns_its_commitizen or carries_only"`
Expected: PASS (the invariant's `just --list` proves the two recipes parse in every combination).

Run: `(cd examples/reference-service && just next-version)`
Expected: prints a version line from PyFr's own tags (the example is nested in this repository, so Commitizen reads PyFr's history) — the point is only that `cz` resolves from the example's lock and exits without a traceback; exit 21 (`NO_COMMITS_TO_BUMP`) is fine.

Run: `(cd examples/reference-service && just check)`
Expected: exit 0.

- [ ] **Step 8: Docs**

`docs/contributing.md`, in "Conventional Commits are required", after the paragraph that ends `see [ADR 0014](adr/0014-dependabot-and-one-pin-per-tool.md).`, add:

```markdown
A generated project carries its own Commitizen (spec M7-9): `commitizen`
in its `dev` group, a `[tool.commitizen]` table in its `pyproject.toml`,
the same commit-message hook, and `just changelog` / `just next-version`.
Its version, tags and releases are its own; the root's copy decides PyFr's
releases only. In this repository the example's copy is rendered output,
and the root's hook is the one that checks your messages.
```

`docs/adr/0014-dependabot-and-one-pin-per-tool.md`, under `## Consequences`, add one bullet at the end:

```markdown
- A generated project (M7) pins its own Commitizen in its own
  `pyproject.toml`, exactly as this root does, and its own Dependabot keeps
  that pin current: one pin per tool holds per repository, not across the
  template and what it generates.
```

`docs/reference/supply-chain.md`, after the sentence ending `read their image names from there.` (~line 249), add:

```markdown
A generated project repeats the arrangement inside its own tree: its
`pyproject.toml` pins Commitizen, and its `justfile`, `release.yml` and
commit-message hook all call `uv run --locked cz`.
```

`docs/reference/commands.md`, in the reference service's command table (the one with `just promote-latest`), after that row add:

```markdown
| `just changelog` | Preview the changelog entry the next release would write from the Conventional Commits since the last tag. Read-only. |
| `just next-version` | Preview the version the next release would choose. Read-only — the release itself runs in the project's `release.yml`. |
```

Bump `last_reviewed` in the front matter of every page you edited to `2026-09-13`.

- [ ] **Step 9: Verify everything and commit**

```bash
just regen-check && just lint && just docs-build && uv run --group dev pytest tests -q && just precommit
```

Expected: all exit 0.

```bash
git add '{{cookiecutter.project_slug}}' examples/reference-service tests/test_generation.py docs
git commit -m "feat(template): give a generated project its own commitizen"
```

---

### Task 3: The generated `ci.yml`, and the workflow invariant

**Files:**
- Create: `{{cookiecutter.project_slug}}/.github/workflows/ci.yml`
- Modify: `tests/test_generation.py` (`RAW_GUARDED_FILES`; new helpers `workflow_files`, `run_scripts`, `assert_workflows_are_coherent`; call from `assert_invariant`)
- Regenerated: `examples/reference-service/.github/workflows/ci.yml`

**Interfaces:**
- Produces: `assert_workflows_are_coherent(root: Path, answers: dict[str, str]) -> None`, called by `assert_invariant`; `WORKFLOW_BACKEND_WORDS`; Tasks 4–6 add files that this helper covers with no further test code.

- [ ] **Step 1: Extend the tests first**

In `tests/test_generation.py`, replace the `RAW_GUARDED_FILES` block (the comment and the frozenset) with:

```python
# Files where a literal {{ }} / {% %} is someone else's syntax, not ours,
# and is guarded with {% raw %} so Jinja leaves it alone: golang-migrate's
# CLI placeholders and the buildx/trivy recipes' own {{name}} interpolation
# (justfile), Prometheus's alert-label templating (slo.yml), sqlfluff's
# comment naming its own template markers (.sqlfluff), a raw PromQL query
# string (test_observability_stack.py), and GitHub Actions' `${{ }}`
# expressions (the three workflows). None of these are cookiecutter
# collisions. They are still checked for ALWAYS_FORBIDDEN_MARKERS above --
# only their own raw-guarded braces are excused, not real Jinja mistakes.
RAW_GUARDED_FILES = frozenset(
    {
        "justfile",
        "ops/prometheus/rules/slo.yml",
        ".sqlfluff",
        "tests/integration/test_observability_stack.py",
        ".github/workflows/ci.yml",
        ".github/workflows/nightly.yml",
        ".github/workflows/release.yml",
    }
)
```

After `assert_compose_is_self_consistent` and before `assert_invariant`, add:

```python
# A word that must not survive in .github/ when its backend is off. Matched
# case-insensitively over the whole file, comments included: a comment that
# names a container the render does not have is the M7 PR 2 rule broken.
# "schema" is not here because "schemathesis" carries it in every render.
WORKFLOW_BACKEND_WORDS = {
    "database": ("postgres", "migrat"),
    "cache": ("redis",),
    "object_storage": ("minio", "s3"),
}
JUST_CALL = re.compile(r"\bjust\s+([a-z][a-z0-9-]*)")
DEPENDABOT_ECOSYSTEMS = ["uv", "github-actions", "docker", "docker-compose", "pre-commit"]


def workflow_files(root: Path) -> list[Path]:
    return sorted((root / ".github").rglob("*.yml"))


def run_scripts(document: dict) -> Iterator[str]:
    """Every `run:` value in a parsed workflow, shell comment lines removed."""
    for job in document.get("jobs", {}).values():
        for step in job.get("steps", []):
            script = step.get("run")
            if script:
                yield "\n".join(
                    line
                    for line in script.splitlines()
                    if not line.lstrip().startswith("#")
                )


def assert_workflows_are_coherent(root: Path, answers: dict[str, str]) -> None:
    # The rendered workflows never run in this repository (GitHub runs
    # workflows from a repository's root only), so this is their only
    # gate before a generated project pushes them: the YAML parses, a
    # pruned backend leaves no word behind, every `just` recipe a step
    # calls exists in this render's justfile, and Dependabot's schedule
    # names the five ecosystems.
    present = {p.relative_to(root).as_posix() for p in workflow_files(root)}
    assert present >= {
        ".github/workflows/ci.yml",
        ".github/workflows/nightly.yml",
        ".github/workflows/release.yml",
        ".github/dependabot.yml",
    }, present
    recipes = recipe_names(root)
    for path in workflow_files(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_text()
        document = yaml.safe_load(text)
        assert isinstance(document, dict), relative
        for key, words in WORKFLOW_BACKEND_WORDS.items():
            if answers[key] == "none":
                for word in words:
                    assert word not in text.lower(), (relative, word)
        if relative == ".github/dependabot.yml":
            updates = document["updates"]
            assert [u["package-ecosystem"] for u in updates] == DEPENDABOT_ECOSYSTEMS
            assert all(u["directory"] == "/" for u in updates), relative
            continue
        for script in run_scripts(document):
            for recipe in JUST_CALL.findall(script):
                assert recipe in recipes, (relative, recipe)
```

In `assert_invariant`, directly after the line `assert_compose_is_self_consistent(root, answers)`, add:

```python
    assert_workflows_are_coherent(root, answers)
```

- [ ] **Step 2: Run the matrix to see it fail**

Run: `uv run --group dev pytest tests/test_generation.py -q -k carries_only`
Expected: 8 FAIL on the presence assertion (`present` is empty: the template has no `.github/` yet). Tasks 4–6 turn it green one file at a time; until Task 6 the matrix stays red on that one assertion, which is acceptable inside one pull request — do not weaken it.

- [ ] **Step 3: Write the workflow**

Create `{{cookiecutter.project_slug}}/.github/workflows/ci.yml` with exactly this content:

```yaml
name: CI

on:
  push:
    branches: [main]
  pull_request:

# One run per branch. Cancelling in-flight runs is safe here in a way it
# is not for release.yml: nothing is published, so a cancelled run leaves
# nothing half-done.
concurrency:
{%- raw %}
  group: ci-${{ github.ref }}
{%- endraw %}
  cancel-in-progress: true

jobs:
  check:
    # `just check` is lint, typecheck, imports, unit tests and pre-commit,
    # then `git diff --exit-code` to catch a hook that mutated the tree.
    # One job rather than five: they share an install, they all finish in
    # a couple of minutes, and splitting them would mean five copies of
    # the setup for a failure message that already names which gate broke.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      - name: Install uv
        uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true

      - name: Install just
        uses: extractions/setup-just@v4

      - name: Install the project
        run: uv sync

      - name: Run every fast gate
        run: just check

  integration:
    # testcontainers starts every container the integration tests need,
    # from the pins in the test code and compose.yaml. Deliberately NOT a
    # `services:` block: the versions CI runs against are the versions a
    # developer runs against, and there is one place to change them.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: extractions/setup-just@v4
      - run: uv sync
      - run: just test-integration

  gates:
{%- if cookiecutter.database == "postgres" %}
    # Migration files, the schema snapshot, model/schema drift, and the
    # generated configuration reference. Needs Docker for the schema
    # gates, which run against a real PostgreSQL.
{%- else %}
    # The generated configuration reference: `.env.example` and the
    # configuration page must still match settings.py.
{%- endif %}
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: extractions/setup-just@v4
      - run: uv sync
      - run: just gates

  contract:
    # `just contract-gates`: schemathesis conformance against the committed
    # contract, plus the oasdiff breaking-change check cross-referenced
    # against the commit's own `!` marker. OpenAPI drift -- whether the
    # committed openapi.json still matches the code -- is NOT one of them:
    # that gate (tests/unit/test_contract_drift.py) carries no contract
    # marker, so it runs in the default `just test` tier instead, covered
    # by the `check` job above. `fetch-depth: 0` because the commit-marker
    # half reads the commit range -- with a shallow clone `git log
    # base..head` is empty, which reads as "nobody marked it breaking" and
    # fails every legitimate breaking change.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: extractions/setup-just@v4
      - run: uv sync
      - run: just contract-gates

  o11y-gates:
    # promtool over the SLO rules, out of the pinned otel-lgtm image. No
    # uv sync: it runs no Python at all.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: extractions/setup-just@v4
      - run: just o11y-gates

  build:
    # Every image for linux/amd64 AND linux/arm64, with no output: proves
    # each Dockerfile still builds for both, which is what "Apple Silicon
    # laptops and cloud servers share one image" rests on. QEMU supplies
    # the emulated architecture; the `pyfr` builder is created by the
    # recipe itself (`_buildx-builder`) and is never made the current
    # builder, so plain `docker build` elsewhere in the same job still
    # loads into the daemon. No `docker/setup-buildx-action`: it makes its
    # own `docker-container` builder the CURRENT one, and on Docker >= 23
    # `docker build` then runs on that builder and `--load`s nothing (the
    # default `docker` driver cannot target two platforms at once).
    # `docker buildx` itself is preinstalled on ubuntu-latest. Pushing is
    # release.yml's job.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: docker/setup-qemu-action@v4
      - uses: extractions/setup-just@v4
      - name: Build every image for both architectures
        run: just build-multiarch

  security:
    # pip-audit over the lock, Trivy over the images, and a software bill
    # of materials per image. `build-images` first because `scan` and
    # `sbom` read the locally built single-architecture images over the
    # Docker socket. One step per recipe, so a red job names which one.
    # No `uv sync`: `just audit` reads the lock with `uv export` and runs
    # pip-audit through `uvx`.
    #
    # This job's result can change with no commit -- an advisory is
    # published against a version already locked -- which is also why
    # nightly.yml runs the same recipes every night.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: extractions/setup-just@v4
      - name: Build the images
        run: just build-images
      - name: Audit the lock
        run: just audit
      - name: Scan the images
        run: just scan
      - name: Write the software bills of materials
        run: just sbom
      - uses: actions/upload-artifact@v7
        with:
          name: sbom
          path: sbom/*.cdx.json
          if-no-files-found: error
```

- [ ] **Step 4: Regenerate and check the render**

```bash
just regen
git status --short
```

Expected: `examples/reference-service/.github/workflows/ci.yml` is new; nothing else changed.

Run: `uv run --group dev pytest tests/test_generation.py -q -k "no_template_syntax"`
Expected: 8 PASS (the `${{` survives only inside a raw-guarded file; no `{% raw` reaches the render).

Run: `diff <(sed -n '/^jobs:/,$p' .github/workflows/ci.yml) <(sed -n '/^jobs:/,$p' examples/reference-service/.github/workflows/ci.yml) | head -80`
Expected: the differences are the removed jobs (`golden`, `precommit`, `docs`, `docs-freshness`, `docs-warnings`, `links`, `docs-examples`), the removed `defaults: run: working-directory:` blocks, the removed documentation-toolchain audit step, the neutral comments and the `sbom/*.cdx.json` path — nothing else.

- [ ] **Step 5: Prove the invariant bites, then commit**

Temporarily change the `gates` job's `{%- else %}` comment to mention `PostgreSQL`; run `uv run --group dev pytest tests/test_generation.py -q -k carries_only`; every `none-*` case must fail naming `.github/workflows/ci.yml` and `postgres` (in addition to the missing-files assertion, which stays red until Task 6). Revert. Temporarily change `run: just gates` to `run: just gatez`; the matrix must fail naming `gatez`. Revert and `just regen` (confirm `git status --short` shows only the intended new files).

```bash
git add '{{cookiecutter.project_slug}}/.github' examples/reference-service/.github tests/test_generation.py
git commit -m "feat(template): give a generated project its own ci workflow"
```

---

### Task 4: The generated `nightly.yml`

**Files:**
- Create: `{{cookiecutter.project_slug}}/.github/workflows/nightly.yml`
- Regenerated: `examples/reference-service/.github/workflows/nightly.yml`

- [ ] **Step 1: Write the workflow**

Create `{{cookiecutter.project_slug}}/.github/workflows/nightly.yml` with exactly this content:

```yaml
name: Nightly

# Slow work that must not sit in the pull request path: mutation testing
# takes far longer than a reviewer will wait, and an advisory published
# against an image already shipped changes no file here, so nothing in
# the pull request path would ever re-check it.

on:
  schedule:
    # 03:17 UTC. Deliberately not on the hour: every scheduled job on
    # GitHub is queued at :00, and a job that starts when the queue is
    # empty starts sooner.
    - cron: "17 3 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  mutation:
    # Measures whether a test would NOTICE a change in behaviour, which is
    # the question coverage cannot answer. Read the survivors, not the
    # percentage -- the recipe enforces a floor so a regression is caught,
    # but the value is in which mutants lived.
    runs-on: ubuntu-latest
    timeout-minutes: 60
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: extractions/setup-just@v4
      - run: uv sync
      - run: just mutants-gate

  security:
    # The same audit ci.yml runs on every pull request, plus a scan of the
    # images LAST PUBLISHED rather than freshly built: a CVE is published
    # against a version already shipped, and nothing else here would
    # re-check the image anyone is actually running. Fails on the night a
    # new advisory lands, which is the point.
    #
    # `packages: read` and the two TRIVY_* variables are what let Trivy
    # pull a package that has not been made public yet; once it is public
    # they are harmless. Before the first release there is no `latest`
    # tag and the scan step fails on "not found" -- expected, until the
    # first release publishes one.
    runs-on: ubuntu-latest
    permissions:
      contents: read
      packages: read
{%- raw %}
    env:
      TRIVY_USERNAME: ${{ github.actor }}
      TRIVY_PASSWORD: ${{ secrets.GITHUB_TOKEN }}
{%- endraw %}
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          enable-cache: true
      - uses: extractions/setup-just@v4
      - name: Audit the lock
        run: just audit
      - name: Scan what was last published
        run: >-
          just scan
          ghcr.io/{{ cookiecutter.github_org | lower }}/{{ cookiecutter.project_slug }}:latest
{%- if cookiecutter.database == "postgres" %}
          ghcr.io/{{ cookiecutter.github_org | lower }}/{{ cookiecutter.project_slug }}-migrations:latest
{%- endif %}
```

- [ ] **Step 2: Regenerate and check**

```bash
just regen && git status --short
```

Expected: only `examples/reference-service/.github/workflows/nightly.yml` is new.

Run: `python3 -c "import yaml; d = yaml.safe_load(open('examples/reference-service/.github/workflows/nightly.yml')); print(d['jobs']['security']['steps'][-1]['run'])"`
Expected: `just scan ghcr.io/emadmokhtar/reference-service:latest ghcr.io/emadmokhtar/reference-service-migrations:latest` on one line (the folded scalar joined the lines).

Render `database=none` once and read the same step: `uv run --group dev python -c "..."` is fine, or simply run the matrix: `uv run --group dev pytest tests/test_generation.py -q -k carries_only` — the `none-*` cases must no longer name `nightly.yml` (they still fail on the missing `release.yml` and `dependabot.yml`).

- [ ] **Step 3: Commit**

```bash
git add '{{cookiecutter.project_slug}}/.github/workflows/nightly.yml' examples/reference-service/.github/workflows/nightly.yml
git commit -m "feat(template): give a generated project its own nightly workflow"
```

---

### Task 5: The generated `release.yml`

**Files:**
- Create: `{{cookiecutter.project_slug}}/.github/workflows/release.yml` — a copy of `.github/workflows/release.yml` with the edits below
- Regenerated: `examples/reference-service/.github/workflows/release.yml`

The root's file is 376 lines and its comments are the record of every verified behaviour; copy it and edit, so the reviewer's `diff .github/workflows/release.yml examples/reference-service/.github/workflows/release.yml` shows exactly the edits below and nothing else.

- [ ] **Step 1: Copy**

```bash
cp .github/workflows/release.yml '{{cookiecutter.project_slug}}/.github/workflows/release.yml'
```

- [ ] **Step 2: Edit the header comment**

Replace the first paragraph

```yaml
# Releases the REPOSITORY, not the reference service. One version, one
# CHANGELOG.md, one tag series -- see the M5 plan's Global Constraints.
# The reference service is an example nobody deploys; it stays at 0.1.0
# and publishes nothing. Image publishing arrives in M6.
```

with

```yaml
# Releases this service: one version, one CHANGELOG.md, one tag series,
# and the container images published under that version (README,
# "Supply chain").
```

and the last four lines of the second paragraph

```yaml
# The bootstrap mode exists only because this repository starts with zero
# tags. Once the first release has run, every later run takes the `bump`
# path, and the bootstrap branch is dead code that stays dead -- see that
# step's comment for the empirical reasons it cannot be deleted anyway.
```

with

```yaml
# The bootstrap mode exists because a project generated from PyFr starts
# at 0.1.0 with zero tags. Once the first release has run, every later run
# takes the `bump` path -- see that step's comment for the empirical
# reasons Commitizen cannot cut the first release itself.
```

- [ ] **Step 3: Guard the expressions**

Wrap each of these regions in own-line `{%- raw %}` / `{%- endraw %}` (column 0, the tag on its own line directly before the first and directly after the last line of the region):

1. The `outputs:` block of the `release` job (two lines, `released:` and `version:`).
2. In the "Push the release" step: from `env:` through the end of its `run: |` script (the script reads `${{ steps.bump.outputs.mode }}` and `${{ steps.bump.outputs.version }}`).
3. In the "Publish the GitHub Release" step: the `env:` block (`GH_TOKEN`, `RELEASED`, `VERSION`).
4. In the `publish-images` job: from `env:` through `TRIVY_PASSWORD:` (the comment lines inside the block are fine inside raw), then the first two steps (`- uses: actions/checkout@v7` with its `ref:` … through the `docker/login-action@v4` step's `password:` line).

After each wrap, confirm the region contains no `{{ cookiecutter` and no `{%- if`.

- [ ] **Step 4: Edit the `release` job**

1. "Install just" step comment: `# For `just regen` in the bump step. This puts a binary on the` → `# For `just contract-release` in the bump step. This puts a binary on the`.
2. Bump step comment, first paragraph — replace

```yaml
        # Commitizen comes from the root uv.lock -- the one place its
        # version lives (ADR 0014) -- so the tool deciding the version
        # here is the tool the commit-msg hook ran on every message it
        # reads.
```

   with

```yaml
        # Commitizen comes from uv.lock -- the one place its version
        # lives -- so the tool deciding the version here is the tool the
        # commit-msg hook ran on every message it reads.
```

3. Same comment, second paragraph — replace

```yaml
        # updating it, and `.venv/` is untracked and ignored (M6 plan,
        # Verified Fact 12). The one deliberate write is the
        # contract-baseline promotion inside the else branch below -- the
        # template body's baseline, and the example `just regen` renders
        # from it -- which relies on exactly this behaviour to ride along
        # in the bump commit.
```

   with

```yaml
        # updating it, and `.venv/` is untracked and ignored (M6 plan,
        # Verified Fact 12). The one deliberate write is the
        # contract-baseline promotion inside the else branch below, which
        # relies on exactly this behaviour to ride along in the bump
        # commit.
```
4. Same comment: `# This repository starts with no git tags at all, and `cz bump`` → `# A generated project starts with no git tags at all, and `cz bump``; and `because this repository's `update_changelog_on_bump = true`` → `because `update_changelog_on_bump = true` in pyproject.toml`.
5. Same comment, last paragraph: replace from `# So: branch on whether any tag exists.` to the end of the comment with:

```yaml
        # So: branch on whether any tag exists. With none, skip `cz bump`
        # entirely and hand-tag the current commit with the version
        # already on disk -- 0.1.0 as generated -- so there is nothing to
        # bump; the GitHub Release below gets an empty notes section for
        # it, and the first `cz bump` after it creates CHANGELOG.md. With
        # a tag already in place, run `cz bump` exactly as normal; it is
        # fully reliable once it has a base to work from.
```

6. In the script, every `uv run --locked --group dev cz` → `uv run --locked cz` (four occurrences in the file: `cz version --project` twice, `cz bump`, `cz changelog` in the publish step). The generated project's `dev` group is a default group, so `uv run` installs it without `--group`.
7. The promotion: replace the end of the first comment paragraph

```yaml
            # request after a release and stays red until someone
            # promotes by hand. Steady-state only: the bootstrap branch
            # above makes no commit, so its baseline was promoted on the
            # branch that introduced this workflow instead.
```

   with

```yaml
            # request after a release and stays red until someone
            # promotes by hand. Steady-state only: the bootstrap branch
            # above makes no commit, and a freshly generated baseline
            # already equals openapi.json.
```

   delete the whole second paragraph (from `# In PyFr's own repository the baseline lives in the template` through `# the untracked `.venv/`.` and the blank `#` line before `# If cz then decides`); replace the two commands

```yaml
            cp '{{cookiecutter.project_slug}}/openapi.json' '{{cookiecutter.project_slug}}/openapi.baseline.json'
            just regen
```

with

```yaml
            just contract-release
```

8. "Push the release" step: replace the paragraph from `# The push uses RELEASE_TOKEN, not the workflow token.` through `# workflow runs again and stops at the `bump:` guard above.` with:

```yaml
        # The push uses RELEASE_TOKEN when that secret exists and the
        # workflow token otherwise. The workflow token is enough on a
        # repository whose `main` accepts a direct push from Actions. A
        # ruleset that requires a pull request on `main` refuses that push
        # (GH013) -- and on a user-owned repository GitHub does not let
        # the Actions app be exempted -- so add a fine-grained personal
        # access token of an exempt admin (this repository only; Contents:
        # read and write) as the `RELEASE_TOKEN` secret (README,
        # "Continuous integration and releases"). It reaches only this
        # step, through its environment. A push made with RELEASE_TOKEN,
        # unlike one made with GITHUB_TOKEN, DOES start other workflows:
        # ci.yml runs again on the bump commit (harmless), and this
        # workflow runs again and stops at the `bump:` guard above.
```

- [ ] **Step 5: Edit the `publish-images` job**

1. Comment: `# Both images, both architectures, tagged with the REPOSITORY version` → `# Every image, both architectures, tagged with the version`; `# `just` / `# build-images` would build inside that container builder and never` / `# load `reference-service:ci` into the daemon` → `{{ cookiecutter.project_slug }}:ci` in place of `reference-service:ci`.
2. Delete the `defaults:` / `run:` / `working-directory: examples/reference-service` lines.
3. Step names: `Build both images` → `Build the images`; `Scan both images` → `Scan the images`; `Push both images for both architectures under the version tag` → `Push the images for both architectures under the version tag`.
4. The SBOM step's `run:` becomes:

```yaml
        run: >-
          just sbom
          "ghcr.io/{{ cookiecutter.github_org | lower }}/{{ cookiecutter.project_slug }}:$VERSION"
{%- if cookiecutter.database == "postgres" %}
          "ghcr.io/{{ cookiecutter.github_org | lower }}/{{ cookiecutter.project_slug }}-migrations:$VERSION"
{%- endif %}
```

5. The "Attach the SBOMs to the release" step's `run:` becomes:

```yaml
        run: >-
          gh release upload --clobber "$VERSION"
          sbom/{{ cookiecutter.project_slug }}.cdx.json
{%- if cookiecutter.database == "postgres" %}
          sbom/{{ cookiecutter.project_slug }}-migrations.cdx.json
{%- endif %}
```

- [ ] **Step 6: Regenerate, diff, test**

```bash
just regen && git status --short
diff .github/workflows/release.yml examples/reference-service/.github/workflows/release.yml
```

Expected: the diff shows only Steps 2, 4 and 5 (the raw tags leave no trace in the render). Read it once from top to bottom; anything else is a slip.

Run: `uv run --group dev pytest tests/test_generation.py -q -k "no_template_syntax or carries_only"`
Expected: `no_template_syntax` 8 PASS; `carries_only` still fails only on the missing `dependabot.yml`.

Render `database=none` and confirm the two folded scalars collapsed to one image each:

```bash
uv run --group dev python - <<'EOF'
import os, tempfile, yaml
from pathlib import Path
from cookiecutter.main import cookiecutter
os.environ["PYFR_REGEN"] = "1"
out = Path(tempfile.mkdtemp())
cookiecutter(".", no_input=True, output_dir=str(out), extra_context={"database": "none"}, default_config=True)
doc = yaml.safe_load((out / "my-service/.github/workflows/release.yml").read_text())
steps = {s.get("name"): s for s in doc["jobs"]["publish-images"]["steps"]}
print(steps["Write the software bills of materials from the pushed images"]["run"])
print(steps["Attach the SBOMs to the release"]["run"])
EOF
```

Expected: `just sbom "ghcr.io/your-org/my-service:$VERSION"` and `gh release upload --clobber "$VERSION" sbom/my-service.cdx.json`.

- [ ] **Step 7: Rehearse the bump script's two paths in a real render**

Render the everything-on template live (hook on, network on) into a scratch directory, then walk the two branches of the bump step by hand — the workflow itself never runs here (Verified Fact 7):

```bash
scratch=$(mktemp -d)
uv run --group dev cookiecutter . --no-input --output-dir "$scratch" --default-config
cd "$scratch/my-service"
git log --oneline            # one commit: chore: generate the project from pyfr
git tag -l                   # empty: the bootstrap branch would run
uv run --locked cz version --project   # 0.1.0 -- what the bootstrap tags
git tag v0.1.0
uv run --locked cz changelog v0.1.0 --dry-run   # "## v0.1.0 (date)", exit 0
git commit -q --allow-empty -m "feat: a change"
just contract-release && uv run --locked cz bump --yes --changelog
git log --oneline -3 && git tag -l && head -5 CHANGELOG.md && grep '^version' pyproject.toml
cd - && rm -rf "$scratch"
```

Expected: the bump commit `bump: version 0.1.0 → 0.2.0`, tag `v0.2.0`, a new `CHANGELOG.md` whose first heading is `## v0.2.0`, `version = "0.2.0"`; and the generation commit itself passed the commit-msg hook the post-generation `pre-commit install` wired (it exists, so it did). Record the output in your report.

- [ ] **Step 8: Commit**

```bash
git add '{{cookiecutter.project_slug}}/.github/workflows/release.yml' examples/reference-service/.github/workflows/release.yml
git commit -m "feat(template): give a generated project its own release workflow"
```

---

### Task 6: The generated `dependabot.yml`

**Files:**
- Create: `{{cookiecutter.project_slug}}/.github/dependabot.yml`
- Regenerated: `examples/reference-service/.github/dependabot.yml`

- [ ] **Step 1: Write the file**

Create `{{cookiecutter.project_slug}}/.github/dependabot.yml` with exactly this content:

```yaml
# Automated dependency updates. Weekly, one grouped pull request per
# ecosystem, so a Monday brings at most five pull requests rather than
# thirty.
#
# What is NOT here, and why: any way to update a version literal inside
# the justfile -- Dependabot has none, which is why every tool version
# lives in uv.lock, compose.yaml or a Dockerfile instead (the one
# exception, pip-audit's pin in the `audit` recipe, is commented there).
version: 2

updates:
  # uv.lock and the pins in pyproject.toml.
  - package-ecosystem: "uv"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      python:
        patterns: ["*"]
    commit-message:
      prefix: "build(deps)"
    labels: ["dependencies"]

  - package-ecosystem: "github-actions"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      actions:
        patterns: ["*"]
    commit-message:
      prefix: "ci(deps)"
    labels: ["dependencies"]

{%- if cookiecutter.database == "postgres" %}
  # Dockerfile and Dockerfile.migrations: the file fetcher matches any
  # name containing "dockerfile".
{%- else %}
  # The Dockerfile.
{%- endif %}
  - package-ecosystem: "docker"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      images:
        patterns: ["*"]
    commit-message:
      prefix: "build(deps)"
    labels: ["dependencies"]

  # compose.yaml. The integration tests and `just o11y-gates` read their
  # pins from this file, so a bump here IS the bump everywhere.
  - package-ecosystem: "docker-compose"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      compose-images:
        patterns: ["*"]
    ignore:
      # `image: {{ cookiecutter.project_slug }}:compose` is built locally by
      # `app`; there is nothing on Docker Hub to update it from.
      - dependency-name: "{{ cookiecutter.project_slug }}"
    commit-message:
      prefix: "build(deps)"
    labels: ["dependencies"]

  # The hooks that carry a `rev:`. ruff, uv and Commitizen are local hooks
  # resolved through uv.lock and need none.
  - package-ecosystem: "pre-commit"
    directory: "/"
    schedule:
      interval: "weekly"
    groups:
      hooks:
        patterns: ["*"]
    commit-message:
      prefix: "build(deps)"
    labels: ["dependencies"]
```

- [ ] **Step 2: Regenerate and run the whole matrix**

```bash
just regen && git status --short
uv run --group dev pytest tests/test_generation.py -q
```

Expected: only `examples/reference-service/.github/dependabot.yml` is new; every test passes, including all eight `carries_only` cases — this is the task that turns Task 3's file-presence assertion green.

Confirm the `compose.yaml` of the reference render names `image: reference-service:compose` for `app` (so the `ignore` entry names a real image): `grep -n "image: reference-service" examples/reference-service/compose.yaml`.

- [ ] **Step 3: Commit**

```bash
git add '{{cookiecutter.project_slug}}/.github/dependabot.yml' examples/reference-service/.github/dependabot.yml
git commit -m "feat(template): give a generated project its own dependabot schedule"
```

---

### Task 7: The template's action pins follow the root's

**Files:**
- Modify: `scripts/regen.py` (`action_pins`, `adopt_action_pins`, `main`)
- Modify: `tests/test_regen.py` (four tests)
- Modify: `.github/workflows/ci.yml` (`golden` job comment; an adopt step in the `docs` job)
- Modify: `.github/workflows/adopt.yml` (stage the example too; header comment)
- Modify: `docs/contributing.md` ("Dependabot and the template"), `docs/reference/commands.md` (`just adopt` row), `docs/adr/0017-the-template-is-the-source-of-truth.md` (the `just adopt` consequence)

**Interfaces:**
- Produces: `regen.action_pins(workflows: Path) -> dict[str, str]` (action `owner/repo` → ref; raises `AdoptError` when one action carries two refs); `regen.adopt_action_pins(source: Path, target: Path) -> list[str]` (names of the target files it rewrote); constants `regen.ROOT_WORKFLOWS`, `regen.TEMPLATE_WORKFLOWS`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_regen.py`:

```python
ROOT_WORKFLOWS = ROOT / ".github" / "workflows"
TEMPLATE_WORKFLOWS = ROOT / "{{cookiecutter.project_slug}}" / ".github" / "workflows"


def test_action_pins_reads_every_uses_line(tmp_path: Path) -> None:
    (tmp_path / "a.yml").write_text(
        "steps:\n"
        "  - uses: actions/checkout@v7\n"
        "  - name: x\n"
        "    uses: astral-sh/setup-uv@v7  # pinned by Dependabot\n"
        "    with:\n"
        "      enable-cache: true\n"
    )
    assert regen.action_pins(tmp_path) == {
        "actions/checkout": "v7",
        "astral-sh/setup-uv": "v7",
    }


def test_action_pins_refuses_two_refs_for_one_action(tmp_path: Path) -> None:
    (tmp_path / "a.yml").write_text("- uses: actions/checkout@v7\n")
    (tmp_path / "b.yml").write_text("- uses: actions/checkout@v6\n")
    with pytest.raises(regen.AdoptError, match="actions/checkout"):
        regen.action_pins(tmp_path)


def test_adopt_action_pins_rewrites_only_the_ref(tmp_path: Path) -> None:
    source = tmp_path / "root"
    target = tmp_path / "template"
    source.mkdir()
    target.mkdir()
    (source / "ci.yml").write_text(
        "- uses: actions/checkout@v8\n- uses: docker/login-action@v4\n"
    )
    (target / "ci.yml").write_text(
        "      - uses: actions/checkout@v7\n"
        "      - uses: other/action@v1  # not in the root: left alone\n"
    )
    (target / "release.yml").write_text("      - uses: docker/login-action@v4\n")
    assert regen.adopt_action_pins(source, target) == ["ci.yml"]
    assert (target / "ci.yml").read_text() == (
        "      - uses: actions/checkout@v8\n"
        "      - uses: other/action@v1  # not in the root: left alone\n"
    )
    assert (target / "release.yml").read_text() == "      - uses: docker/login-action@v4\n"
    # Idempotent: a second pass changes nothing.
    assert regen.adopt_action_pins(source, target) == []


def test_the_template_workflows_pin_what_the_root_workflows_pin() -> None:
    # Dependabot's github-actions ecosystem reads /.github/workflows only,
    # so the template's pins follow the root's through `just adopt`. An
    # action the root does not use would never be bumped: add it to a root
    # workflow too, or do not use it in the template.
    template = regen.action_pins(TEMPLATE_WORKFLOWS)
    root = regen.action_pins(ROOT_WORKFLOWS)
    drift = {
        action: (ref, root.get(action))
        for action, ref in template.items()
        if root.get(action) != ref
    }
    assert drift == {}
```

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --group dev pytest tests/test_regen.py -q -k "action_pins or pin_what"`
Expected: 4 FAIL with `AttributeError: module 'regen' has no attribute 'action_pins'`.

- [ ] **Step 3: Implement**

In `scripts/regen.py`, add `import re` to the imports (alphabetical: after `import os`). After `EXCLUDED = frozenset({"uv.lock"})` add:

```python
# Dependabot's github-actions ecosystem reads /.github/workflows only, so its
# bumps land in the root's workflows; the template's workflows follow them
# through --adopt (spec section 8, amended in PR 3).
ROOT_WORKFLOWS = ROOT / ".github" / "workflows"
TEMPLATE_WORKFLOWS = TEMPLATE_BODY / ".github" / "workflows"
USES = re.compile(
    r"^(?P<head>\s*-?\s*uses:\s*)(?P<action>[\w.-]+/[\w./-]+)@(?P<ref>[^\s#]+)(?P<tail>.*)$"
)
```

After `line_runs` add:

```python
def action_pins(workflows: Path) -> dict[str, str]:
    """`owner/repo` -> ref for every `uses:` line in the directory's *.yml."""
    pins: dict[str, str] = {}
    for path in sorted(workflows.glob("*.yml")):
        for line in path.read_text().splitlines():
            match = USES.match(line)
            if match is None:
                continue
            action, ref = match["action"], match["ref"]
            if pins.setdefault(action, ref) != ref:
                raise AdoptError(
                    f"{action} is pinned at both {pins[action]} and {ref} "
                    f"under {workflows}; pin it once"
                )
    return pins


def adopt_action_pins(source: Path, target: Path) -> list[str]:
    """Rewrite each `uses:` ref under `target` to the ref `source` pins it at.

    Only the ref changes: indentation, the action name and any trailing
    comment stay. An action `source` does not use is left alone. Returns the
    names of the files it rewrote.
    """
    pins = action_pins(source)
    changed: list[str] = []
    for path in sorted(target.glob("*.yml")):
        lines = path.read_text().splitlines(keepends=True)
        rewritten: list[str] = []
        for line in lines:
            match = USES.match(line.rstrip("\n"))
            if match is not None and pins.get(match["action"], match["ref"]) != match["ref"]:
                line = f"{match['head']}{match['action']}@{pins[match['action']]}{match['tail']}\n"
            rewritten.append(line)
        if rewritten != lines:
            path.write_text("".join(rewritten))
            changed.append(path.name)
    return changed
```

Replace the body of `main` from `if args.adopt:` to the end of the `with` block with:

```python
        if args.adopt:
            adopted = adopt(rendered, EXAMPLE, TEMPLATE_BODY, answers)
            for name in adopted:
                print(f"adopted into the template: {name}")
            again = Path(scratch) / "again"
            again.mkdir()
            rendered = render(ROOT, answers, again)
            comparison = compare(rendered, EXAMPLE)
            if not comparison.clean:
                report(comparison, rendered, EXAMPLE)
                return 1
            # The other direction: Dependabot bumps the root workflows'
            # action pins, the template's workflows follow, and the example
            # is regenerated so the golden diff stays clean.
            repinned = adopt_action_pins(ROOT_WORKFLOWS, TEMPLATE_WORKFLOWS)
            for name in repinned:
                print(f"adopted the root's action pins into .github/workflows/{name}")
            if repinned:
                repinned_render = Path(scratch) / "repinned"
                repinned_render.mkdir()
                sync(render(ROOT, answers, repinned_render), EXAMPLE)
            print("examples/reference-service matches the template.")
            return 0
        if args.check:
            comparison = compare(rendered, EXAMPLE)
            if comparison.clean:
                print("examples/reference-service matches the template.")
                return 0
            report(comparison, rendered, EXAMPLE)
            return 1
        sync(rendered, EXAMPLE)
        print("examples/reference-service regenerated.")
        return 0
```

Update the module docstring's `--adopt` line to: `regen.py --adopt    copy each line changed in the example back into the template file that renders it, then check; then copy the root workflows' action pins into the template's workflows and regenerate`, and add after the `--adopt` paragraph: `Action pins go the other way: Dependabot's github-actions updates land in the root's .github/workflows only, so --adopt copies each bumped `uses:` ref from there into the template's workflows.`

- [ ] **Step 4: Run the tests, then prove the round trip end to end**

Run: `uv run --group dev pytest tests/test_regen.py -q`
Expected: all PASS (the last test passes because Tasks 3–5 copied the root's refs verbatim).

Prove it end to end without committing anything:

```bash
sed -i '' 's|actions/checkout@v7|actions/checkout@v99|' .github/workflows/*.yml   # every root workflow, or action_pins reports two refs
uv run --group dev pytest tests/test_regen.py -q -k pin_what      # FAIL: drift names actions/checkout
just adopt                                                          # prints the three workflows it repinned
grep -c 'actions/checkout@v99' '{{cookiecutter.project_slug}}/.github/workflows/'*.yml examples/reference-service/.github/workflows/*.yml
just regen-check && uv run --group dev pytest tests/test_regen.py -q -k pin_what   # both green
git checkout -- .github/workflows '{{cookiecutter.project_slug}}' examples/reference-service
git status --short                                                  # empty
```

Expected: `grep -c` prints a non-zero count for every one of the six files (each workflow uses `actions/checkout`); `just regen-check` and the test pass after adoption. (`sed -i ''` is macOS's in-place form; on Linux use `sed -i`.)

- [ ] **Step 5: Root CI**

`.github/workflows/ci.yml`, the `golden` job's comment — after `adopt its pin changes into the template first (M7-10). adopt.yml then` / `commits the same result to main.` add:

```yaml
    #
    # The same step carries the root workflows' action pins into the
    # template's workflows: Dependabot's github-actions ecosystem reads
    # /.github/workflows only, so a `ci(deps)` bump lands here and the
    # template follows it (scripts/regen.py, adopt_action_pins).
```

The `docs` job: directly before the "Run every root-level gate" step add:

```yaml
      - name: Adopt Dependabot's pins into the template
        # Same step, same condition as the `golden` job's: `just check`
        # below runs the golden diff and tests/test_regen.py's check that
        # the template's action pins match the root's, and on a Dependabot
        # pull request neither holds until the pins are adopted.
        if: github.event.pull_request.user.login == 'dependabot[bot]' || github.event.head_commit.author.name == 'dependabot[bot]'
        run: just adopt
```

`.github/workflows/adopt.yml`: in the commit-and-push step, `if git diff --quiet -- '{{cookiecutter.project_slug}}'; then` → `if git diff --quiet -- '{{cookiecutter.project_slug}}' examples/reference-service; then` and `git add -- '{{cookiecutter.project_slug}}'` → `git add -- '{{cookiecutter.project_slug}}' examples/reference-service`. In the header comment, after `so this commit is that proven result, not a new experiment.` add: `A github-actions bump goes the other way -- the root's workflows to the template's -- and regenerates the example, so the example is staged too.`

Run: `uv run --group dev pre-commit run check-yaml --files .github/workflows/ci.yml .github/workflows/adopt.yml`
Expected: Passed.

- [ ] **Step 6: Docs**

`docs/contributing.md`, "Dependabot and the template", append a paragraph:

```markdown
Action versions go the other way. Dependabot's `github-actions` ecosystem
reads `/.github/workflows` only, so its bumps land in this repository's
own workflows, and `just adopt` copies each bumped `uses:` ref into the
template's workflows and regenerates the example. `tests/test_regen.py`
fails when a template workflow pins an action at a different ref than the
root does — or uses one the root does not — so every action a generated
project runs is one Dependabot sees here.
```

`docs/reference/commands.md`, the `just adopt` row: append ` Also copies the root workflows' action pins into the template's workflows and regenerates the example — Dependabot's `github-actions` updates land in `/.github/workflows` only.` before the closing `|`.

`docs/adr/0017-the-template-is-the-source-of-truth.md`, the `just adopt` bullet: `- `just adopt` serves two round trips, not one:` → `- `just adopt` serves three round trips, not one:` and append to the bullet: `; and the root workflows' action pins, which Dependabot can bump only there, are copied into the template's workflows.`

Bump `last_reviewed` on the pages you edited.

- [ ] **Step 7: Verify and commit**

```bash
just lint && just check && just precommit
```

Expected: all exit 0 (`just check` runs the new tests and the golden diff).

```bash
git add scripts/regen.py tests/test_regen.py .github/workflows/ci.yml .github/workflows/adopt.yml docs
git commit -m "feat(regen): adopt the root workflows' action pins into the template"
```

---

### Task 8: Documentation, the generated README, and two stale comments

**Files:**
- Modify: `{{cookiecutter.project_slug}}/README.md` (a new section; the release paragraph under "Supply chain")
- Modify: `{{cookiecutter.project_slug}}/justfile:493` (a stale comment)
- Modify: `docs/contributing.md` ("Working on the template"), `docs/roadmap.md` (the M7 row)
- Regenerated: `examples/reference-service/README.md`, `examples/reference-service/justfile`

- [ ] **Step 1: The generated README — a new section**

Directly before `## Graceful shutdown and the orchestrator's kill deadline`, add:

```markdown
## Continuous integration and releases

Three workflows under `.github/workflows/` and a Dependabot schedule ship
with the project and run from the first push:

| Workflow | Runs | What it does |
|---|---|---|
| `ci.yml` | every push to `main` and every pull request | `just check`, `just test-integration`, `just gates`, `just contract-gates` and `just o11y-gates` as separate jobs, so a failure names its gate; a two-architecture build of every image; `just audit`, `just scan` and `just sbom` |
| `nightly.yml` | 03:17 UTC daily, or by hand | `just mutants-gate`, `just audit`, and a Trivy scan of the images last published — an advisory published against a version already shipped is the failure nothing else would catch |
| `release.yml` | every push to `main`, or by hand | Commitizen reads the Conventional Commits since the last tag, decides the version, writes `CHANGELOG.md`, promotes the API contract baseline, tags, and the images are published under that version; the very first release tags `v0.1.0` without a bump, because there is no tag yet for Commitizen to count from |

`.github/dependabot.yml` opens one grouped pull request per ecosystem each
week: `uv`, `github-actions`, `docker`, `docker-compose` and `pre-commit`.

Four settings live in the GitHub interface, not in this repository:

- **Settings → Actions → General → Workflow permissions → "Read and write
  permissions"**, so `release.yml` can push its tag and bump commit.
- **A `RELEASE_TOKEN` secret, only if a ruleset on `main` requires a pull
  request.** The workflow token cannot pass such a ruleset (`GH013`), and
  on a user-owned repository GitHub does not let the Actions app be
  exempted; a fine-grained personal access token of an exempt admin (this
  repository only; Contents: read and write) stored as `RELEASE_TOKEN` is
  what `release.yml` pushes with. Without such a ruleset, leave the secret
  out — the workflow falls back to its own token.
- **Squash-merge as the merge strategy**, so the pull request title — a
  Conventional Commit — becomes the commit on `main` that Commitizen reads.
- **After the first release, make each GHCR package public** under the
  package's own settings; `publish-images` creates them private, and
  `docker pull` fails for anyone outside the repository until then.
```

- [ ] **Step 2: The README's release paragraph**

In the paragraph beginning `On release, the repository's workflow builds and scans the`: `then builds both images for both` → `then builds every image for both`; and replace the two lines

```markdown
architectures and pushes `ghcr.io/{{ cookiecutter.github_org | lower }}/{{ cookiecutter.project_slug }}` and
`ghcr.io/{{ cookiecutter.github_org | lower }}/{{ cookiecutter.project_slug }}-migrations` under the
```

with

```markdown
architectures and pushes `ghcr.io/{{ cookiecutter.github_org | lower }}/{{ cookiecutter.project_slug }}`
{%- if cookiecutter.database == "postgres" %}
and `ghcr.io/{{ cookiecutter.github_org | lower }}/{{ cookiecutter.project_slug }}-migrations`
{%- endif %}
under the
```

(Markdown joins the lines of a paragraph, so the rendered prose reads the same with the migrations image present or absent.)

- [ ] **Step 3: The justfile's stale comment**

`{{cookiecutter.project_slug}}/justfile`, in the comment above `publish-images`: `# version and revision are only known here. The registry namespace is a` / `# literal until M7 makes it a template variable. `builder` exists so the` → `# version and revision are only known here. The registry namespace is` / `# rendered from the answers (github_org). `builder` exists so the`.

- [ ] **Step 4: Regenerate and check the render**

```bash
just regen && git status --short
grep -c "ghcr.io/emadmokhtar/reference-service-migrations" examples/reference-service/README.md   # 1
(cd examples/reference-service && just check)
```

Expected: the two template files and their two renders changed; the example's `just check` exits 0.

- [ ] **Step 5: `docs/contributing.md` — "Working on the template"**

After the paragraph that ends `at the root runs them over every tracked file.`, add:

```markdown
The template also ships a generated project's `.github/` — `ci.yml`,
`nightly.yml`, `release.yml` and `dependabot.yml`. In this repository
their render at `examples/reference-service/.github/` is output and
inert: GitHub runs workflows from a repository's root only, and the root's
own workflows test the example through `working-directory`. Edit them in
the template. The generation tests parse every render's workflows, check
that each `just` recipe a step calls exists in that render's justfile,
that a pruned backend leaves no word behind in them, and that every
`uses:` ref equals the root's; the workflows themselves run only in a
generated project.
```

- [ ] **Step 6: `docs/roadmap.md` — the M7 row**

Replace the sentence `Still to come: a generated project's own workflows, its own documentation site, and the full-suite tests.` with:

```markdown
The third gave a generated project its own `.github/` — CI, nightly and release workflows and a Dependabot schedule, rendered inert at `examples/reference-service/.github/` — and its own Commitizen; the workflows' action pins follow the root's through `just adopt`. Still to come: a generated project's own documentation site, with the documentation jobs and `docs.yml` that build it, and the full-suite tests.
```

- [ ] **Step 7: Verify and commit**

```bash
just lint && just check && just precommit
```

Expected: all exit 0.

```bash
git add '{{cookiecutter.project_slug}}' examples/reference-service docs/contributing.md docs/roadmap.md
git commit -m "docs: describe a generated project's workflows and repository settings"
```

---

### Task 9: Final verification

**Files:** none modified; this task reports.

- [ ] **Step 1: The root**

```bash
uv run --group dev pytest tests -q
just lint && just check && just precommit && just docs-build
git status --short
```

Expected: every test passes (the 24 matrix cases included); every command exits 0; the status is empty.

- [ ] **Step 2: The example**

```bash
(cd examples/reference-service && just check)
uv run --group dev pre-commit run check-yaml --files examples/reference-service/.github/workflows/*.yml examples/reference-service/.github/dependabot.yml
```

Expected: exit 0; `check-yaml` Passed.

- [ ] **Step 3: Two live renders**

Render `none-none-none` and everything-on live (hook on, network on):

```bash
scratch=$(mktemp -d)
uv run --group dev cookiecutter . --no-input --output-dir "$scratch/off" --default-config database=none cache=none object_storage=none
uv run --group dev cookiecutter . --no-input --output-dir "$scratch/on" --default-config
for tree in "$scratch/off/my-service" "$scratch/on/my-service"; do
  (cd "$tree" && ls .github/workflows && git log --oneline && just lint && just typecheck && just imports && just test; echo "just test exit=$?")
done
rm -rf "$scratch"
```

Expected: each tree lists `ci.yml nightly.yml release.yml`; one commit `chore: generate the project from pyfr` (it passed the commit-msg hook); lint, typecheck and imports exit 0; `just test` fails only the two documented `tests/unit/test_config_docs.py` tests (until PR 4). Record both outputs.

- [ ] **Step 4: Report**

List every commit on the branch (`git log --oneline origin/main..HEAD`), the outputs of Steps 1–3, and anything you left undone.

---

## After the plan: a live smoke test (the controller, with the user's go-ahead)

The rendered workflows never run in this repository (Verified Fact 7). The one proof that they are "real from day one" is a generated project pushed to GitHub: generate with the everything-on answers, create a private scratch repository under the user's account, push, and watch `CI` and `Release` run (the release should tag `v0.1.0` through the bootstrap path and publish `ghcr.io/<owner>/<slug>:v0.1.0`). Creating and later deleting a repository are outward-facing actions: ask the user before each, and do not include this in the subagent tasks.

## Self-review

- **Spec coverage.** §8 `ci.yml` (Task 3), `nightly.yml` (Task 4), `release.yml` with the bootstrap branch live and images under `ghcr.io/{{ github_org }}/{{ project_slug }}` (Task 5), `dependabot.yml` with the five ecosystems (Task 6); `docs.yml` and the documentation jobs — moved to PR 4 (Task 1). M7-9 Commitizen (Task 2). "Schema jobs on database; the Redis and MinIO integration jobs on their backends" — the `gates` job's comment is conditional and `just gates` prunes its own schema half; the integration tier is one job whose recipe prunes per backend, so no job is conditional as a whole. §7 raw guards (Global Constraints; Verified Fact 1). §10.1 the eight-combination tests cover the new files (Task 3). §12 row 3 (Task 1). The reference service's `.github/` appears as output (every task's `just regen`). M7-10 extended to action pins (Task 7).
- **Placeholders.** None: every file is given in full or as an exact edit list against a copied file; every test is written out.
- **Type consistency.** `assert_workflows_are_coherent(root, answers)` (Task 3) is called from `assert_invariant` with the same arguments as `assert_compose_is_self_consistent`; `regen.action_pins` / `regen.adopt_action_pins` / `AdoptError` (Task 7) are used with the same signatures in `main` and the tests; `recipe_names` and `dependency_names` (Verified Fact 6) are used unchanged in Tasks 2 and 3.
