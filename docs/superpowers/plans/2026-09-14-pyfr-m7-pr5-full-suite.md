# PyFr M7 — PR 5: Full-suite tests, the template version, and M7 done — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close milestone M7: prove on every merge to `main` and nightly that a project generated from the template passes its own gates, make every generated project record the template version it came from, and mark the milestone done.

**Architecture:** Three combinations are rendered for real — the post-generation hook runs `git init`, `uv sync` and the first commit, as on a user's machine — and each project's own `just check-all` runs; the tests carry a `full_suite` marker that `pyproject.toml` deselects by default, and a new root workflow runs them off the pull-request path. The template version is moved by the release's `cz bump` itself: Commitizen's `version_files` writes it into `cookiecutter.json`, and its `pre_bump_hooks` runs `just regen` between that write and the bump commit, so the example's `.pyfr-answers.yml` records the released version in the same commit. Four small items handed over from PRs 3 and 4 land alongside: the generator refuses a port the project's own stack binds, every page must be in its site's nav, three template-perspective wordings become project-perspective, and the status pages flip to **Done**.

**Tech Stack:** cookiecutter 2.6 (Python API, `default_config=True`), pytest 8 with `-m` marker selection, Commitizen 4.18.0 (`version_files`, `pre_bump_hooks`, `--check-consistency`), GitHub Actions (`strategy.matrix`), `just`, `uv`, Docker on `ubuntu-latest`, PyYAML.

**Spec:** `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md` — sections 1 (definition of done), 4.4 (regeneration in the release), 5.2 (`pre_gen_project.py`), 5.4 (`.pyfr-answers.yml`), 10.3 (full-suite tests), 11 (PyFr's own CI and release), 12 row 5 (this PR), 13 (error handling: "Full-suite test").

## Global Constraints

- **Conventional Commits** for every commit message and for the PR title (user rule, `CLAUDE.md`). Every commit message ends with the trailer `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`.
- **The template is the source of truth.** Edit `{{cookiecutter.project_slug}}/`, never `examples/reference-service/`; run `just regen` after every template change and commit the result; `just regen-check` must be clean (spec 4.2, ADR 0017).
- **Jinja rules in the template body** (established in PRs 2–4): `{%- if %}`, `{%- elif %}`, `{%- else %}`, `{%- endif %}`, `{%- set %}` each on its own line at column 0; the tag vanishes with its line, and the left-strip eats the blank line before it, so a separating blank line goes *inside* the branch. `{%- set %}` phrase variables are the established form for enumerations that depend on the answers (`README.md` line 202, `docs/reference/http-api.md` line 43).
- **Root workflows are not rendered.** Every `uses:` ref in a root workflow must equal the ref the other root workflows use — today `actions/checkout@v7`, `astral-sh/setup-uv@v7`, `extractions/setup-just@v4` — because `scripts/regen.py`'s `action_pins()` refuses one action pinned at two refs and `tests/test_regen.py` holds the template's pins equal to the root's.
- **Root Python** (`hooks/`, `scripts/`, `tests/`) passes `just lint` (ruff check and format, 88 columns). `hooks/pre_gen_project.py` must stay valid Python *before* rendering (its docstring says why): no `{% if %}` lines inside it; answers arrive through `json.loads(r'''{{ ... | tojson }}''')`.
- **Comments and prose in simple, direct English**; expand an acronym the first time a file uses it; no idioms (user rule).
- **Documentation pages touched get `last_reviewed: 2026-09-14`** (or the day of the edit) in their front matter; the reference service's rendered pages come from the template, never edited directly.
- **No pre-release packages** in either lock (`prerelease = "explicit"`); nothing here adds a dependency.
- **The example's `just check` ends with `git diff --exit-code`**: run it after `git add -A` (or after committing), never on a tree with unstaged regeneration output.
- `pytest` at the root runs through `uv run --group dev pytest` (or `--group dev --group docs` for `just test`); never a bare `pytest`.

## Verified Facts (checked on 2026-09-14 against `main` at `8b25ebc`, v0.9.0)

1. **Commitizen 4.18.0's bump order** (`.venv/lib/python3.13/site-packages/commitizen/commands/bump.py`, lines 344–401): the changelog is written; a dry run raises `DryRunExit` *here*; then `bump.update_version_in_files(current, new, version_files, check_consistency=...)`; then `provider.set_version(new)` (the `uv` provider writes `pyproject.toml`'s `[project].version` and the matching `[[package]]` entry in `uv.lock`, by editing the files with tomlkit, no `uv` call); then `hooks.run(pre_bump_hooks, ...)` — each hook string runs through `subprocess.run(cmd, shell=True, env=os.environ + CZ_PRE_*)` in the current directory; then `git add <updated files>`, `git commit -a`, `git tag`, then `post_bump_hooks`. So a pre-bump hook runs **after** the version is on disk and **before** the commit, and whatever it changes in *tracked* files rides in the bump commit (`-a` stages modified tracked files only — a new untracked file would not).
2. **`version_files` entries of the form `file:regex`** replace the *current* version string on lines matching the regex. A line that does not contain the current version is left alone silently — unless `cz bump --check-consistency` is given, which then fails with "Current version X is not found in <file>". `cookiecutter.json` today says `"_template_version": "0.6.0"` while `pyproject.toml` says `0.9.0`, so the first thing this PR does is set them equal; from then on the bump moves both.
3. **`pytest -m full_suite` on the command line replaces `-m "not full_suite"` from `addopts`** (the last `-m` wins; verified with a two-test project: default run → `1 passed, 1 deselected`; `-m slow` → the marked test alone). `-k ""` is no filter at all (`keywordexpr` is empty, so `deselect_by_keyword` returns).
4. **A fresh render passes its own `just check-all` today.** Rendered with the real hook (no `PYFR_REGEN`), so `git init`, `uv sync` (a fresh `uv.lock`, 126 packages resolved) and the first commit ran: everything off with the default identity → `EXIT=0` in about three minutes including downloads; everything on with `project_name="Orders API" github_org=acme license=MIT http_port=8080` → `EXIT=0` in about ninety seconds (449 unit tests, 36 integration tests through testcontainers, the schema gates, `config-docs-check`, `o11y-gates`, 6 contract tests, `check_contract_compatibility.py`). Local Docker 29.7.2. Nothing binds a host port during `check-all`: the integration tier uses testcontainers (random host ports), and `docs-examples` — which does start the compose stack — is not in `check-all`.
5. **Host ports the generated stack binds** (`{{cookiecutter.project_slug}}/compose.yaml`): `5432` (postgres, only with `database=postgres`), `6379` (redis, only with `cache=redis`), `9000` and `9001` (minio, only with `object_storage=s3`), `9099` (`payment-stub`, always; its container port is `8080`), `3000`, `4317`, `4318`, `9090` (`lgtm`, profile `o11y`, always present); `just docs` serves on `8001`. No template file mentions `9100` or `8090`; `8080` appears once, as the payment stub's *container* port.
6. **`scripts/regen.py`'s `render()` sets `os.environ["PYFR_REGEN"] = "1"` for the whole process**, and `tests/test_golden.py` / `tests/test_regen.py` call it. A test that needs the hook's side effects must `monkeypatch.delenv("PYFR_REGEN", raising=False)` — an earlier test in the same session may have set it.
7. **`uv run` at the root exports `VIRTUAL_ENV=<root>/.venv`.** Inside a render, every `uv` command then prints `warning: VIRTUAL_ENV=... does not match the project environment path .venv and will be ignored` and uses the project's own `.venv`. Harmless, but noisy: the full-suite fixture unsets it.
8. **Both sites' navs are complete except `adr/template.md`** (the copy-me template, deliberately outside the nav); the root `mkdocs.yml` excludes `docs/superpowers/` through `exclude_docs`. A page in no nav is an INFO line from MkDocs, which `--strict` does not fail on.
9. **Nothing in `tests/` or `hooks/` pins the default `description`** (`A Python microservice generated from PyFr.`); the root `docs/getting-started.md` prompts table shows it (line 43). The template's `README.md` prints `{{ cookiecutter.description }} Generated from [PyFr](...)`, so the default reads "…generated from PyFr. Generated from PyFr."
10. **`tests/test_generation.py:135`** asserts `recorded["_template_version"] == "0.6.0"`; the file already imports `tomllib` and defines `ROOT`. The two port tests (`test_a_custom_port_reaches_every_place_the_port_lives`, `test_the_docs_carry_the_chosen_port`) render `http_port="9000"` with the default (everything-on) answers, which Task 4's rule refuses — they move to `9100`.
11. **Commitizen's default bump message** is `bump: version $current_version → $new_version` (main's log: `bump: version 0.8.0 → 0.9.0`); with `major_version_zero = true`, a `feat:` commit bumps MINOR (`0.9.0` → `0.10.0`), which is how `cz_conventional_commits`' `bump_map` reads `feat`.
12. **`release.yml` today** runs `cp <template>/openapi.json <template>/openapi.baseline.json` and then `just regen` *before* `cz bump --yes --changelog`, relying on `git commit -a` to carry both into the bump commit (lines 156–184). Its "Install just" step comment (line 84) says the binary is "For `just regen` in the bump step".
13. **`just` is on PATH wherever the root tests run**: CI's `docs` job calls `just check` through `extractions/setup-just@v4`, and contributors already need `just` for every recipe.
14. **The identity test** in `tests/test_generation.py` sweeps `IDENTITY_TREES = ("docs", "README.md", "scripts", "mkdocs.yml", ".github")` of a render for the reference identity, excepting the two PyFr URLs `github.com/EmadMokhtar/pyfr` and `emadmokhtar.github.io/pyfr/`; a link to PyFr's roadmap page is allowed.
15. **`scripts/check_site_links.py`** (run by root `just docs-build`) resolves every `https://emadmokhtar.github.io/pyfr/...` link in the root and example Markdown against the built `site/`; `roadmap/` exists there.

## Rulings made while planning

- **One gate command per combination.** Spec 10.3 says "run the generated project's `just check` and … `just check-all`". `check-all`'s first dependency *is* `check` (`check-all: check docs-build test-integration gates o11y-gates contract-gates`), so the test runs `just check-all` once: `check` runs first, in the spec's order, and nothing runs twice. Cost if wrong: none — a failure still names the recipe.
- **The regen step is a Commitizen pre-bump hook, not a workflow step.** Spec 4.4 asks for "one step between `cz bump` and the commit"; `cz bump` writes the files and commits in one command, so no workflow step can sit between them. `pre_bump_hooks` is exactly that slot (Verified Fact 1). Spec 4.4 gets an amendment note. The explicit `just regen` line in `release.yml` goes: the hook does it, later, with the new version already on disk.
- **The closing release is "the release that closes M7", not `v0.7.0`.** The spec named `v0.7.0` before the milestone took four releases (`v0.6.0` … `v0.9.0`). Commitizen numbers it; the spec's three mentions are amended to say so. The PR is a `feat:` (a generated project records its template version; the generator refuses colliding ports), so merging it cuts that release.
- **ADR 0016's Context and Alternatives keep the `migrate/migrate` story in every render** (ledgered by PR 4). An ADR's Context is why the decision was taken; the migrations image is that reason whether or not this project has one, and the Decision and Consequences are already gated per backend. Nothing changes there.
- **The nested docs build keeps `uv run --group docs`** (PR 4's "lighter syncs" item). `--only-group docs` would uninstall the example's `dev` group from its `.venv` every time `just docs-build` runs at the root, and `just test` there would reinstall it — a slower loop for a contributor to save one sync in CI. Dropped.
- **Follow-up issue #36 (storage-subject tests) is not M7 work** and stays an issue.
- **The identity-varying render** PR 4 asked for is folded into the full-suite combinations: two of the three use a different name, organisation, licence and port, so the slow tests prove those substitutions produce a working project at no extra cost. The fast identity test already covers the text sweep.

## File structure

| File | Task | Responsibility |
| --- | --- | --- |
| `tests/conftest.py` (new) | 1 | Records each test's call outcome on its item, so a fixture can keep a render on disk only when its test failed. |
| `tests/test_generated_service.py` (new) | 1 | The three full-suite tests. |
| `pyproject.toml` | 1, 3 | The `full_suite` marker and its default deselection; Commitizen's `version_files` and `pre_bump_hooks`. |
| `justfile` | 1 | `test-full-suite [combination]`. |
| `docs/contributing.md` | 1, 2, 3 | The full-suite tests, the workflow, the command row, the template version. |
| `.github/workflows/full-suite.yml` (new) | 2 | Runs the three tests on push to `main`, nightly and on demand, one job per combination. |
| `README.md` | 2, 7 | The Full suite badge; the status section. |
| `cookiecutter.json` | 3, 6 | `_template_version` = the repository version; the default description. |
| `.github/workflows/release.yml` | 3 | `cz bump --check-consistency`; the regen moves into the hook; comments. |
| `tests/test_generation.py` | 3, 4 | `TEMPLATE_VERSION` from `pyproject.toml`; the equality test; the port tests on `9100`. |
| `tests/test_release_bump.py` (new) | 3 | A real `cz bump` in a throwaway repository proves the order: version files, hook, commit. |
| `hooks/pre_gen_project.py` | 4 | Refuses an `http_port` the project's own stack binds. |
| `tests/test_hooks.py` | 4 | The refused ports, and a backend's port free when the backend is absent. |
| `docs/getting-started.md` | 4, 6 | The `http_port` row; the `description` default. |
| `{{cookiecutter.project_slug}}/justfile` | 4 | The `docs` recipe's comment no longer assumes port 8000. |
| `tests/test_site_nav.py` (new) | 5 | Every page under `docs/` is in its site's nav — root, example, and an everything-off render. |
| `{{cookiecutter.project_slug}}/README.md`, `docs/getting-started.md`, `docs/adr/README.md` | 6 | Project-perspective wording. |
| `docs/roadmap.md`, `docs/index.md`, the spec | 7 | M7 **Done**; the version amendments. |
| `examples/reference-service/**` | 3, 4, 6 | Regenerated output only. |

---

### Task 1: The full-suite tests

**Files:**
- Create: `tests/conftest.py`
- Create: `tests/test_generated_service.py`
- Modify: `pyproject.toml` (`[tool.pytest.ini_options]`, lines 108–110)
- Modify: `justfile` (after the `test:` recipe, line 62)
- Modify: `docs/contributing.md` (after the paragraph ending "The workflows themselves run only in a generated project.", line 100; the command table, line 634)

**Interfaces:**
- Consumes: `scripts/regen.py`'s `load_answers()` (returns `tests/reference-answers.yaml` as `dict[str, str]`); the post-generation hook's first commit message `chore: generate the project from pyfr` (`hooks/post_gen_project.py`, `set_up()`).
- Produces: the marker name `full_suite`; the test ids `everything-on`, `everything-off`, `postgres-only`; the recipe `just test-full-suite [combination]` — Task 2's workflow calls it with one id per job.

- [ ] **Step 1: Register the marker and deselect it by default**

In `pyproject.toml`, replace

```toml
[tool.pytest.ini_options]
addopts = "-q --strict-markers --strict-config"
testpaths = ["tests"]
```

with

```toml
[tool.pytest.ini_options]
# `-m "not full_suite"` keeps the full-suite tests out of every ordinary
# run: `just test`, CI's `docs` job, a bare `pytest`. A `-m` given on the
# command line replaces this one (the last `-m` wins), so
# `pytest -m full_suite` runs exactly those -- that is what
# `just test-full-suite` and .github/workflows/full-suite.yml do.
addopts = "-q --strict-markers --strict-config -m \"not full_suite\""
markers = [
    "full_suite: renders a project for real -- the hook runs `uv sync` and `git init` -- and runs its own `just check-all`; slow, needs Docker and the network (spec section 10.3)",
]
testpaths = ["tests"]
```

- [ ] **Step 2: Write the conftest hook**

Create `tests/conftest.py`:

```python
"""Shared pytest plumbing for the repository's own tests."""

from __future__ import annotations

import pytest


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    # Records whether the test body failed on the item itself, so a
    # fixture's teardown can read `request.node.failed`. The full-suite
    # fixture keeps a rendered project on disk only when its test failed:
    # each render carries a `.venv/` of a few hundred megabytes, and
    # pytest keeps the last three sessions' temporary directories.
    report = yield
    if report.when == "call":
        item.failed = report.failed  # type: ignore[attr-defined]
    return report
```

- [ ] **Step 3: Write the full-suite tests**

Create `tests/test_generated_service.py`:

```python
"""A generated project passes its own gates -- the full-suite tests.

The generation tests prove every render is well-formed; these prove three
of them are services. Each is rendered WITHOUT PYFR_REGEN, so the
post-generation hook runs `git init`, `uv sync` (a fresh lock, resolved
today) and the first commit, exactly as on a user's machine; then the
project's own `just check-all` runs -- every gate its CI runs as separate
jobs, as one command (spec section 10.3). Three syncs and three full gate
runs are too slow for every push: the tests carry the `full_suite`
marker, pyproject.toml deselects it by default, and
.github/workflows/full-suite.yml runs them on every merge to main, nightly
and on demand. Locally: `just test-full-suite`, with Docker running.

The three combinations: everything on, with the reference service's own
answers -- the render examples/reference-service/ is the golden copy of,
this time synced and gated from scratch; everything off; and PostgreSQL
alone. The last two also change the identity answers, so a project that
is not called `reference-service`, on another port, under another
organisation and licence, is proven to pass its gates too.

A failing gate fails the test with that gate's output: `just` is run
uncaptured, and pytest shows a failed test's captured output in full.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import regen  # noqa: E402

pytestmark = pytest.mark.full_suite

# The ports are ones nothing in the template mentions and nothing in the
# generated stack binds (hooks/pre_gen_project.py refuses those).
COMBINATIONS: dict[str, dict[str, str]] = {
    "everything-on": regen.load_answers(),
    "everything-off": {
        "project_name": "Notify Service",
        "description": "Sends notifications.",
        "author_name": "Ada Lovelace",
        "author_email": "ada@example.com",
        "github_org": "acme",
        "database": "none",
        "cache": "none",
        "object_storage": "none",
        "http_port": "9100",
        "license": "MIT",
    },
    "postgres-only": {
        "project_name": "Orders API",
        "description": "Takes orders.",
        "author_name": "Grace Hopper",
        "author_email": "grace@example.com",
        "github_org": "example-org",
        "database": "postgres",
        "cache": "none",
        "object_storage": "none",
        "http_port": "8090",
        "license": "Apache-2.0",
    },
}
FIRST_COMMIT = "chore: generate the project from pyfr"


@pytest.fixture(params=list(COMBINATIONS))
def project(
    request: pytest.FixtureRequest,
    tmp_path_factory: pytest.TempPathFactory,
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[Path]:
    """A project rendered for real; kept on disk only when its test fails."""
    # scripts/regen.py sets PYFR_REGEN for the whole process and an earlier
    # test in this session may have called it; the hook must see it unset
    # here or it prunes and stops without the sync and the commit.
    monkeypatch.delenv("PYFR_REGEN", raising=False)
    # The root's `uv run` exports its own environment; inside the render
    # every `uv` command would warn that it does not match the project's
    # `.venv` and ignore it. Unset, the project's own environment is the
    # only one in sight, as on a user's machine.
    monkeypatch.delenv("VIRTUAL_ENV", raising=False)
    # Imported here so the marker's deselection never needs cookiecutter.
    from cookiecutter.main import cookiecutter

    output = tmp_path_factory.mktemp(request.param)
    rendered = Path(
        cookiecutter(
            str(ROOT),
            no_input=True,
            extra_context=COMBINATIONS[request.param],
            output_dir=str(output),
            # Never read ~/.cookiecutterrc: a contributor's defaults must
            # not reach a render this proves.
            default_config=True,
        )
    )
    yield rendered
    if getattr(request.node, "failed", False):
        print(f"\nThe failed render is kept at {rendered}")
    else:
        shutil.rmtree(output)


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def test_a_generated_project_passes_every_one_of_its_gates(project: Path) -> None:
    # The hook's side effects, in the order it runs them: `git init`,
    # `uv sync`, `pre-commit install`, then one commit of everything. The
    # commit is what `just check` needs -- it ends in `git diff
    # --exit-code` -- and its presence proves the three steps before it
    # did not fall back to "run it later".
    assert git("log", "--format=%s", cwd=project).splitlines() == [FIRST_COMMIT]
    assert (project / "uv.lock").is_file()
    assert (project / ".git" / "hooks" / "pre-commit").is_file()
    assert git("status", "--porcelain", cwd=project) == ""
    # `check-all` runs `check` first (lint, types, imports, tests, hooks),
    # then the site build, the container tier and the three gate recipes:
    # the six jobs the project's CI runs separately, in one command.
    subprocess.run(["just", "check-all"], cwd=project, check=True)
```

- [ ] **Step 4: Run the fast suite to prove the deselection**

Run: `uv run --group dev pytest tests/test_generated_service.py`
Expected: `3 deselected` and exit code 5 ("no tests ran") — the marker is registered (`--strict-markers` did not complain) and the default `-m` keeps them out. Then run `uv run --group dev pytest tests/test_hooks.py -q` and expect every test to pass as before (the conftest hook must not disturb anything).

- [ ] **Step 5: Run one combination for real**

Run: `uv run --group dev pytest -m full_suite -k everything-off tests/test_generated_service.py`
Expected: `1 passed` in roughly three minutes with Docker running (Verified Fact 4). The render's output streams through pytest; nothing is left under pytest's temporary directory for that test afterwards (`ls /tmp/pytest-of-$USER/pytest-current/` shows no `everything-off*` directory).

Then run all three: `uv run --group dev pytest -m full_suite tests/test_generated_service.py` — Expected: `3 passed`.

- [ ] **Step 6: Add the recipe**

In `justfile`, after the `test:` recipe (line 62), add:

```just
# The full-suite tests: render three combinations for real -- the hook
# runs `uv sync` and `git init` -- and run each project's own
# `just check-all`. Slow (a few minutes per combination) and needs Docker
# and the network. CI runs them on every merge to main and nightly
# (.github/workflows/full-suite.yml), never on a pull request; `just test`
# deselects them. `combination` narrows the run to one test id:
# everything-on, everything-off or postgres-only.
test-full-suite combination="":
    uv run --group dev pytest -m full_suite -k "{{combination}}" tests/test_generated_service.py
```

Run: `just test-full-suite postgres-only`
Expected: `1 passed, 2 deselected`.

- [ ] **Step 7: Document them**

In `docs/contributing.md`, after the paragraph ending "The workflows themselves run only in a generated project." (line 100), add:

```markdown
### The full-suite tests

The generation tests prove every render is well-formed. Three renders are
also proven to be *services*: `tests/test_generated_service.py` renders
everything on (the reference answers), everything off, and PostgreSQL
alone, for real — the post-generation hook runs `git init`, `uv sync` and
the first commit, exactly as on a user's machine — and runs each project's
own `just check-all`, the six gates its CI runs as separate jobs. The two
smaller combinations also change the name, organisation, licence and port,
so those substitutions are proven to produce a working project too. Three
syncs and three full gate runs take too long for every push, so the tests
carry the `full_suite` marker, `pyproject.toml` deselects it by default,
and `.github/workflows/full-suite.yml` runs them on every merge to `main`,
nightly, and on demand — one job per combination. Locally, with Docker
running:

```bash
just test-full-suite            # all three, a few minutes each
just test-full-suite postgres-only
```

A failing gate fails the test with that gate's output, and the render is
kept on disk (the test prints where); a passing render is removed, since
each carries a `.venv/` of a few hundred megabytes.
```

In the command table, after the `just test` row, add:

```markdown
| `just test-full-suite [combination]` | The full-suite tests: three combinations rendered for real, synced, committed and run through their own `just check-all`. Slow; needs Docker and the network. `combination` is one of `everything-on`, `everything-off`, `postgres-only`. CI runs them on merge to `main` and nightly, never on a pull request — see [above](#the-full-suite-tests). |
```

Set `last_reviewed: 2026-09-14` in the page's front matter (it already is; keep it current with the day of the edit).

- [ ] **Step 8: Lint, then commit**

Run: `just lint` — Expected: no findings. Run: `uv run --group dev pytest tests/ -q` — Expected: every fast test passes, `3 deselected`.

```bash
git add tests/conftest.py tests/test_generated_service.py pyproject.toml justfile docs/contributing.md
git commit -m "test: prove three generated projects pass their own gates

Rendered without PYFR_REGEN, so the hook syncs, commits and installs the
hooks as it does for a user, then each project's just check-all runs.
Marked full_suite and deselected by default: three syncs and three gate
runs are too slow for every push (spec section 10.3).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: The `full-suite.yml` workflow

**Files:**
- Create: `.github/workflows/full-suite.yml`
- Modify: `README.md` (badges, line 9)
- Modify: `docs/contributing.md` (front matter `covers:`, lines 3–9; the layout listing, line 31)

**Interfaces:**
- Consumes: `just test-full-suite <combination>` and the ids `everything-on`, `everything-off`, `postgres-only` from Task 1.
- Produces: nothing later tasks use.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/full-suite.yml`:

```yaml
name: Full suite

# Proves that what the generation tests call a well-formed render is also
# a service that passes its own gates: three combinations are rendered for
# real -- the post-generation hook runs `git init`, `uv sync` and the
# first commit, as on a user's machine -- and each project's own
# `just check-all` runs (spec section 10.3). Three syncs and three full
# gate runs are too slow for every push, so this is not part of ci.yml:
# it runs on every merge to main, nightly, and on demand. `just test`
# deselects these tests; `just test-full-suite` runs them locally.
#
# This is PyFr's own workflow, not template content: the template's
# workflows live under {{cookiecutter.project_slug}}/.github/.

on:
  push:
    branches: [main]
  schedule:
    # 04:17 UTC, an hour after nightly.yml, and off the hour for the
    # reason that workflow gives: every scheduled job on GitHub is queued
    # at :00, and a job that starts when the queue is empty starts sooner.
    - cron: "17 4 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  generated-service:
    # One job per combination: a failure names the combination in the job
    # name, and the three run side by side instead of one after another.
    # `fail-fast: false` because the other two results are the point when
    # one fails.
    strategy:
      fail-fast: false
      matrix:
        combination: [everything-on, everything-off, postgres-only]
    name: ${{ matrix.combination }}
    runs-on: ubuntu-latest
    # A render's `uv sync` from a cold cache, its container tier and the
    # image pulls for the schema gates and o11y-gates all fit in a
    # fraction of this; the limit exists so a hung container cannot hold
    # the runner for six hours.
    timeout-minutes: 45
    steps:
      - uses: actions/checkout@v7
      - uses: astral-sh/setup-uv@v7
        with:
          # The render resolves the same packages the example's uv.lock
          # pins, so the cache the example's jobs fill serves it too.
          enable-cache: true
      - uses: extractions/setup-just@v4
      - name: Render the project and run its own gates
        run: just test-full-suite ${{ matrix.combination }}
```

- [ ] **Step 2: Check the file parses and its pins agree with the other root workflows**

Run: `uv run --group dev python -c "import yaml, pathlib; print(sorted(yaml.safe_load(pathlib.Path('.github/workflows/full-suite.yml').read_text())['jobs']))"`
Expected: `['generated-service']`.

Run: `uv run --group dev pytest tests/test_regen.py -q`
Expected: every test passes — in particular the pin-drift test, which reads every root `*.yml` through `action_pins()` and would fail on a ref that differs from `ci.yml`'s.

- [ ] **Step 3: The badge and the page**

In `README.md`, after the CI badge (line 9), add:

```markdown
[![Full suite](https://github.com/EmadMokhtar/pyfr/actions/workflows/full-suite.yml/badge.svg)](https://github.com/EmadMokhtar/pyfr/actions/workflows/full-suite.yml)
```

In `docs/contributing.md`'s front matter, add `  - .github/workflows/full-suite.yml` after `  - .github/workflows/docs.yml`. In the layout listing, change

```
  .github/workflows/           continuous integration and publishing
```

to

```
  .github/workflows/           continuous integration, the full suite, publishing
```

- [ ] **Step 4: Commit**

Run: `just docs-build` — Expected: both sites build with `--strict`; `Every cross-site link resolves…`.

```bash
git add .github/workflows/full-suite.yml README.md docs/contributing.md
git commit -m "ci: run the full-suite tests on merge to main and nightly

One job per combination, off the pull-request path (spec section 11).

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: The template version follows the release

**Files:**
- Modify: `cookiecutter.json` (`_template_version`, line 14)
- Modify: `pyproject.toml` (`[tool.commitizen]`, after `version_provider = "uv"`, line 38)
- Modify: `.github/workflows/release.yml` (lines 83–88, 166–184)
- Modify: `tests/test_generation.py` (line 135; a new test after `test_every_combination_renders_and_records_its_answers`)
- Create: `tests/test_release_bump.py`
- Modify: `docs/contributing.md` (after the paragraph ending "and the root's hook is the one that checks your messages.", line 546)
- Modify: `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md` (section 4.4, lines 149–157)
- Regenerate: `examples/reference-service/.pyfr-answers.yml`

**Interfaces:**
- Consumes: Verified Facts 1, 2, 11, 12.
- Produces: `TEMPLATE_VERSION` in `tests/test_generation.py` (the `[project].version` of the root `pyproject.toml`); the invariant `cookiecutter.json["_template_version"] == pyproject.toml [project].version`, which Task 7 and every future release rely on.

- [ ] **Step 1: Write the failing equality test**

In `tests/test_generation.py`, after `REFERENCE_ANSWERS = ROOT / "tests" / "reference-answers.yaml"` (line 22), add:

```python
# The version the release last wrote into pyproject.toml. cookiecutter.json
# cannot compute, so its `_template_version` is written by the same
# `cz bump` (pyproject.toml's [tool.commitizen] version_files) and must
# equal this at every commit.
TEMPLATE_VERSION: str = tomllib.loads((ROOT / "pyproject.toml").read_text())[
    "project"
]["version"]
```

Replace line 135, `assert recorded["_template_version"] == "0.6.0"`, with `assert recorded["_template_version"] == TEMPLATE_VERSION`.

After that test function, add:

```python
def test_the_template_version_is_the_repository_version() -> None:
    # A hand edit of either file between releases would drift them apart;
    # `cz bump --check-consistency` in release.yml then refuses to release
    # a version it cannot find on cookiecutter.json's line, and this fails
    # first, on the pull request.
    answers = json.loads((ROOT / "cookiecutter.json").read_text())
    assert answers["_template_version"] == TEMPLATE_VERSION
```

and add `import json` to the imports (alphabetically, after `import ast`).

- [ ] **Step 2: Run them to see them fail**

Run: `uv run --group dev pytest tests/test_generation.py -q -k "records_its_answers or template_version_is_the_repository"`
Expected: 9 failures, each `assert '0.6.0' == '0.9.0'`.

- [ ] **Step 3: Set the version and wire the bump**

In `cookiecutter.json`, change `"_template_version": "0.6.0",` to `"_template_version": "0.9.0",` — the version `pyproject.toml` carries today. (If `main`'s `[project].version` has moved by the time this runs, use that value; the test in Step 1 is the check.)

In `pyproject.toml`, after `version_provider = "uv"` (line 38) and before `tag_format = "v$version"`, add:

```toml
# The template version every generated project records in its
# .pyfr-answers.yml, moved by the same bump: cookiecutter.json's
# `_template_version` is the version on disk here, always
# (tests/test_generation.py holds the two equal), and a render copies it.
# Commitizen replaces the CURRENT version on the line the pattern names,
# and release.yml passes `--check-consistency` so a bump that cannot find
# it there fails instead of leaving the template version behind.
version_files = ["cookiecutter.json:_template_version"]
# Runs after `cz bump` has written the new version into pyproject.toml,
# uv.lock and cookiecutter.json, and before its commit -- the one slot
# between the two, since `cz bump` writes and commits in a single command.
# The regeneration rewrites the example's .pyfr-answers.yml with the
# version being released and carries the contract baseline release.yml
# promotes in the template body into the example; `cz bump` commits with
# `git commit -a`, so both ride in the bump commit (spec section 4.4). A
# dry run (`just next-version`) stops before any file is written and never
# reaches this. Needs `just` on PATH, which release.yml installs.
pre_bump_hooks = ["just regen"]
```

- [ ] **Step 4: Move the regen out of the workflow**

In `.github/workflows/release.yml`, replace the "Install just" step's comment (lines 84–87)

```yaml
        # For `just regen` in the bump step. This puts a binary on the
        # runner's PATH and writes nothing into the checkout, so it does
        # not fall foul of the "nothing writes before the bump" rule that
        # step's comment explains.
```

with

```yaml
        # For the `just regen` that `cz bump` runs as its pre-bump hook
        # (pyproject.toml, [tool.commitizen]). This puts a binary on the
        # runner's PATH and writes nothing into the checkout, so it does
        # not break the "nothing writes before the bump" rule the bump
        # step's comment explains.
```

Replace lines 166–184 — from the comment line `# In PyFr's own repository the baseline lives in the template` through `uv run --locked --group dev cz bump --yes --changelog` — with:

```yaml
            # In PyFr's own repository the baseline lives in the template
            # body and examples/reference-service/ is rendered from it
            # (ADR 0017), so the promotion happens there, and `just regen`
            # carries it into the example. That regeneration is `cz
            # bump`'s pre-bump hook (pyproject.toml): it runs after the
            # bump has written the new version into pyproject.toml,
            # uv.lock and cookiecutter.json's `_template_version`, and
            # before the bump commit, so the example's .pyfr-answers.yml
            # records the version being released in that same commit.
            # Promoting inside the example instead -- `just
            # contract-release` there -- would leave the example's
            # baseline ahead of the template's, and the `golden` job red
            # from the next pull request on. A generated project runs
            # `just contract-release` in its own tree.
            #
            # If cz decides there is nothing to release (exit 3 or 21
            # below), the hook never runs and this copy is discarded with
            # the runner: nothing is committed and nothing is pushed.
            #
            # --check-consistency: a bump that cannot find the current
            # version on cookiecutter.json's `_template_version` line
            # fails here rather than release a template that records the
            # wrong version.
            cp '{{cookiecutter.project_slug}}/openapi.json' '{{cookiecutter.project_slug}}/openapi.baseline.json'

            set +e
            uv run --locked --group dev cz bump --yes --changelog --check-consistency
```

Keep everything after (`status=$?` onwards) unchanged. Run `uv run --group dev python -c "import yaml, pathlib; yaml.safe_load(pathlib.Path('.github/workflows/release.yml').read_text())"` — Expected: no error.

- [ ] **Step 5: Regenerate and run the fast tests**

Run: `just regen` — Expected: `examples/reference-service regenerated.`; `git status --short` shows exactly `examples/reference-service/.pyfr-answers.yml` modified (its `_template_version` line now `"0.9.0"`) besides the files edited above.

Run: `uv run --group dev pytest tests/test_generation.py tests/test_golden.py -q`
Expected: all pass.

- [ ] **Step 6: Write the failing end-to-end bump test**

Create `tests/test_release_bump.py`:

```python
"""The release's bump commit moves the template version and regenerates.

release.yml runs `cz bump`; what makes that one command carry
cookiecutter.json's `_template_version` and the example's regenerated
.pyfr-answers.yml is configuration in pyproject.toml -- `version_files`
and `pre_bump_hooks` -- and the order Commitizen applies it in: the
version files, then the hook, then the commit (spec section 4.4). This
drives a real `cz bump` in a throwaway repository that carries the root's
own pyproject.toml, uv.lock and cookiecutter.json, with a stub justfile
whose `regen` recipe records what it saw in place of the regeneration.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
# Commitizen from the root's own environment, the one the release runs
# (`uv run --locked --group dev cz`). `uv run` inside the throwaway
# repository would try to sync its copy of pyproject.toml instead.
CZ = Path(sys.executable).parent / "cz"


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def version_in(repository: Path) -> str:
    return tomllib.loads((repository / "pyproject.toml").read_text())["project"][
        "version"
    ]


@pytest.fixture
def repository(tmp_path: Path) -> Path:
    repository = tmp_path / "pyfr"
    repository.mkdir()
    for name in ("pyproject.toml", "uv.lock", "cookiecutter.json"):
        shutil.copy(ROOT / name, repository / name)
    # The stand-in for `just regen` copies cookiecutter.json as it is at
    # the moment the hook runs. The copy is a TRACKED file: `cz bump`
    # commits with `git commit -a`, which picks up modified tracked files
    # and nothing else -- the same way it picks up the example's
    # regenerated .pyfr-answers.yml.
    (repository / "justfile").write_text(
        "regen:\n    cp cookiecutter.json regen-saw.json\n"
    )
    (repository / "regen-saw.json").write_text("{}\n")
    git("init", "-q", cwd=repository)
    git("config", "user.name", "Test", cwd=repository)
    git("config", "user.email", "test@example.com", cwd=repository)
    git("add", "-A", cwd=repository)
    git("commit", "-q", "-m", "chore: start", cwd=repository)
    git("tag", f"v{version_in(repository)}", cwd=repository)
    (repository / "feature.txt").write_text("new\n")
    git("add", "feature.txt", cwd=repository)
    git("commit", "-q", "-m", "feat: add a feature", cwd=repository)
    return repository


def test_the_bump_commit_carries_the_template_version_and_the_regen(
    repository: Path,
) -> None:
    before = version_in(repository)
    major, minor, _ = before.split(".")
    # One feat: commit since the tag, and major_version_zero: MINOR moves.
    expected = f"{major}.{int(minor) + 1}.0"

    subprocess.run(
        [str(CZ), "bump", "--yes", "--changelog", "--check-consistency"],
        cwd=repository,
        check=True,
    )

    assert version_in(repository) == expected
    answers = json.loads((repository / "cookiecutter.json").read_text())
    assert answers["_template_version"] == expected
    # The hook ran AFTER the version was written ...
    seen = json.loads((repository / "regen-saw.json").read_text())
    assert seen["_template_version"] == expected
    # ... and BEFORE the commit, which carries its output beside the
    # version files, under the bump message, with the tag on it.
    committed = set(git("show", "--name-only", "--format=", "HEAD", cwd=repository).split())
    assert {
        "pyproject.toml",
        "uv.lock",
        "cookiecutter.json",
        "regen-saw.json",
        "CHANGELOG.md",
    } <= committed
    subject = git("log", "-1", "--format=%s", cwd=repository).strip()
    assert subject == f"bump: version {before} → {expected}"
    assert f"v{expected}" in git("tag", cwd=repository).split()
    assert git("status", "--porcelain", cwd=repository) == ""


def test_a_dry_run_writes_nothing_and_runs_no_hook(repository: Path) -> None:
    # `just next-version` is `cz bump --dry-run`: it must stay read-only,
    # and the hook must not fire from it.
    subprocess.run([str(CZ), "bump", "--dry-run"], cwd=repository, check=True)
    assert git("status", "--porcelain", cwd=repository) == ""
    assert (repository / "regen-saw.json").read_text() == "{}\n"
```

Prove the test has teeth before trusting it: temporarily comment out the `pre_bump_hooks = ["just regen"]` line in `pyproject.toml`, run `uv run --group dev pytest tests/test_release_bump.py -q`, and expect the first test to fail at `seen["_template_version"]` with `KeyError: '_template_version'` — without the hook the stub copy never runs and `regen-saw.json` still holds `{}`. Restore the line. (No `git stash` in this worktree; the wiring is what the test needs on disk.)

- [ ] **Step 7: Run it green**

Run: `uv run --group dev pytest tests/test_release_bump.py -q`
Expected: `2 passed` in a few seconds (the `uv` provider parses the copied `uv.lock` with tomlkit; that is the slow part).

- [ ] **Step 8: Document, amend the spec, commit**

In `docs/contributing.md`, after the paragraph ending "and the root's hook is the one that checks your messages." (line 546), add:

```markdown
The release moves one more version. `cookiecutter.json`'s
`_template_version` — the value every generated project records in its
`.pyfr-answers.yml` — is written by the same `cz bump` as
`pyproject.toml`'s version (`version_files` in `[tool.commitizen]`), and
`just regen` runs as that bump's pre-bump hook, after the write and before
the commit, so the example's `.pyfr-answers.yml` records the released
version in the bump commit. Between releases the two versions are equal by
construction, and `tests/test_generation.py` fails the pull request that
edits one by hand; `cz bump --check-consistency` in `release.yml` refuses
to release if they have drifted anyway. A generated project's
`_template_version` is therefore the tag its template body was released
under — what M8 will read to bring it up to date.
```

In the spec, section 4.4, after the paragraph ending "the same pattern that already promotes the contract baseline in that commit." add:

```markdown
*Amended in PR 5.* `cz bump` writes the version files and commits in one
command, so no workflow step can sit between the two. The step is
Commitizen's `pre_bump_hooks` (`["just regen"]` in `pyproject.toml`), which
runs after `version_files` are written and before the bump commit; the
workflow's own `just regen` line went, and `cz bump` is passed
`--check-consistency` so a version it cannot find in `cookiecutter.json`
fails the release. `tests/test_release_bump.py` proves the order.
```

Run: `just lint && uv run --group dev pytest tests/ -q` — Expected: clean; all fast tests pass.

```bash
git add cookiecutter.json pyproject.toml .github/workflows/release.yml tests/test_generation.py tests/test_release_bump.py docs/contributing.md docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md examples/reference-service/.pyfr-answers.yml
git commit -m "feat: record the released template version in every generated project

cz bump now writes cookiecutter.json's _template_version beside
pyproject.toml's version and regenerates the example as its pre-bump
hook, so the bump commit carries both (spec section 4.4). The template
version is set to the repository's current version so the next bump
finds it.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: The generator refuses a port the project's own stack binds

**Files:**
- Modify: `hooks/pre_gen_project.py` (constants after `HTTP_PORT`, line 30; `problems()`, the port branch at lines 96–104)
- Modify: `tests/test_hooks.py` (the parametrised cases, lines 34–56; a new test after `test_free_text_may_contain_apostrophes_and_non_ascii`)
- Modify: `tests/test_generation.py` (the two `9000` tests, lines 167–195)
- Modify: `docs/getting-started.md` (the `http_port` row, line 50)
- Modify: `{{cookiecutter.project_slug}}/justfile` (the `docs` recipe's comment, lines 277–278)
- Regenerate: `examples/reference-service/justfile`

**Interfaces:**
- Consumes: Verified Fact 5 (the ports); Task 1's combinations use `9100` and `8090`, both free.
- Produces: the refusal sentence `http_port <port> is taken by <what>; the service could not run beside its own stack.`

- [ ] **Step 1: Write the failing tests**

In `tests/test_hooks.py`, inside the `parametrize` list of `test_bad_answers_are_rejected_before_anything_is_written`, after the `"08000"` case, add:

```python
        # Ports the generated stack binds on the host (compose.yaml and
        # `just docs`): always, and per chosen backend -- the defaults
        # choose every backend.
        ({"http_port": "8001"}, "documentation preview"),
        ({"http_port": "9099"}, "payment stub"),
        ({"http_port": "3000"}, "Grafana"),
        ({"http_port": "5432"}, "PostgreSQL"),
        ({"http_port": "6379"}, "Redis"),
        ({"http_port": "9000"}, "MinIO"),
        ({"http_port": "9001"}, "MinIO console"),
```

After `test_free_text_may_contain_apostrophes_and_non_ascii`, add:

```python
def test_a_backend_port_is_free_when_the_backend_is_absent(cookies) -> None:
    # MinIO's 9000 is refused only when MinIO is in the stack; a project
    # without object storage may listen there.
    result = cookies.bake(extra_context={"http_port": "9000", "object_storage": "none"})
    assert result.exit_code == 0, result.exception
    assert '"9000:9000"' in (result.project_path / "compose.yaml").read_text()
```

In `tests/test_generation.py`, change every `9000` in `test_a_custom_port_reaches_every_place_the_port_lives` and `test_the_docs_carry_the_chosen_port` to `9100` — every occurrence in those two tests, eight string literals: the `extra_context`, `EXPOSE 9100`, `"9100:9100"`, `APP_HTTP_PORT=9100`, `default=9100`, `== 9100`, the `render(cookies, http_port="9100")` call, and `"| `9100` |"`. Add one line above the first of the two: `# 9100: no template file mentions it, and nothing in the stack binds it.`

Run: `uv run --group dev pytest tests/test_hooks.py -q`
Expected: the seven new refusal cases fail (the render succeeds instead of exiting 1); the rest pass.

- [ ] **Step 2: Implement the rule**

In `hooks/pre_gen_project.py`, after `HTTP_PORT = json.loads(...)` (line 30, inside the `# fmt: off` block), add:

```python
DATABASE = json.loads(r'''{{ cookiecutter.database | tojson }}''')
CACHE = json.loads(r'''{{ cookiecutter.cache | tojson }}''')
OBJECT_STORAGE = json.loads(r'''{{ cookiecutter.object_storage | tojson }}''')
```

After `MAX_PACKAGE_NAME_LENGTH = 25`, add:

```python
# Host ports the generated project's own tooling binds -- compose.yaml's
# services and the documentation preview. A service told to listen on one
# of them could never run beside its own stack, and the collision would
# surface as a failed `just up`, long after generation. Keys are the
# answer's own spelling: a plain decimal string, checked below before this
# table is consulted.
RESERVED_PORTS = {
    "8001": "the documentation preview (`just docs`)",
    "9099": "the payment stub (compose.yaml)",
    "3000": "Grafana (compose.yaml, the o11y profile)",
    "4317": "the OTLP gRPC collector (compose.yaml, the o11y profile)",
    "4318": "the OTLP HTTP collector (compose.yaml, the o11y profile)",
    "9090": "Prometheus (compose.yaml, the o11y profile)",
}
# Bound only while the backend is in the stack; a project without it may
# use the port.
BACKEND_PORTS = {
    "postgres": {"5432": "PostgreSQL (compose.yaml)"},
    "redis": {"6379": "Redis (compose.yaml)"},
    "s3": {
        "9000": "MinIO (compose.yaml)",
        "9001": "the MinIO console (compose.yaml)",
    },
}
```

In `problems()`, replace

```python
    elif not 1 <= int(HTTP_PORT) <= 65535:
        found.append(f"http_port {HTTP_PORT} is outside 1-65535.")
    return found
```

with

```python
    elif not 1 <= int(HTTP_PORT) <= 65535:
        found.append(f"http_port {HTTP_PORT} is outside 1-65535.")
    else:
        reserved = dict(RESERVED_PORTS)
        for backend in (DATABASE, CACHE, OBJECT_STORAGE):
            reserved.update(BACKEND_PORTS.get(backend, {}))
        if HTTP_PORT in reserved:
            found.append(
                f"http_port {HTTP_PORT} is taken by {reserved[HTTP_PORT]}; "
                "the service could not run beside its own stack."
            )
    return found
```

Run: `uv run --group dev pytest tests/test_hooks.py tests/test_generation.py -q`
Expected: all pass. Run `just lint` — Expected: clean (the file is still plain Python before rendering).

- [ ] **Step 3: The prompt table and the recipe comment**

In `docs/getting-started.md`, change the `http_port` row's second cell from

`The port the service listens on: in `just dev`, in the compose stack and in the container image. A plain decimal integer between 1 and 65535.`

to

`The port the service listens on: in `just dev`, in the compose stack and in the container image. A plain decimal integer between 1 and 65535, and not one the project's own stack binds — 8001 (`just docs`), 9099 (the payment stub), 3000, 4317, 4318 and 9090 (the observability profile), nor 5432, 6379, 9000 or 9001 while PostgreSQL, Redis or MinIO is chosen; the generator refuses those and says which service has the port.`

Set the page's `last_reviewed` to `2026-09-14`.

In `{{cookiecutter.project_slug}}/justfile`, replace lines 277–278

```just
# Serve a live preview on http://127.0.0.1:8001, rebuilding on save. One
# above the service's default port, so `just dev` and this can run together.
```

with

```just
# Serve a live preview on http://127.0.0.1:8001, rebuilding on save. Not the
# service's port ({{ cookiecutter.http_port }}), so `just dev` and this can
# run together; PyFr refuses 8001 as an `http_port` answer for that reason.
```

Run: `just regen` — Expected: only `examples/reference-service/justfile` changes (the comment reads `(8000)` there). Run `cd examples/reference-service && git add -A && just check` — Expected: clean (`just --list` still parses the comment).

- [ ] **Step 4: Commit**

Run: `uv run --group dev pytest tests/ -q` — Expected: all fast tests pass.

```bash
git add hooks/pre_gen_project.py tests/test_hooks.py tests/test_generation.py docs/getting-started.md '{{cookiecutter.project_slug}}/justfile' examples/reference-service/justfile
git commit -m "feat: refuse an http_port the generated stack itself binds

8001 (just docs), the payment stub and the observability profile always;
PostgreSQL, Redis and MinIO's ports while that backend is chosen. The
collision used to surface as a failed just up, long after generation.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: Every page is in its site's nav

**Files:**
- Create: `tests/test_site_nav.py`

**Interfaces:**
- Consumes: `cookies` (pytest-cookies), `PYFR_REGEN` (Verified Fact 6), Verified Fact 8.
- Produces: `pages_missing_from_nav(root: Path) -> list[str]` — for a directory holding `mkdocs.yml` and `docs/`, the pages under `docs/` (relative, posix) that no nav entry names, excluding the sanctioned non-pages.

- [ ] **Step 1: Write the tests and the helper**

Create `tests/test_site_nav.py`:

```python
"""Every page in a docs/ tree is reachable from its site's nav.

`mkdocs build --strict` fails on a nav entry whose page is missing, but a
page that exists and is in no nav is one INFO line nobody reads: it
builds, it is published, and nothing links to it. Both sites get the
check, and so does a render with every backend off, whose nav has lost
the pruned decision records and must have lost nothing else.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "reference-service"
# Not pages: the design archive (the root mkdocs.yml excludes it from the
# build) and the decision-record template, copied and never read on the
# site.
NOT_PAGES = ("superpowers/", "adr/template.md")


class Loader(yaml.SafeLoader):
    """Tolerates the `!ENV [NAME, default]` tag MkDocs resolves itself."""


def env_default(loader: Loader, node: yaml.SequenceNode) -> object:
    return loader.construct_sequence(node)[-1]


Loader.add_constructor("!ENV", env_default)


def nav_pages(mkdocs_yml: Path) -> set[str]:
    pages: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and node.endswith(".md"):
            pages.add(node)

    walk(yaml.load(mkdocs_yml.read_text(), Loader=Loader)["nav"])
    return pages


def pages_missing_from_nav(root: Path) -> list[str]:
    docs = root / "docs"
    on_disk = {path.relative_to(docs).as_posix() for path in docs.rglob("*.md")}
    return sorted(
        page
        for page in on_disk - nav_pages(root / "mkdocs.yml")
        if not page.startswith(NOT_PAGES)
    )


def test_pyfr_site_lists_every_page() -> None:
    assert pages_missing_from_nav(ROOT) == []


def test_the_reference_service_site_lists_every_page() -> None:
    assert pages_missing_from_nav(EXAMPLE) == []


def test_a_render_with_every_backend_off_lists_every_page(
    cookies, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYFR_REGEN", "1")
    result = cookies.bake(
        extra_context={"database": "none", "cache": "none", "object_storage": "none"}
    )
    assert result.exit_code == 0, result.exception
    assert pages_missing_from_nav(result.project_path) == []


def test_the_helper_names_an_orphan(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# Home\n")
    (tmp_path / "docs" / "lost.md").write_text("# Lost\n")
    (tmp_path / "mkdocs.yml").write_text(
        "site_name: x\nrepo_url: !ENV [REPO_URL, https://example.com]\n"
        "nav:\n  - Home: index.md\n"
    )
    assert pages_missing_from_nav(tmp_path) == ["lost.md"]
```

- [ ] **Step 2: Run them**

Run: `uv run --group dev pytest tests/test_site_nav.py -q`
Expected: `4 passed` (Verified Fact 8: nothing is missing today; the fourth test proves the helper would notice).

- [ ] **Step 3: Lint and commit**

Run: `just lint` — Expected: clean.

```bash
git add tests/test_site_nav.py
git commit -m "test: fail on a documentation page that no nav entry reaches

A strict build catches a nav entry without a page; the other direction
was an INFO line. Both sites and an everything-off render are checked.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: Project-perspective wording in the template

**Files:**
- Modify: `{{cookiecutter.project_slug}}/README.md` (the `{%- else %}` branch of the `just up` paragraph, lines 84–88)
- Modify: `{{cookiecutter.project_slug}}/docs/getting-started.md` (the `{%- else %}` branch, lines 64–67; `last_reviewed`)
- Modify: `{{cookiecutter.project_slug}}/docs/adr/README.md` (the second paragraph, lines 12–14; `last_reviewed`)
- Modify: `cookiecutter.json` (`description`, line 5)
- Modify: `docs/getting-started.md` (the `description` row, line 43)
- Regenerate: `examples/reference-service/README.md`, `docs/getting-started.md`, `docs/adr/README.md`

**Interfaces:**
- Consumes: the `{%- set %}` phrase-variable form (Global Constraints).
- Produces: nothing later tasks use.

- [ ] **Step 1: The enumeration in the README**

In `{{cookiecutter.project_slug}}/README.md`, replace

```markdown
{%- else %}

`just up` is the containerized alternative: one command builds the service
image, starts whichever backends this project has and a payment stub, and
starts the API.
```

with

```markdown
{%- else %}
{%- set _services = (["PostgreSQL"] if cookiecutter.database == "postgres" else []) + (["Redis"] if cookiecutter.cache == "redis" else []) + (["MinIO"] if cookiecutter.object_storage == "s3" else []) + ["a payment stub"] %}
{%- set _started = ((_services[:-1] | join(", ")) ~ " and " ~ _services[-1]) if _services | length > 1 else _services[0] %}

`just up` is the containerized alternative: one command builds the service
image, starts {{ _started }}, and starts the API.
```

The two `{%- set %}` lines sit directly under `{%- else %}`; each strips the newline before it, and the blank line after the second one is the paragraph's separator, exactly as the blank line after `{%- else %}` was.

- [ ] **Step 2: The same sentence in getting-started**

In `{{cookiecutter.project_slug}}/docs/getting-started.md`, replace

```markdown
{%- else %}

That builds the service image, starts whichever backends this project has
and a payment stub, and starts the API. Once the API reports healthy, a
```

with

```markdown
{%- else %}
{%- set _services = (["PostgreSQL"] if cookiecutter.database == "postgres" else []) + (["Redis"] if cookiecutter.cache == "redis" else []) + (["MinIO"] if cookiecutter.object_storage == "s3" else []) + ["a payment stub"] %}
{%- set _started = ((_services[:-1] | join(", ")) ~ " and " ~ _services[-1]) if _services | length > 1 else _services[0] %}

That builds the service image, starts {{ _started }}, and starts the API.
Once the API reports healthy, a
```

Keep the `{%- endif %}` and the `one-shot `seed` container…` line after it as they are. Set the page's `last_reviewed` to `2026-09-14`.

- [ ] **Step 3: The decision-record index**

In `{{cookiecutter.project_slug}}/docs/adr/README.md`, replace

```markdown
Records 1 to 12 were backfilled after M0 to M4 already existed, and describe
decisions taken during that work. They are dated to the milestone that made
each decision rather than to the day the record itself was written.
```

with

```markdown
The records were written while PyFr's reference service — the service this
project was generated from — was being built, and records 1 to 12 were
backfilled after the work they describe. The "Decided" column names the
PyFr milestone (M0, M1, …) that made each decision — PyFr's
[roadmap](https://emadmokhtar.github.io/pyfr/roadmap/) says what each
milestone built — and a record is dated to that milestone rather than to
the day it was written.
```

Set `last_reviewed` to `2026-09-14`.

- [ ] **Step 4: The default description**

In `cookiecutter.json`, change `"description": "A Python microservice generated from PyFr.",` to `"description": "A Python microservice.",` — the README renders it followed by "Generated from [PyFr](…)", so the old default said it twice. In `docs/getting-started.md`, change the `description` row's default cell from `` `A Python microservice generated from PyFr.` `` to `` `A Python microservice.` ``.

- [ ] **Step 5: Render every combination, regenerate, check**

Run: `uv run --group dev pytest tests/test_generation.py -q` — Expected: every test passes (no Jinja survives any combination; the roadmap link is one of the two PyFr URLs the identity sweep allows; both extreme renders still build strict).

Render the three enumerations by eye:

```bash
for c in "database=none cache=none object_storage=none" "database=postgres cache=none object_storage=none" "database=postgres cache=redis object_storage=none"; do d=$(mktemp -d); PYFR_REGEN=1 uv run --group dev cookiecutter . --no-input --default-config --output-dir "$d" $c >/dev/null && grep -h "one command builds" -A1 "$d/my-service/README.md"; rm -rf "$d"; done
```

Expected, in order: `starts a payment stub, and starts the API.` / `starts PostgreSQL and a payment stub, and` / `starts PostgreSQL, Redis and a payment stub, and`.

Run: `just regen` — Expected changes: `examples/reference-service/docs/getting-started.md` (its front-matter date only — the example is everything on, and that branch of the sentence did not change; the same holds for its `README.md`, which must not change at all) and `examples/reference-service/docs/adr/README.md`. Then `cd examples/reference-service && git add -A && just docs-build` — Expected: the site builds strict. At the root, `just docs-build` — Expected: both sites build; `Every cross-site link resolves in the built site; every repository link names a path in the checkout.`

- [ ] **Step 6: Commit**

```bash
git add cookiecutter.json docs/getting-started.md '{{cookiecutter.project_slug}}/README.md' '{{cookiecutter.project_slug}}/docs/getting-started.md' '{{cookiecutter.project_slug}}/docs/adr/README.md' examples/reference-service/docs/getting-started.md examples/reference-service/docs/adr/README.md
git commit -m "docs(template): name the project's own backends instead of PyFr's

The README and getting-started page enumerate what just up starts, the
decision-record index explains PyFr's milestones to a reader who has
never seen them, and the default description no longer says generated
from PyFr twice.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: M7 is done

**Files:**
- Modify: `docs/roadmap.md` (line 11; the M7 row, line 26; `last_reviewed`)
- Modify: `README.md` (the status badge, line 13; the section "🚧 Honest status…", lines 36–62)
- Modify: `docs/index.md` (the admonition, lines 19–40; `last_reviewed`)
- Modify: `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md` (section 1 item 6, lines 37–38; section 11, lines 457–460; section 12 row 5, line 478)

**Interfaces:**
- Consumes: Tasks 1–6 complete (the claims below must be true).
- Produces: nothing.

- [ ] **Step 1: The roadmap**

In `docs/roadmap.md`, replace line 11

`**M0, M1, M2, M3, M4, M5 and M6 are done; M7 is in progress.** Everything on this site describes code that exists today.`

with

`**M0, M1, M2, M3, M4, M5, M6 and M7 are done; M8 is next.** Everything on this site describes code that exists today.`

In the M7 row, change the State cell `**In progress**` to `**Done**`, and replace the row's last two sentences — `Still to come: the full-suite tests. **PyFr becomes a usable template at the end of M7.**` — with:

`The fifth added the full-suite tests — three combinations rendered for real, synced, committed and run through their own `just check-all` on every merge to `main` and nightly — wired `_template_version` to the release, so every generated project records the template version it came from, and made the generator refuse a port the project's own stack binds. **PyFr is a usable template: `uvx cookiecutter gh:EmadMokhtar/pyfr` produces a project whose `just check` passes.**`

Set `last_reviewed` to the day of the edit.

- [ ] **Step 2: The README**

Replace the badge line 13

`[![Status: pre-release](https://img.shields.io/badge/status-building%20toward%20M7-orange)](https://emadmokhtar.github.io/pyfr/roadmap/)`

with

`[![Status: usable template](https://img.shields.io/badge/status-usable%20template-brightgreen)](https://emadmokhtar.github.io/pyfr/roadmap/)`

Replace the section from `## 🚧 Honest status: M0–M6 done, M7 in progress, M8 to go` through the paragraph ending `for what ships when.` (lines 36–62) with:

```markdown
## ✅ Status: M0–M7 done, M8 to go

**The template is usable** — `uvx cookiecutter gh:EmadMokhtar/pyfr`
generates a project whose `just check` passes, for every combination of
backends. M7, the conversion into a template, is complete: the template
renders from twelve prompts, prunes the backends you do not choose, gives
a generated project its own workflows and its own documentation site
about itself, and records the template version it came from. On every
merge to `main` and every night, three combinations are generated for
real and run through their own `just check-all` — see the
[roadmap](https://emadmokhtar.github.io/pyfr/roadmap/).
The [**reference service**](examples/reference-service/) is rendered from
that template; it is the complete, running service you can run, read, and
copy from right now.

PyFr is built in three phases:

| Phase | Milestones | What happens |
| --- | --- | --- |
| **A** | M0–M6 | Build the reference service as ordinary Python — no template placeholders anywhere |
| **B** | M7 | Convert it into the cookiecutter template ✨ |
| **C** | M8+ | Keep the two in step, forever |

The rule behind that order: never debug Jinja and Python at the same time. 🙂

**M0 through M7 — the reference service and its conversion into a
template — are complete. M8, template updates for generated projects, is
next.** See the [roadmap](https://emadmokhtar.github.io/pyfr/roadmap/)
for what ships when.
```

- [ ] **Step 3: The site's front page**

In `docs/index.md`, replace the admonition (from `!!! warning "Status: M0–M6 done, M7 in progress, M8 to go"` through the line ending `language cookiecutter uses.)`, lines 19–40) with:

```markdown
!!! note "Status: M0–M7 done, M8 to go"

    **The template is usable.** `{{cookiecutter.project_slug}}/` is the
    template body and the source of truth: the *reference service* —
    [`examples/reference-service/`](https://github.com/EmadMokhtar/pyfr/tree/main/examples/reference-service)
    — is rendered from it and never edited by hand.

    M7, the conversion into a template, is complete. The template renders
    from twelve prompts; it prunes the backends you do not choose; a
    generated project carries its own continuous-integration, nightly,
    release and documentation workflows, ships its own documentation site
    about itself, and records the template version it came from; and on
    every merge to `main` and every night, three combinations are
    generated for real and run through their own `just check-all`. M8 —
    template updates for generated projects — is next.

    PyFr is built in three phases. Phase A (milestones M0 to M6) built that
    service as ordinary Python, with no template placeholders anywhere.
    Phase B (M7) converted it into the template. Phase C keeps the two in
    step forever after. The reason is stated plainly in the design: never
    debug Jinja and Python at the same time. (Jinja is the placeholder
    language cookiecutter uses.)
```

Set `last_reviewed` to the day of the edit.

- [ ] **Step 4: The spec's version numbers**

In the spec, section 1 item 6, replace

```markdown
6. The roadmap marks M7 done and the release is `v0.7.0`, which is also the
   `_template_version` every generated project records.
```

with

```markdown
6. The roadmap marks M7 done, and the release that closes M7 is also the
   `_template_version` every generated project records. *(Amended in
   PR 5: this said `v0.7.0`; the milestone took four releases, `v0.6.0`
   to `v0.9.0`, before its fifth pull request, and Commitizen numbers the
   closing one.)*
```

In section 11, replace

```markdown
One tag series, as today: `v0.7.0` is "M7 done" and is the
`_template_version` a project generated from it records. A generated
project's version is its own.
```

with

```markdown
One tag series, as today: the release that closes M7 is "M7 done" and is
the `_template_version` a project generated from it records (`v0.7.0`
when this was written; amended in PR 5). A generated project's version is
its own.
```

In section 12 row 5, replace `` roadmap **Done**; README status; `v0.7.0`. `` with `` roadmap **Done**; README status; the closing release (`v0.7.0` when this was written). ``.

- [ ] **Step 5: Build, check, commit**

Run: `just check` at the root — Expected: both sites build strict, the cross-site links resolve, every fast test passes (`… deselected` for the three full-suite tests), the golden diff is clean.

Run: `just docs-freshness origin/main HEAD` — Expected: warnings only for pages this branch changed whose `last_reviewed` was not updated; none should remain.

```bash
git add docs/roadmap.md README.md docs/index.md docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md
git commit -m "docs: mark m7 done and name the release that closes it

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

## Self-review

**Spec coverage.** Section 10.3 (three combinations, no `PYFR_REGEN`, the project's gates, marked and deselected) → Task 1. Section 11 (`full-suite.yml`: push to `main`, nightly, on demand) → Task 2. Section 4.4 and definition-of-done item 6 (`_template_version` moved by the release; `.pyfr-answers.yml` carries it) → Task 3; the amendment records why the mechanism is a hook. Section 5.2's port rule is extended, not changed → Task 4. Section 13's "Full-suite test" row (the gate's output; the combination in the test id) → Task 1's uncaptured `subprocess.run` and the `params` ids. Section 12 row 5's "ADR 0017" shipped in PR 4 (`docs/adr/0017-…`), nothing to do. Roadmap **Done** and README status → Task 7. Items PR 4 handed over: identity-varying render (Task 1's combinations), orphan pages (Task 5), reserved ports (Task 4), wordings (Task 6), the `uv --only-group` and ADR 0016 items (rulings above).

**Placeholder scan.** Every code step carries its code; the one "temporarily comment out" instruction in Task 3 Step 6 names the exact line and the exact expected failure.

**Type consistency.** `COMBINATIONS: dict[str, dict[str, str]]` (Task 1) ↔ `regen.load_answers() -> dict[str, str]`; the ids `everything-on` / `everything-off` / `postgres-only` appear identically in Task 1's dict, its recipe comment, Task 2's matrix and the contributing page; `TEMPLATE_VERSION: str` (Task 3) is compared to strings read from YAML and JSON; `pages_missing_from_nav(root: Path) -> list[str]` (Task 5) is called with `ROOT`, `EXAMPLE` and `result.project_path`, all `Path`.

## Handoff notes for the pull request

- **Branch:** `claude/m7-pr5-full-suite`, from `origin/main` at `8b25ebc` (v0.9.0).
- **Issue first** (memory: link every PR to an issue): `gh issue create --title "M7 PR 5: full-suite tests, the template version, and M7 done" --body "..." --assignee EmadMokhtar`, then reference it with `Closes #<n>` in the PR body and verify `gh pr view <pr> --json closingIssuesReferences`.
- **PR title:** `feat: prove a generated project passes its own gates and close m7 (m7 pr 5)` — a `feat:` so that merging cuts the release that closes M7 (Ruling 3). Assign with `--assignee EmadMokhtar` (bare login) and verify with `gh pr view --json assignees`.
- **One-time hazard at merge time:** `cookiecutter.json` says `0.9.0`, the version on `main` today. If another release lands on `main` before this PR merges, rebase and set `_template_version` to the new `[project].version` (Task 3 Step 3); `tests/test_generation.py::test_the_template_version_is_the_repository_version` goes red on `main` otherwise, and the release's `--check-consistency` refuses to run. Once this PR is in, the bump keeps them equal without anyone's help.
- **After the merge:** the release run should show `Running hook 'just regen'` inside the bump step, a bump commit that touches `cookiecutter.json`, `examples/reference-service/.pyfr-answers.yml` and the two baselines, and a tag `v0.10.0` (or whatever Commitizen chooses); `Full suite` runs three jobs on the merge commit — the first real run of the workflow. Confirm all three pass; a failure there is the first item of the next session.
