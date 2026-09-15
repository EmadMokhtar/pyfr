# PyFr M8 PR 1 — `pyfr-cli` Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship `pyfr-cli` — a Python package published to PyPI from this repository, exposing `pyfr update` and `pyfr update-check` — so a project generated from the template can pull in a later template version through a git merge.

**Architecture:** A `src/pyfr_cli/` package beside `hooks/`, `scripts/` and `tests/`, outside the template body, so cookiecutter never renders it. Ten small modules, each with one job (git wrapper, answers file, versions, render, ignore list, vendor branch, migrations, changelog, state, orchestration) and an argparse entry point. The root `pyproject.toml` becomes a real package built by hatchling; the release workflow publishes the wheel to PyPI with `uv publish` under Trusted Publishing. Nothing under `{{cookiecutter.project_slug}}/` changes in this PR — PR 2 adds the generated side.

**Tech Stack:** Python 3.13, argparse, `cookiecutter>=2.6,<3`, `pyyaml>=6.0`, `pathspec>=0.12`, hatchling, `uv build` / `uv publish`, mypy `--strict`, ruff, pytest.

**Spec:** [`docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md`](../specs/2026-09-14-pyfr-m8-template-updates-design.md) — this PR implements sections 3 (the package), 4 (the update algorithm), 6 (the migration-script contract, runner side), 8.1, 8.2 and 8.4 (unit, end-to-end and packaging tests), and the `publish-pypi` job of 3.5. Section 9 lists it as PR 1.

## Global Constraints

- `requires-python = ">=3.13"`; `target-version = "py313"` in ruff; `.python-version` is `3.13`.
- Distribution name `pyfr-cli`, command `pyfr`, import name `pyfr_cli` (spec M8-2). The version is `[project].version`, moved only by `cz bump`; never edit it by hand.
- Runtime dependencies are exactly `cookiecutter>=2.6,<3`, `pyyaml>=6.0`, `pathspec>=0.12` (spec 3.3). No CLI framework: argparse.
- The tool never prompts (spec M8-6). Every error is an `UpdateError(cause, fix)` printed as two lines on stderr, exit 2; exit 1 means the user must act (a merge is waiting); exit 0 means done or already current (spec 3.2).
- Every git call goes through `pyfr_cli.git.Git.run`; argument lists are fixed literals or paths the tool computed.
- The tool's own commits pass `--no-verify`: the `template` worktree shares `.git/hooks`, where the generator installed pre-commit, and the project's hooks must not run against the pristine template in a directory that has no environment. CI runs the gates on the pull request.
- Comments and messages in simple, direct English; Conventional Commits for every commit (`feat(pyfr-cli): …`, `test(pyfr-cli): …`, `build: …`, `ci: …`, `docs: …`).
- `just lint`, `just typecheck` and `just test` must pass after every task. Run from the repository root.
- The plan's code blocks are written for reading; ruff's formatter has the final say on layout. Run `uv run --group dev ruff format .` before `just lint` in every task, and keep whatever it produces (an import line longer than 88 columns becomes a parenthesised multi-line import, for example).
- Test files under `tests/cli/` (a package with `__init__.py`), not `tests/pyfr_cli/` as the spec's 8.1 says: pytest would import `tests/pyfr_cli/test_x.py` as module `pyfr_cli.test_x`, colliding with the real package. Shared test helpers live in `tests/cli/helpers.py` and are imported as `from cli.helpers import …` (pytest puts `tests/` on `sys.path`).

## Verified facts (checked on 2026-09-14 in this checkout)

- cookiecutter 2.7.1: `cookiecutter(template, checkout=None, no_input=False, extra_context=None, …, output_dir='.', …, default_config=False, …) -> str` returns the rendered project path. `extra_context` keys the template does not declare are ignored; a value outside a choice list raises `ValueError("mysql provided for choice variable db, but the choices are ['postgres', 'none'].")`.
- pathspec 1.1.1 is already in `uv.lock` (transitively); `pathspec.GitIgnoreSpec.from_lines(lines).match_file("docs/adr/x.md")` is the API.
- `git ls-remote --tags <repo>` prints `<sha>\trefs/tags/<name>`; an annotated tag adds a `<name>^{}` line. Works on a local path.
- `git clone --depth 1 --branch <tag> <local path>` warns "--depth is ignored in local clones" on stderr and succeeds.
- Both sides renaming the same file to the same path merge cleanly, three-way against the old content (probed: the team's edit survived the rename).
- **Squash merges break the natural merge base.** After an update pull request is squash-merged, `git merge template` uses the root commit as its base and re-conflicts every hunk the team resolved last time — even with `origin/template` present. `git replace --graft <HEAD> <HEAD's parents…> <T_prev>` (a temporary extra parent) makes `git merge-base` return `T_prev`, the merge is clean, the merge commit's parents are the real `HEAD` and the template commit, and `git replace -d <HEAD>` leaves no trace. Probed end to end. Task 1 amends spec 4.7 with this.
- Adjacent changed lines merge as one hunk: an end-to-end fixture must edit lines at least a few lines apart to be clean.
- `CHANGELOG.md` headings are `## v0.10.0 (2026-09-14)` (Commitizen).
- The template body's `pyproject.toml` has `dependencies = [` on its own line; `tests/unit/test_order_repository.py`, `tests/integration/test_order_repository.py`, `lychee.toml`, `.trivyignore.yaml`, `ruff.toml` exist in the body (ruff.toml has one Jinja expression, in `known-first-party`).
- The root CI's root-level gates run in the `docs` job of `.github/workflows/ci.yml` via `just check`; `just check` is `docs-build test regen-check`. Root `just test` is `uv run --group dev --group docs pytest tests/`.
- The root `release.yml`'s `release` job outputs `version` (bare, no `v`) only when a tag was settled on; `publish-images` gates on `needs.release.outputs.publish == 'true'`.
- `tests/test_release_bump.py` drives a real `cz bump` on a copy of `pyproject.toml`, `uv.lock` and `cookiecutter.json` — it must still pass after the package rename (`version_provider = "uv"` looks the lock's package up by `[project].name`).
- Root ruff: `select = ["E","W","F","I","B","S","UP","ASYNC","RUF"]`, line length 88; `S603`/`S607` are ignored per directory for subprocess with literal arguments.

## File structure

| Path | Responsibility |
|---|---|
| `pyproject.toml` | Becomes the `pyfr-cli` package: name, dependencies, console script, hatchling, mypy config. |
| `ruff.toml` | Adds `src/` and the test package to first-party and the subprocess ignores. |
| `justfile` | `typecheck`, `wheel`; `check` runs `typecheck`. |
| `src/pyfr_cli/__init__.py` | `__version__`. |
| `src/pyfr_cli/errors.py` | `UpdateError(cause, fix)`. |
| `src/pyfr_cli/git.py` | `Git` wrapper and the queries the tool needs; `require_tools`. |
| `src/pyfr_cli/versions.py` | `Version`, tag parsing, target resolution. |
| `src/pyfr_cli/answers.py` | Read `.pyfr-answers.yml`; build cookiecutter's context; install the rendered file. |
| `src/pyfr_cli/state.py` | `.git/pyfr-update.json`. |
| `src/pyfr_cli/ignore.py` | The built-in default list and gitignore matching. |
| `src/pyfr_cli/changelog.py` | The `(A, B]` sections of a Commitizen changelog. |
| `src/pyfr_cli/render.py` | Shallow clone at a tag; render with `PYFR_REGEN=1`. |
| `src/pyfr_cli/vendor.py` | The `template` branch: find, guard, sync, commit, push; the commit for a version. |
| `src/pyfr_cli/migrate.py` | `updates/<version>/before.py` and `after.py`. |
| `src/pyfr_cli/update.py` | `check()` and `update()` — spec section 4 in order. |
| `src/pyfr_cli/__main__.py` | argparse; exit codes. |
| `updates/README.md` | The migration-script contract for contributors (spec 6). |
| `tests/cli/__init__.py`, `tests/cli/helpers.py`, `tests/cli/conftest.py` | Test package, git helpers, git isolation. |
| `tests/cli/test_<module>.py` | One unit-test file per module. |
| `tests/test_update_e2e.py` | The end-to-end scenarios of spec 8.2. |
| `.github/workflows/ci.yml` | `just wheel` step in the `docs` job. |
| `.github/workflows/release.yml` | `publish-pypi` job. |
| `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md` | Three amendments (Task 1). |

---

### Task 1: Package skeleton — `pyproject.toml`, `pyfr --version`, spec amendments

**Files:**
- Modify: `pyproject.toml`
- Modify: `ruff.toml`
- Modify: `justfile`
- Create: `src/pyfr_cli/__init__.py`, `src/pyfr_cli/errors.py`, `src/pyfr_cli/__main__.py`
- Create: `tests/cli/__init__.py`, `tests/cli/test_main.py`
- Modify: `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md`

**Interfaces:**
- Produces: `pyfr_cli.__version__: str`; `pyfr_cli.errors.UpdateError(cause: str, fix: str)` with attributes `.cause`, `.fix`; `pyfr_cli.__main__.main(argv: Sequence[str] | None = None) -> int` (only `--version` works after this task; Task 11 wires the subcommands).

- [ ] **Step 1: Write the failing test**

Create `tests/cli/__init__.py` (empty) and `tests/cli/test_main.py`:

```python
"""The `pyfr` command: arguments, exit codes, error printing."""

from __future__ import annotations

import pytest

from pyfr_cli import __version__
from pyfr_cli.__main__ import main


def test_version_prints_the_package_version(
    capsys: pytest.CaptureFixture[str],
) -> None:
    with pytest.raises(SystemExit) as stop:
        main(["--version"])
    assert stop.value.code == 0
    assert capsys.readouterr().out.strip() == f"pyfr {__version__}"


def test_version_is_the_project_version() -> None:
    # importlib.metadata reads the installed distribution; uv installs the
    # project editable on every `uv run`, so this is pyproject.toml's value.
    assert __version__.count(".") == 2
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run --group dev pytest tests/cli/test_main.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli'`.

- [ ] **Step 3: Turn the root into the `pyfr-cli` package**

Replace the top of `pyproject.toml` — everything from the first line down to and including the `prerelease = "explicit"` line of `[tool.uv]` — with:

```toml
# The PyFr repository's own project: the documentation toolchain, the
# template's test suite, and -- since M8 -- the `pyfr-cli` package.
#
# PyFr v1 is a cookiecutter template (see docs/explanation/why-a-template.md).
# A generated service imports no PyFr package and has no runtime
# dependency on this repository (spec D1). What IS published, to PyPI, is
# `pyfr-cli`: the development-time tool a generated project runs through
# `uvx` to pull in a newer template version (M8 spec, section 3). It is
# built from src/pyfr_cli/ only; hooks/, scripts/, tests/ and the template
# body never enter the wheel.
#
# The reference service has its own, entirely separate `pyproject.toml` under
# examples/reference-service/. The two are never synced together.
[project]
name = "pyfr-cli"
version = "0.10.0"
description = "PyFr — a cookiecutter template for production-ready Python microservices, and the tool that keeps a generated project up to date with it"
readme = "README.md"
requires-python = ">=3.13"
license = { file = "LICENSE" }
dependencies = [
    # Renders the template at the target version inside `pyfr update`;
    # the same range the template's own tests render with.
    "cookiecutter>=2.6,<3",
    # .pyfr-answers.yml, the one file an update reads and rewrites.
    "pyyaml>=6.0",
    # .pyfr-update-ignore uses gitignore syntax; pathspec is the
    # pure-Python implementation of gitignore matching.
    "pathspec>=0.12",
]

[project.scripts]
pyfr = "pyfr_cli.__main__:main"

[build-system]
requires = ["hatchling>=1.27,<2"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/pyfr_cli"]

[tool.hatch.build.targets.sdist]
# The sdist is the wheel's source and nothing else: not the template body,
# not the example, not the tests.
only-include = ["src/pyfr_cli", "README.md", "LICENSE"]

[tool.uv]
# Never resolve to a pre-release unless a requirement names one; the same
# rule as the template's pyproject.toml, for the same reason (PR #32). No
# requirement here names one, so this lock holds no pre-releases at all.
prerelease = "explicit"

[tool.mypy]
# The published tool is type-checked strictly; nothing else at the root is
# (hooks/ and scripts/ are checked by their tests). `just typecheck`.
strict = true
python_version = "3.13"
files = ["src/pyfr_cli"]

[[tool.mypy.overrides]]
# cookiecutter ships no type information.
module = ["cookiecutter.*"]
ignore_missing_imports = true
```

The `[tool.commitizen]` section that follows stays exactly as it is.

In `[dependency-groups] dev`, remove the `pyyaml>=6.0.3` entry and its comment, and the `cookiecutter>=2.6,<3` entry and its comment (both are runtime dependencies now — `pytest-cookies` still pulls cookiecutter, and `regen.py`'s `import yaml` is satisfied by the project's own dependency). Add, after `pre-commit>=4.0`'s entry:

```toml
    # `just typecheck`: mypy --strict over src/pyfr_cli. types-pyyaml is
    # the stub package for pyyaml, which ships no type information.
    "mypy>=1.13",
    "types-pyyaml>=6.0",
```

- [ ] **Step 4: Create the package**

`src/pyfr_cli/__init__.py`:

```python
"""pyfr-cli: bring a project generated from PyFr up to a newer template version.

`pyfr update` re-renders the template at the target version with the answers
the project recorded, commits the result on the `template` branch, and merges
that branch in (M8 design, section 4). `pyfr update-check` says whether a
newer version exists.
"""

from __future__ import annotations

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("pyfr-cli")
except PackageNotFoundError:  # a checkout that was never installed
    __version__ = "0.0.0"
```

`src/pyfr_cli/errors.py`:

```python
"""The one error the command reports: a cause and a fix, one line each."""

from __future__ import annotations


class UpdateError(Exception):
    """Stops the run. `__main__` prints `cause` and `fix` and exits 2."""

    def __init__(self, cause: str, fix: str) -> None:
        super().__init__(cause)
        self.cause = cause
        self.fix = fix
```

`src/pyfr_cli/__main__.py` (the subcommands arrive in Task 11; `--version` is enough for the packaging to be real):

```python
"""The `pyfr` command."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence

from pyfr_cli import __version__
from pyfr_cli.errors import UpdateError


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfr",
        description="Keep a project generated from PyFr up to date with the template.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    parser.add_subparsers(dest="command", required=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        raise UpdateError(f"unknown command {args.command}", "run pyfr --help")
    except UpdateError as exc:
        if os.environ.get("PYFR_DEBUG"):
            raise
        print(f"error: {exc.cause}", file=sys.stderr)
        print(f"  fix: {exc.fix}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: ruff and just**

In `ruff.toml`: change `src = ["scripts", "tests"]` to `src = ["scripts", "tests", "src"]`; under `[lint.per-file-ignores]` add, after the `"hooks/*"` line:

```toml
# src/pyfr_cli shells out to git and uv the same way; every argument list
# is a fixed literal or a path the tool computed.
"src/*" = ["S603", "S607"]
```

and change `known-first-party = ["regen", "check_site_links"]` to `known-first-party = ["regen", "check_site_links", "pyfr_cli", "cli"]`.

In `justfile`: replace the `lint:` recipe and its comment with:

```
# ruff over the root's own Python -- hooks/, scripts/, src/, tests/ --
# then mypy over the published package. ruff.toml's extend-exclude keeps
# both out of the template body; the example is linted with its own
# ruff.toml, by its own `just lint`.
lint: typecheck
    uv run --group dev ruff check .
    uv run --group dev ruff format --check .

# mypy --strict over src/pyfr_cli, the one package this repository
# publishes (pyproject.toml's [tool.mypy] names the files).
typecheck:
    uv run --group dev mypy
```

and change the last line, `check: docs-build test regen-check`, to `check: docs-build typecheck test regen-check`.

- [ ] **Step 6: Lock, then run the tests**

Run: `uv lock && uv run --group dev pytest tests/cli/test_main.py -v`
Expected: both PASS; `uv.lock` now has a `[[package]] name = "pyfr-cli"` entry with `source = { editable = "." }`.

Run: `just lint && uv run --group dev pytest tests/test_release_bump.py -v`
Expected: PASS (the bump test copies the renamed `pyproject.toml` and `uv.lock`; Commitizen's uv provider finds the package by name).

- [ ] **Step 7: Amend the spec for what this task and the probes changed**

In `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md`:

1. Section 4.5, after the sentence ending "the trailer still records the version.", insert:

   > The commit passes `--no-verify`, as does every commit this tool makes: the worktree shares `.git/hooks`, where the generator installed pre-commit, and the project's hooks must not run against the pristine template in a directory that has no environment. CI runs the gates on the pull request.

2. Section 4.7, replace the opening code block and the paragraph after it (`git merge --no-ff --no-commit template` … "so the answers file can join the commit.") with:

   > **Pinning the merge base.** The base must be the template commit at the *recorded* version — call it `T_prev`: the root commit on a first update, otherwise the `template` commit whose trailer names the recorded version. Git would pick it by itself only if `T_prev` is in `HEAD`'s history, and after a squash-merged update pull request it is not: the squash discards the merge commit, `git merge-base` falls back to the root, and every hunk the team resolved last time conflicts again (verified in the PR 1 plan). So when `T_prev` is not an ancestor of `HEAD`, the tool adds it as a temporary extra parent — `git replace --graft HEAD <HEAD's parents> T_prev`, a replacement object under `refs/replace/` that changes how git reads the commit, not the commit itself — runs the merge, and deletes the graft. The merge commit's parents are the real `HEAD` and the template commit; nothing of the graft remains. This is what makes `origin/template` necessary: `T_prev` must exist somewhere.
   >
   > ```
   > git merge --no-ff --no-commit template
   > ```
   >
   > `--no-ff`: always a merge commit, never a fast-forward, even in a project that committed nothing since its root. `--no-commit`: stop before committing so the answers file can join the commit.

3. Section 4.3, in the paragraph beginning "**Why it lives on the remote.**", replace the last two sentences ("Rebuilding from the root would make … starts by fetching it.") with:

   > The pushed branch keeps that commit alive; section 4.7 says how the merge is told to use it. Every machine — a laptop, the weekly workflow's fresh checkout — starts by fetching it.

4. Section 4.3, the paragraph "**The branch's version** …": after "sections 4.4 and 4.5 are skipped" replace the rest of the sentence with: "— the render still runs, because step 10's answers file comes from it, but the sync, commit and push do not — a re-run after a conflicted merge, or a laptop picking up what the weekly workflow already pushed."

5. Section 5.2, the default list: replace the code block with comments on their own lines (gitignore syntax has no inline comments — a `#` after a pattern is part of the pattern):

   ```
   # Paths `just update` leaves exactly as this project has them: yours from
   # the first day, or artifacts of your code. Add paths as you diverge --
   # one gitignore pattern per line, comments on their own lines.
   # Everything not listed is template-owned and receives fixes by default.

   # Written by the update itself.
   .pyfr-answers.yml
   # This file.
   .pyfr-update-ignore
   README.md
   CHANGELOG.md
   # Resolver output; run `uv lock` after an update that touched pyproject.toml.
   uv.lock
   # Your schema.
   migrations/
   schema.sql
   # Artifacts of your code: the contract, and the baseline your release promotes.
   openapi.json
   openapi.baseline.json
   # Your decisions.
   docs/adr/
   # The example slice, then your business model.
   src/<package>/domain/
   src/<package>/services/
   src/<package>/api/v1/
   ```

   and change the sentence before it, "Gitignore syntax: blank lines and `#` comments are skipped, …" to "Gitignore syntax: blank lines and lines starting with `#` are skipped (a `#` after a pattern is part of the pattern, as in `.gitignore`), a trailing `/` names a directory and everything under it, `*` and `**` as in `.gitignore`, `!` negates."

6. Section 8.2, scenario 2: replace "because the base came from `origin/template`. This is decision M8-3's proof." with "because the merge base was pinned to the template commit at the recorded version, which `origin/template` keeps alive (section 4.7). This is the proof of decision M8-3 and of the pinned base."

- [ ] **Step 8: Commit**

```bash
git add pyproject.toml uv.lock ruff.toml justfile src/pyfr_cli tests/cli docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md
git commit -m "feat(pyfr-cli): add the package skeleton and pyfr --version

The root becomes the pyfr-cli package, built by hatchling from
src/pyfr_cli only. The spec gains the pinned merge base, the hook skip
and the own-line comment rule the probes made necessary.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 2: `versions.py` — tags as numbers

**Files:**
- Create: `src/pyfr_cli/versions.py`
- Test: `tests/cli/test_versions.py`

**Interfaces:**
- Produces: `Version(major, minor, patch)` — frozen, ordered dataclass; `Version.parse("v1.2.3" | "1.2.3") -> Version` (raises `ValueError`); `str(v) == "v1.2.3"`; `v.bare == "1.2.3"`. `parse_ls_remote(output: str) -> list[Version]` (release tags only, oldest first). `remote_versions(template: str, git: Git) -> list[Version]` (Task 3 supplies `Git`; this task writes the function but its test arrives in Task 3). `resolve_target(requested: str | None, available: list[Version]) -> Version`.

- [ ] **Step 1: Write the failing tests**

`tests/cli/test_versions.py`:

```python
"""Template versions: the vX.Y.Z tags, compared as numbers."""

from __future__ import annotations

import pytest

from pyfr_cli.errors import UpdateError
from pyfr_cli.versions import Version, parse_ls_remote, resolve_target

LS_REMOTE = """\
aaaa\trefs/tags/v0.10.0
bbbb\trefs/tags/v0.9.0
cccc\trefs/tags/v1.0.0-rc1
dddd\trefs/tags/latest
eeee\trefs/tags/v0.11.0
eeee\trefs/tags/v0.11.0^{}
ffff\trefs/tags/1.2.3
"""
AVAILABLE = [Version(0, 9, 0), Version(0, 10, 0), Version(0, 11, 0)]


def test_parse_accepts_the_v_and_its_absence() -> None:
    assert Version.parse("v1.2.3") == Version.parse("1.2.3") == Version(1, 2, 3)
    assert Version.parse(" v0.12.0\n") == Version(0, 12, 0)


@pytest.mark.parametrize("bad", ["1.2", "v1.2.3.4", "latest", "v1.0.0-rc1", ""])
def test_parse_rejects_other_shapes(bad: str) -> None:
    with pytest.raises(ValueError, match="not a version"):
        Version.parse(bad)


def test_str_carries_the_v_and_bare_does_not() -> None:
    version = Version(0, 12, 0)
    assert str(version) == "v0.12.0"
    assert version.bare == "0.12.0"


def test_versions_compare_as_numbers_not_text() -> None:
    assert Version(0, 9, 0) < Version(0, 10, 0) < Version(1, 0, 0)


def test_parse_ls_remote_keeps_release_tags_only_oldest_first() -> None:
    # v1.0.0-rc1, `latest` and a v-less 1.2.3 are not release tags; the
    # ^{} line of an annotated tag does not count twice.
    assert parse_ls_remote(LS_REMOTE) == AVAILABLE


def test_resolve_target_defaults_to_the_newest() -> None:
    assert resolve_target(None, AVAILABLE) == Version(0, 11, 0)


@pytest.mark.parametrize("requested", ["v0.10.0", "0.10.0"])
def test_resolve_target_accepts_to_with_or_without_the_v(requested: str) -> None:
    assert resolve_target(requested, AVAILABLE) == Version(0, 10, 0)


def test_resolve_target_refuses_an_unknown_tag_and_names_the_newest() -> None:
    with pytest.raises(UpdateError) as stop:
        resolve_target("v0.12.0", AVAILABLE)
    assert "no tag v0.12.0" in stop.value.cause
    assert "v0.11.0" in stop.value.fix


def test_resolve_target_refuses_garbage() -> None:
    with pytest.raises(UpdateError) as stop:
        resolve_target("latest", AVAILABLE)
    assert "not a version" in stop.value.cause
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --group dev pytest tests/cli/test_versions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli.versions'`.

- [ ] **Step 3: Implement**

`src/pyfr_cli/versions.py`:

```python
"""Template versions: the vX.Y.Z tags, compared as numbers, printed with the v."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyfr_cli.errors import UpdateError

if TYPE_CHECKING:
    from pyfr_cli.git import Git

# A release tag on the template repository. The v is required: a tag
# without it is not one Commitizen made for a release (spec section 4.2).
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
# What people type after --to, and what .pyfr-answers.yml records
# (cookiecutter.json holds the version without the v): the v is optional.
LENIENT = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
# `git ls-remote --tags` prints "<sha>\trefs/tags/<name>"; an annotated tag
# adds a second line for the commit it points at, whose name ends in ^{}.
REF = re.compile(r"^[0-9a-f]+\trefs/tags/(?P<name>[^\s^]+)$")


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> Version:
        match = LENIENT.match(text.strip())
        if match is None:
            raise ValueError(f"{text.strip()!r} is not a version like v0.12.0")
        major, minor, patch = (int(part) for part in match.groups())
        return cls(major, minor, patch)

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    @property
    def bare(self) -> str:
        """Without the v, as cookiecutter.json and PyPI carry it."""
        return f"{self.major}.{self.minor}.{self.patch}"


def parse_ls_remote(output: str) -> list[Version]:
    """Every release tag in `git ls-remote --tags` output, oldest first."""
    found: set[Version] = set()
    for line in output.splitlines():
        ref = REF.match(line)
        if ref is None:
            continue
        tag = TAG.match(ref["name"])
        if tag is None:
            continue
        major, minor, patch = (int(part) for part in tag.groups())
        found.add(Version(major, minor, patch))
    return sorted(found)


def remote_versions(template: str, git: Git) -> list[Version]:
    """The template's release tags, oldest first; never empty."""
    result = git.run("ls-remote", "--tags", template, check=False)
    if result.returncode != 0:
        raise UpdateError(
            f"could not list the tags of {template}: {result.stderr.strip()}",
            "check the _template URL in .pyfr-answers.yml (or --template), "
            "and that you are online",
        )
    found = parse_ls_remote(result.stdout)
    if not found:
        raise UpdateError(
            f"{template} has no release tags (vX.Y.Z)",
            "check the _template URL in .pyfr-answers.yml, or pass --template",
        )
    return found


def resolve_target(requested: str | None, available: list[Version]) -> Version:
    """The version to update to: the newest, or the one --to names."""
    if requested is None:
        return available[-1]
    try:
        wanted = Version.parse(requested)
    except ValueError as exc:
        raise UpdateError(str(exc), "pass --to like v0.12.0") from exc
    if wanted not in available:
        newest = ", ".join(str(version) for version in available[-5:])
        raise UpdateError(
            f"the template has no tag {wanted}", f"the newest tags are {newest}"
        )
    return wanted
```

- [ ] **Step 4: Run the tests**

Run: `uv run --group dev pytest tests/cli/test_versions.py -v && just lint`
Expected: all PASS; ruff and mypy clean (mypy sees `Git` only under `TYPE_CHECKING`; Task 3 creates it — until then mypy reports the missing module: run `just lint` again after Task 3 if it complains here).

- [ ] **Step 5: Commit**

```bash
git add src/pyfr_cli/versions.py tests/cli/test_versions.py
git commit -m "feat(pyfr-cli): parse and compare template versions

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 3: `git.py` — the wrapper and the queries

**Files:**
- Create: `src/pyfr_cli/git.py`
- Create: `tests/cli/helpers.py`, `tests/cli/conftest.py`
- Test: `tests/cli/test_git.py`, and add the `remote_versions` test to `tests/cli/test_versions.py`

**Interfaces:**
- Produces: `Git(cwd: Path)` with `run(*args, check=True) -> CompletedProcess[str]`, `out(*args) -> str`, `ok(*args) -> bool`, `toplevel() -> Path`, `git_dir() -> Path`, `current_branch() -> str | None`, `has_tracked_changes() -> bool`, `has_staged_changes() -> bool`, `operation_in_progress() -> str | None`, `root_commits() -> list[str]`, `has_identity() -> bool`, `branch_exists(name) -> bool`, `remote_exists(name) -> bool`, `commit(message, *, allow_empty=False) -> str` (sha; `--no-verify`), `subject(rev) -> str`. `GitError(UpdateError)`. `require_tools(*names: str) -> None`.
- Test helpers: `cli.helpers.git(cwd, *args) -> str`, `cli.helpers.make_repo(path, files=None) -> Path` (one commit `chore: generate the project from pyfr` on `main`, identity set).

- [ ] **Step 1: Write the helpers and the git-isolation fixture**

`tests/cli/helpers.py`:

```python
"""Tiny git repositories for the pyfr-cli unit tests."""

from __future__ import annotations

import subprocess
from pathlib import Path


def git(cwd: Path, *args: str) -> str:
    """Run git in `cwd`; fail the test on a non-zero exit; return stdout."""
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout.strip()


def make_repo(path: Path, files: dict[str, str] | None = None) -> Path:
    """A repository on `main` with one commit -- the shape the generator
    leaves behind -- holding `files` (default: one README)."""
    path.mkdir(parents=True, exist_ok=True)
    git(path, "init", "-q", "-b", "main")
    git(path, "config", "user.name", "Test")
    git(path, "config", "user.email", "test@example.com")
    for name, text in (files or {"README.md": "hello\n"}).items():
        target = path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(text)
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", "chore: generate the project from pyfr")
    return path


def commit_all(path: Path, message: str) -> str:
    git(path, "add", "-A")
    git(path, "commit", "-q", "-m", message)
    return git(path, "rev-parse", "HEAD")
```

`tests/cli/conftest.py`:

```python
"""Every pyfr-cli test runs git in isolation from the contributor's machine."""

from __future__ import annotations

from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def isolated_git(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    # Neither the contributor's global git configuration (commit signing,
    # hooks, an excludes file) nor the system one reaches the repositories
    # these tests build or the git the tool runs -- the same isolation as
    # tests/test_regen.py. The tool inherits the environment, so this
    # covers its subprocesses too.
    config = tmp_path / "gitconfig"
    config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
```

- [ ] **Step 2: Write the failing tests**

`tests/cli/test_git.py`:

```python
"""The git wrapper: queries the update relies on, and the hook skip."""

from __future__ import annotations

import os
import stat
from pathlib import Path

import pytest
from cli.helpers import commit_all, git, make_repo

from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git, GitError, require_tools


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    return make_repo(tmp_path / "repo")


def test_run_raises_a_git_error_with_the_message(repo: Path) -> None:
    with pytest.raises(GitError) as stop:
        Git(repo).run("rev-parse", "--verify", "no-such-ref")
    assert "no-such-ref" in stop.value.cause


def test_out_and_ok(repo: Path) -> None:
    assert Git(repo).out("rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert Git(repo).ok("rev-parse", "HEAD")
    assert not Git(repo).ok("rev-parse", "--verify", "no-such-ref")


def test_toplevel_and_git_dir_from_a_subdirectory(repo: Path) -> None:
    sub = repo / "src"
    sub.mkdir()
    assert Git(sub).toplevel() == repo.resolve()
    assert Git(sub).git_dir() == (repo / ".git").resolve()


def test_git_dir_of_a_linked_worktree_is_its_own(repo: Path, tmp_path: Path) -> None:
    git(repo, "branch", "other")
    worktree = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(worktree), "other")
    assert Git(worktree).git_dir() == (repo / ".git" / "worktrees" / "wt").resolve()


def test_current_branch_is_none_when_detached(repo: Path) -> None:
    assert Git(repo).current_branch() == "main"
    git(repo, "checkout", "-q", "--detach")
    assert Git(repo).current_branch() is None


def test_tracked_changes_ignore_untracked_files(repo: Path) -> None:
    (repo / "scratch.txt").write_text("untracked\n")
    assert not Git(repo).has_tracked_changes()
    (repo / "README.md").write_text("changed\n")
    assert Git(repo).has_tracked_changes()
    git(repo, "add", "README.md")
    assert Git(repo).has_staged_changes()


def test_operation_in_progress_sees_a_conflicted_merge(repo: Path) -> None:
    assert Git(repo).operation_in_progress() is None
    git(repo, "branch", "other")
    (repo / "README.md").write_text("ours\n")
    commit_all(repo, "ours")
    git(repo, "switch", "-q", "other")
    (repo / "README.md").write_text("theirs\n")
    commit_all(repo, "theirs")
    git(repo, "switch", "-q", "main")
    assert Git(repo).run("merge", "other", check=False).returncode != 0
    assert Git(repo).operation_in_progress() == "merge"


def test_root_commits_and_identity(repo: Path) -> None:
    root = git(repo, "rev-list", "--max-parents=0", "HEAD")
    assert Git(repo).root_commits() == [root]
    assert Git(repo).has_identity()
    git(repo, "config", "--unset", "user.email")
    assert not Git(repo).has_identity()


def test_branch_and_remote_exist(repo: Path, tmp_path: Path) -> None:
    assert Git(repo).branch_exists("main")
    assert not Git(repo).branch_exists("template")
    assert not Git(repo).remote_exists("origin")
    git(repo, "remote", "add", "origin", str(tmp_path / "origin.git"))
    assert Git(repo).remote_exists("origin")


def test_commit_skips_the_repository_hooks(repo: Path) -> None:
    # The generator installs pre-commit into .git/hooks; the tool's own
    # commits are mechanical and must not run the project's hooks in the
    # template worktree (Global Constraints).
    hook = repo / ".git" / "hooks" / "pre-commit"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(hook.stat().st_mode | stat.S_IXUSR)
    (repo / "README.md").write_text("changed\n")
    git(repo, "add", "README.md")
    sha = Git(repo).commit("chore: template v0.1.0 -> v0.2.0\n\nX: y\n")
    assert git(repo, "rev-parse", "HEAD") == sha
    assert Git(repo).subject("HEAD") == "chore: template v0.1.0 -> v0.2.0"
    with pytest.raises(GitError):
        Git(repo).commit("nothing staged")
    assert Git(repo).commit("empty is fine", allow_empty=True)


def test_require_tools_names_the_missing_one(monkeypatch: pytest.MonkeyPatch) -> None:
    require_tools("git")
    monkeypatch.setenv("PATH", os.devnull)
    with pytest.raises(UpdateError) as stop:
        require_tools("git", "uv")
    assert stop.value.cause == "git is not on PATH"
```

Append to `tests/cli/test_versions.py`:

```python


def test_remote_versions_reads_a_repository_by_path(tmp_path: Path) -> None:
    from cli.helpers import git, make_repo

    from pyfr_cli.git import Git

    template = make_repo(tmp_path / "template")
    git(template, "tag", "v0.5.0")
    git(template, "tag", "-a", "v0.6.0", "-m", "annotated")
    git(template, "tag", "not-a-release")
    assert remote_versions(str(template), Git(tmp_path)) == [
        Version(0, 5, 0),
        Version(0, 6, 0),
    ]


def test_remote_versions_refuses_a_repository_without_release_tags(
    tmp_path: Path,
) -> None:
    from cli.helpers import make_repo

    from pyfr_cli.git import Git

    template = make_repo(tmp_path / "template")
    with pytest.raises(UpdateError, match="no release tags"):
        remote_versions(str(template), Git(tmp_path))


def test_remote_versions_refuses_an_unreachable_template(tmp_path: Path) -> None:
    from pyfr_cli.git import Git

    with pytest.raises(UpdateError, match="could not list the tags"):
        remote_versions(str(tmp_path / "missing"), Git(tmp_path))
```

and add `from pathlib import Path` to that file's imports and `remote_versions` to its `pyfr_cli.versions` import.

- [ ] **Step 3: Run them to verify they fail**

Run: `uv run --group dev pytest tests/cli/test_git.py tests/cli/test_versions.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli.git'`.

- [ ] **Step 4: Implement**

`src/pyfr_cli/git.py`:

```python
"""Every git call the tool makes goes through `Git.run`."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pyfr_cli.errors import UpdateError


class GitError(UpdateError):
    """A git command the tool expected to succeed did not."""


@dataclass(frozen=True)
class Git:
    """git, run in one directory.

    Arguments are always fixed literals or paths the tool computed, never
    input typed by a user.
    """

    cwd: Path

    def run(
        self, *args: str, check: bool = True
    ) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args], cwd=self.cwd, capture_output=True, text=True
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise GitError(
                f"git {' '.join(args)} failed in {self.cwd}: {detail}",
                "the git message above says what went wrong",
            )
        return result

    def out(self, *args: str) -> str:
        return self.run(*args).stdout.strip()

    def ok(self, *args: str) -> bool:
        return self.run(*args, check=False).returncode == 0

    def toplevel(self) -> Path:
        return Path(self.out("rev-parse", "--show-toplevel")).resolve()

    def git_dir(self) -> Path:
        # Relative for the main worktree (".git"), absolute for a linked
        # worktree; resolved against cwd either way.
        return (self.cwd / self.out("rev-parse", "--git-dir")).resolve()

    def current_branch(self) -> str | None:
        name = self.out("rev-parse", "--abbrev-ref", "HEAD")
        return None if name == "HEAD" else name

    def has_tracked_changes(self) -> bool:
        return bool(self.out("status", "--porcelain", "--untracked-files=no"))

    def has_staged_changes(self) -> bool:
        return not self.ok("diff", "--cached", "--quiet")

    def operation_in_progress(self) -> str | None:
        git_dir = self.git_dir()
        if (git_dir / "MERGE_HEAD").exists():
            return "merge"
        if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
            return "rebase"
        if (git_dir / "CHERRY_PICK_HEAD").exists():
            return "cherry-pick"
        return None

    def root_commits(self) -> list[str]:
        return self.out("rev-list", "--max-parents=0", "HEAD").split()

    def has_identity(self) -> bool:
        return self.ok("config", "user.name") and self.ok("config", "user.email")

    def branch_exists(self, name: str) -> bool:
        return self.ok("show-ref", "--verify", "--quiet", f"refs/heads/{name}")

    def remote_exists(self, name: str) -> bool:
        return self.ok("remote", "get-url", name)

    def commit(self, message: str, *, allow_empty: bool = False) -> str:
        """Commit what is staged and return the sha.

        `--no-verify`: the tool's commits are mechanical, and the template
        worktree shares .git/hooks with the project, where the generator
        installed pre-commit. CI runs the gates on the pull request.
        """
        args = ["commit", "--quiet", "--no-verify", "--message", message]
        if allow_empty:
            args.append("--allow-empty")
        self.run(*args)
        return self.out("rev-parse", "HEAD")

    def subject(self, rev: str) -> str:
        return self.out("show", "--no-patch", "--format=%s", rev)


def require_tools(*names: str) -> None:
    for name in names:
        if shutil.which(name) is None:
            raise UpdateError(f"{name} is not on PATH", f"install {name}, then run again")
```

- [ ] **Step 5: Run the tests**

Run: `uv run --group dev pytest tests/cli -v && just lint`
Expected: all PASS; ruff and mypy clean.

- [ ] **Step 6: Commit**

```bash
git add src/pyfr_cli/git.py tests/cli/helpers.py tests/cli/conftest.py tests/cli/test_git.py tests/cli/test_versions.py
git commit -m "feat(pyfr-cli): add the git wrapper and the repository queries

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 4: `answers.py` — `.pyfr-answers.yml`

**Files:**
- Create: `src/pyfr_cli/answers.py`
- Test: `tests/cli/test_answers.py`

**Interfaces:**
- Produces: `answers.FILE == ".pyfr-answers.yml"`; `answers.GUIDE == "docs/guides/update-from-template.md"`; `Answers(path: Path, template: str, version: Version, values: dict[str, str])`; `load(project: Path) -> Answers`; `context(answers: Answers, prompts: Iterable[str]) -> tuple[dict[str, str], list[str]]` (recorded values for the given prompts, and the prompt names that will take their default); `install(rendered_project: Path, project: Path) -> None`; `version_in(text: str) -> Version | None` (the `_template_version` of an answers file's text, for `vendor.py`).

- [ ] **Step 1: Write the failing tests**

`tests/cli/test_answers.py`:

```python
""".pyfr-answers.yml: reading what the generator recorded."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyfr_cli import answers
from pyfr_cli.errors import UpdateError
from pyfr_cli.versions import Version

RECORDED = """\
# Written by PyFr when this project was generated.
_template: https://github.com/EmadMokhtar/pyfr
_template_version: "0.10.0"
project_name: "My Service"
project_slug: "my-service"
package_name: "my_service"
database: "postgres"
http_port: "8000"
"""


def write(project: Path, text: str = RECORDED) -> Path:
    project.mkdir(exist_ok=True)
    (project / answers.FILE).write_text(text)
    return project


def test_load_reads_template_version_and_every_value_as_a_string(
    tmp_path: Path,
) -> None:
    loaded = answers.load(write(tmp_path / "p"))
    assert loaded.template == "https://github.com/EmadMokhtar/pyfr"
    assert loaded.version == Version(0, 10, 0)
    assert loaded.values["http_port"] == "8000"
    assert loaded.values["_template_version"] == "0.10.0"
    assert loaded.path == tmp_path / "p" / answers.FILE


def test_load_refuses_a_missing_file_and_points_to_the_guide(tmp_path: Path) -> None:
    with pytest.raises(UpdateError) as stop:
        answers.load(tmp_path)
    assert answers.FILE in stop.value.cause
    assert answers.GUIDE in stop.value.fix


@pytest.mark.parametrize(
    ("text", "cause"),
    [
        ("_template: x\n", "no _template_version"),
        ("_template_version: '0.1.0'\n", "no _template"),
        ("_template: x\n_template_version: latest\n", "not a version"),
        ("- a list\n", "not a mapping"),
        ("a: [unclosed\n", "not valid YAML"),
    ],
)
def test_load_refuses_a_broken_file(tmp_path: Path, text: str, cause: str) -> None:
    with pytest.raises(UpdateError) as stop:
        answers.load(write(tmp_path / "p", text))
    assert cause in stop.value.cause


def test_context_keeps_recorded_prompts_and_names_the_defaulted_ones(
    tmp_path: Path,
) -> None:
    loaded = answers.load(write(tmp_path / "p"))
    # The target declares a new prompt (team_channel), dropped one the
    # project recorded (http_port), and its _ keys are never prompts.
    prompts = ["project_name", "database", "team_channel", "_template_version"]
    recorded, defaulted = answers.context(loaded, prompts)
    assert recorded == {"project_name": "My Service", "database": "postgres"}
    assert defaulted == ["team_channel"]


def test_install_copies_the_rendered_file_over_the_project_one(
    tmp_path: Path,
) -> None:
    project = write(tmp_path / "p")
    rendered = write(tmp_path / "r", RECORDED.replace("0.10.0", "0.12.0"))
    answers.install(rendered, project)
    assert answers.load(project).version == Version(0, 12, 0)


def test_version_in_reads_the_text_of_an_answers_file() -> None:
    assert answers.version_in(RECORDED) == Version(0, 10, 0)
    assert answers.version_in("project_name: x\n") is None
    assert answers.version_in("not: [yaml\n") is None
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --group dev pytest tests/cli/test_answers.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli.answers'`.

- [ ] **Step 3: Implement**

`src/pyfr_cli/answers.py`:

```python
""".pyfr-answers.yml: what the generator recorded, what an update rewrites."""

from __future__ import annotations

import shutil
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

import yaml

from pyfr_cli.errors import UpdateError
from pyfr_cli.versions import Version

FILE = ".pyfr-answers.yml"
GUIDE = "docs/guides/update-from-template.md"


@dataclass(frozen=True)
class Answers:
    path: Path
    template: str
    version: Version
    # Every key, every value as a string: cookiecutter's extra_context
    # takes strings, and the generator wrote the file from strings.
    values: dict[str, str]


def load(project: Path) -> Answers:
    path = project / FILE
    if not path.is_file():
        raise UpdateError(
            f"{FILE} not found in {project}",
            "run from the project root; a project generated before PyFr "
            f"v0.7.0 has no answers file -- {GUIDE} shows how to write one",
        )
    try:
        data = yaml.safe_load(path.read_text())
    except yaml.YAMLError as exc:
        raise UpdateError(
            f"{FILE} is not valid YAML: {exc}", f"fix the file; see {GUIDE}"
        ) from exc
    if not isinstance(data, dict):
        raise UpdateError(f"{FILE} is not a mapping", f"fix the file; see {GUIDE}")
    values = {str(key): str(value) for key, value in data.items()}
    for key in ("_template", "_template_version"):
        if key not in values:
            raise UpdateError(f"{FILE} has no {key}", f"add it; see {GUIDE}")
    try:
        version = Version.parse(values["_template_version"])
    except ValueError as exc:
        raise UpdateError(
            f"{FILE}: _template_version {exc}",
            f"set it to the version the project was generated from; see {GUIDE}",
        ) from exc
    return Answers(path, values["_template"], version, values)


def context(
    answers: Answers, prompts: Iterable[str]
) -> tuple[dict[str, str], list[str]]:
    """cookiecutter's extra_context for a render at a template declaring
    `prompts`, and the names of the prompts that will take their default.

    A prompt the target added since the project was generated has no
    recorded value; a recorded answer the target no longer declares is
    left out (spec section 4.4).
    """
    wanted = [prompt for prompt in prompts if not prompt.startswith("_")]
    recorded = {p: answers.values[p] for p in wanted if p in answers.values}
    defaulted = [p for p in wanted if p not in answers.values]
    return recorded, defaulted


def install(rendered_project: Path, project: Path) -> None:
    """Step 10: the render's answers file -- the recorded answers, the new
    prompts' defaults, the target version -- becomes the project's."""
    shutil.copyfile(rendered_project / FILE, project / FILE)


def version_in(text: str) -> Version | None:
    """The _template_version an answers file's text records, if any."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError:
        return None
    if not isinstance(data, dict) or "_template_version" not in data:
        return None
    try:
        return Version.parse(str(data["_template_version"]))
    except ValueError:
        return None
```

- [ ] **Step 4: Run the tests**

Run: `uv run --group dev pytest tests/cli/test_answers.py -v && just lint`
Expected: all PASS; clean.

- [ ] **Step 5: Commit**

```bash
git add src/pyfr_cli/answers.py tests/cli/test_answers.py
git commit -m "feat(pyfr-cli): read and rewrite the answers file

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 5: `state.py` — `.git/pyfr-update.json`

**Files:**
- Create: `src/pyfr_cli/state.py`
- Test: `tests/cli/test_state.py`

**Interfaces:**
- Produces: `Phase = Literal["merging", "after-scripts"]`; `State(from_version: Version, to_version: Version, phase: Phase, graft: str | None = None)` — `graft` is the sha of a `HEAD` the tool grafted (Task 11) and must un-graft if the run died; `path(git: Git) -> Path`; `load(git) -> State | None`; `save(git, state) -> None`; `clear(git) -> None`.

- [ ] **Step 1: Write the failing tests**

`tests/cli/test_state.py`:

```python
"""The paused-update record in .git/, never committed."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from cli.helpers import git, make_repo

from pyfr_cli import state
from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git
from pyfr_cli.versions import Version

PAUSED = state.State(Version(0, 10, 0), Version(0, 12, 0), "merging", graft="abc123")


def test_round_trip_and_clear(tmp_path: Path) -> None:
    repo = Git(make_repo(tmp_path / "repo"))
    assert state.load(repo) is None
    state.save(repo, PAUSED)
    assert state.path(repo) == (tmp_path / "repo" / ".git" / "pyfr-update.json").resolve()
    assert json.loads(state.path(repo).read_text()) == {
        "from": "v0.10.0",
        "to": "v0.12.0",
        "phase": "merging",
        "graft": "abc123",
    }
    assert state.load(repo) == PAUSED
    state.clear(repo)
    assert state.load(repo) is None
    state.clear(repo)  # clearing twice is fine


def test_the_file_lives_in_the_worktree_s_own_git_dir(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "repo")
    git(repo, "branch", "other")
    worktree = tmp_path / "wt"
    git(repo, "worktree", "add", "-q", str(worktree), "other")
    state.save(Git(worktree), PAUSED)
    assert (repo / ".git" / "worktrees" / "wt" / "pyfr-update.json").exists()
    assert state.load(Git(repo)) is None


def test_a_broken_file_is_an_error_naming_it(tmp_path: Path) -> None:
    repo = Git(make_repo(tmp_path / "repo"))
    state.path(repo).write_text('{"phase": "dancing"}')
    with pytest.raises(UpdateError) as stop:
        state.load(repo)
    assert "pyfr-update.json" in stop.value.cause
    assert "delete" in stop.value.fix
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --group dev pytest tests/cli/test_state.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli.state'`.

- [ ] **Step 3: Implement**

`src/pyfr_cli/state.py`:

```python
"""A paused update, recorded in .git/ so a re-run of the same command resumes.

Written when a merge stops on conflicts and before the after-scripts run;
deleted when the update completes. Inside .git/, so never committed
(spec section 4.8).
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git
from pyfr_cli.versions import Version

FILE = "pyfr-update.json"
Phase = Literal["merging", "after-scripts"]
PHASES: tuple[Phase, ...] = ("merging", "after-scripts")


@dataclass(frozen=True)
class State:
    from_version: Version
    to_version: Version
    phase: Phase
    # The sha of the HEAD the tool grafted an extra parent onto for the
    # merge (spec section 4.7), so a run that died before deleting the
    # graft is cleaned up by the next one.
    graft: str | None = None


def path(git: Git) -> Path:
    return git.git_dir() / FILE


def load(git: Git) -> State | None:
    file = path(git)
    if not file.exists():
        return None
    fix = f"delete {file} if no update is in progress, then run again"
    try:
        data = json.loads(file.read_text())
        phase = data["phase"]
        if phase not in PHASES:
            raise ValueError(f"unknown phase {phase!r}")
        return State(
            Version.parse(data["from"]),
            Version.parse(data["to"]),
            "merging" if phase == "merging" else "after-scripts",
            data.get("graft"),
        )
    except (KeyError, ValueError, TypeError) as exc:
        raise UpdateError(f"{FILE} is unreadable: {exc}", fix) from exc


def save(git: Git, state: State) -> None:
    record = {
        "from": str(state.from_version),
        "to": str(state.to_version),
        "phase": state.phase,
        "graft": state.graft,
    }
    path(git).write_text(json.dumps(record, indent=2) + "\n")


def clear(git: Git) -> None:
    path(git).unlink(missing_ok=True)
```

- [ ] **Step 4: Run the tests**

Run: `uv run --group dev pytest tests/cli/test_state.py -v && just lint`
Expected: all PASS; clean. (`json.JSONDecodeError` is a `ValueError`, so a truncated file is caught too.)

- [ ] **Step 5: Commit**

```bash
git add src/pyfr_cli/state.py tests/cli/test_state.py
git commit -m "feat(pyfr-cli): record a paused update in .git

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 6: `ignore.py` — `.pyfr-update-ignore`

**Files:**
- Create: `src/pyfr_cli/ignore.py`
- Test: `tests/cli/test_ignore.py`

**Interfaces:**
- Produces: `ignore.FILE == ".pyfr-update-ignore"`; `default_text(package: str, database: str) -> str` (the built-in default, rendered — PR 2 copies this text into the template body); `Ignore(lines: Iterable[str])` with `.matches(relative: str) -> bool`; `Ignore.from_text(text: str) -> Ignore`; `load(project: Path, recorded: Answers) -> tuple[Ignore, bool]` — the project's file, or the default when it has none; the bool says whether the file existed.

Patterns are anchored with a leading `/` where they name one path at the root: in gitignore syntax a pattern without a slash (`README.md`) matches that name at *any* depth, and the template body has other `README.md` files (for example under `docs/adr/`). `docs/adr/` and `src/…/` contain a slash and are anchored already; the leading `/` is added everywhere for one uniform rule.

- [ ] **Step 1: Write the failing tests**

`tests/cli/test_ignore.py`:

```python
""".pyfr-update-ignore: gitignore syntax over the paths an update never touches."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyfr_cli import answers, ignore
from pyfr_cli.versions import Version

RECORDED = answers.Answers(
    Path(".pyfr-answers.yml"),
    "https://example.com/pyfr",
    Version(0, 10, 0),
    {"package_name": "my_service", "database": "postgres"},
)


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("/README.md", "README.md", True),
        ("/README.md", "docs/adr/README.md", False),
        ("README.md", "docs/adr/README.md", True),
        ("/docs/adr/", "docs/adr/0001-x.md", True),
        ("/docs/adr/", "docs/adr-drafts/x.md", False),
        ("/src/my_service/domain/", "src/my_service/domain/deep/order.py", True),
        ("/src/my_service/domain/", "src/my_service/services/order.py", False),
        ("*.snap", "tests/unit/__snapshots__/a.snap", True),
        ("**/fixtures/", "tests/integration/fixtures/x.json", True),
        ("/.pyfr-update-ignore", ".pyfr-update-ignore", True),
    ],
)
def test_patterns_follow_gitignore(pattern: str, path: str, expected: bool) -> None:
    assert ignore.Ignore([pattern]).matches(path) is expected


def test_comments_blank_lines_and_negation() -> None:
    spec = ignore.Ignore.from_text("# yours\n\n/docs/*.md\n!/docs/index.md\n")
    assert spec.matches("docs/runbook.md")
    assert not spec.matches("docs/index.md")
    assert not spec.matches("docs/reference/commands.md")


def test_a_hash_after_a_pattern_is_part_of_the_pattern() -> None:
    # gitignore has no inline comments; the default keeps comments on their
    # own lines for exactly this reason (spec section 5.2).
    spec = ignore.Ignore.from_text("/README.md   # yours\n")
    assert not spec.matches("README.md")


def test_default_covers_the_spec_s_list_and_ignores_itself() -> None:
    spec = ignore.Ignore.from_text(ignore.default_text("my_service", "postgres"))
    for path in (
        ".pyfr-answers.yml",
        ".pyfr-update-ignore",
        "README.md",
        "CHANGELOG.md",
        "uv.lock",
        "migrations/000001_init.up.sql",
        "schema.sql",
        "openapi.json",
        "openapi.baseline.json",
        "docs/adr/0001-x.md",
        "src/my_service/domain/order.py",
        "src/my_service/services/orders.py",
        "src/my_service/api/v1/orders.py",
    ):
        assert spec.matches(path), path
    for path in (
        "pyproject.toml",
        "justfile",
        "src/my_service/api/health.py",
        "src/my_service/infrastructure/db/engine.py",
        "tests/unit/test_settings.py",
        ".github/workflows/ci.yml",
        "docs/reference/commands.md",
    ):
        assert not spec.matches(path), path


def test_default_drops_the_schema_lines_without_postgres() -> None:
    text = ignore.default_text("my_service", "none")
    assert "migrations/" not in text
    assert "schema.sql" not in text
    assert "/src/my_service/domain/" in text


def test_load_prefers_the_project_file(tmp_path: Path) -> None:
    (tmp_path / ignore.FILE).write_text("/ruff.toml\n")
    spec, from_file = ignore.load(tmp_path, RECORDED)
    assert from_file
    assert spec.matches("ruff.toml")
    assert not spec.matches("README.md")


def test_load_falls_back_to_the_default_for_the_recorded_answers(
    tmp_path: Path,
) -> None:
    spec, from_file = ignore.load(tmp_path, RECORDED)
    assert not from_file
    assert spec.matches("README.md")
    assert spec.matches("migrations/000001_init.up.sql")
    assert spec.matches("src/my_service/domain/order.py")
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --group dev pytest tests/cli/test_ignore.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli.ignore'`.

- [ ] **Step 3: Implement**

`src/pyfr_cli/ignore.py`:

```python
""".pyfr-update-ignore: the paths an update leaves exactly as the project has them.

gitignore syntax, matched with pathspec. A project generated before the
template shipped the file uses the built-in default below, rendered for its
answers (spec section 5.2 and decision M8-5).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pathspec import GitIgnoreSpec

from pyfr_cli.answers import Answers

FILE = ".pyfr-update-ignore"

HEADER = """\
# Paths `just update` leaves exactly as this project has them: yours from
# the first day, or artifacts of your code. Add paths as you diverge --
# one gitignore pattern per line, comments on their own lines.
# Everything not listed is template-owned and receives fixes by default.

# Written by the update itself.
/.pyfr-answers.yml
# This file.
/.pyfr-update-ignore
/README.md
/CHANGELOG.md
# Resolver output; run `uv lock` after an update that touched pyproject.toml.
/uv.lock
"""
SCHEMA = """\
# Your schema.
/migrations/
/schema.sql
"""
FOOTER = """\
# Artifacts of your code: the contract, and the baseline your release promotes.
/openapi.json
/openapi.baseline.json
# Your decisions.
/docs/adr/
# The example slice, then your business model.
/src/{package}/domain/
/src/{package}/services/
/src/{package}/api/v1/
"""


def default_text(package: str, database: str) -> str:
    """The built-in default, as the template body ships it for these answers.

    The schema lines exist only when the project has a database: the
    generator prunes migrations/ and schema.sql otherwise.
    """
    schema = SCHEMA if database == "postgres" else ""
    return HEADER + schema + FOOTER.format(package=package)


class Ignore:
    def __init__(self, lines: Iterable[str]) -> None:
        self._spec = GitIgnoreSpec.from_lines(lines)

    @classmethod
    def from_text(cls, text: str) -> Ignore:
        return cls(text.splitlines())

    def matches(self, relative: str) -> bool:
        """Whether a path (POSIX, relative to the project root) is left alone."""
        return self._spec.match_file(relative)


def load(project: Path, recorded: Answers) -> tuple[Ignore, bool]:
    """The project's ignore file, or the default rendered for its answers.

    Returns the spec and whether the file existed, so the caller can say
    which one applied.
    """
    file = project / FILE
    if file.is_file():
        return Ignore.from_text(file.read_text()), True
    package = recorded.values.get("package_name", "")
    database = recorded.values.get("database", "none")
    return Ignore.from_text(default_text(package, database)), False
```

- [ ] **Step 4: Run the tests**

Run: `uv run --group dev pytest tests/cli/test_ignore.py -v && just lint`
Expected: all PASS; clean. If mypy reports `match_file` returning `Any`, change the return line to `return bool(self._spec.match_file(relative))`.

- [ ] **Step 5: Align the spec's default list with the anchored patterns**

In `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md`, section 5.2, replace the default-list code block (the one Task 1 wrote, with own-line comments) with the exact text `default_text("<package>", "postgres")` produces — the `HEADER`, `SCHEMA` and `FOOTER` strings above, with `{package}` written as `<package>` — and add after the block: "Every pattern carries a leading `/`: without it, gitignore syntax matches the name at any depth, and `README.md` would also match `docs/adr/README.md`."

- [ ] **Step 6: Commit**

```bash
git add src/pyfr_cli/ignore.py tests/cli/test_ignore.py docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md
git commit -m "feat(pyfr-cli): read the ignore list, with the built-in default

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 7: `changelog.py` — the entries between two versions

**Files:**
- Create: `src/pyfr_cli/changelog.py`
- Test: `tests/cli/test_changelog.py`

**Interfaces:**
- Produces: `sections(text: str) -> list[tuple[Version, str, str]]` — `(version, rest of the heading line, body)` in file order; `release_url(template: str, version: Version) -> str`; `entries(text: str, after: Version, up_to: Version, template: str) -> str` — the sections with `after < version <= up_to`, newest first, headings turned into release links; empty string when none.

- [ ] **Step 1: Write the failing tests**

`tests/cli/test_changelog.py`:

```python
"""The template's CHANGELOG.md entries an update carries in its commit body."""

from __future__ import annotations

from pyfr_cli import changelog
from pyfr_cli.versions import Version

TEXT = """\
# Changelog

Generated by Commitizen. Never edited by hand.

## v0.12.0 (2026-09-20)

### Feat

- let a generated project update itself from the template (#60)

## v0.11.0 (2026-09-18)

### Feat

- add pyfr-cli with pyfr update and update-check (#55)

### Fix

- render both bounds in generated config docs

## v0.10.0 (2026-09-14)

### Feat

- prove a generated project passes its own gates and close m7 (#50)
"""
TEMPLATE = "https://github.com/EmadMokhtar/pyfr"


def test_sections_are_parsed_in_file_order_with_their_bodies() -> None:
    parsed = changelog.sections(TEXT)
    assert [version for version, _, _ in parsed] == [
        Version(0, 12, 0),
        Version(0, 11, 0),
        Version(0, 10, 0),
    ]
    version, rest, body = parsed[1]
    assert rest == " (2026-09-18)"
    assert body.startswith("### Feat")
    assert "render both bounds" in body
    assert "close m7" not in body


def test_entries_take_the_half_open_range_newest_first_with_links() -> None:
    body = changelog.entries(TEXT, Version(0, 10, 0), Version(0, 12, 0), TEMPLATE)
    assert body.index("v0.12.0") < body.index("v0.11.0")
    assert "v0.10.0" not in body
    assert (
        "## [v0.12.0](https://github.com/EmadMokhtar/pyfr/releases/tag/v0.12.0)"
        " (2026-09-20)"
    ) in body
    assert "- add pyfr-cli with pyfr update and update-check (#55)" in body
    assert body.endswith("\n")


def test_entries_is_empty_when_nothing_is_in_range() -> None:
    assert changelog.entries(TEXT, Version(0, 12, 0), Version(0, 12, 0), TEMPLATE) == ""
    assert changelog.entries("", Version(0, 1, 0), Version(9, 0, 0), TEMPLATE) == ""


def test_release_url_normalises_the_template_url() -> None:
    for url in (TEMPLATE, TEMPLATE + "/", TEMPLATE + ".git"):
        assert (
            changelog.release_url(url, Version(0, 12, 0))
            == "https://github.com/EmadMokhtar/pyfr/releases/tag/v0.12.0"
        )
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --group dev pytest tests/cli/test_changelog.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli.changelog'`.

- [ ] **Step 3: Implement**

`src/pyfr_cli/changelog.py`:

```python
"""The template's CHANGELOG.md: Commitizen's `## vX.Y.Z (date)` sections.

The sections between the recorded version and the target become the merge
commit's body, and from there the weekly pull request's (spec section 4.9).
"""

from __future__ import annotations

import re

from pyfr_cli.versions import Version

HEADING = re.compile(r"^## v?(?P<version>\d+\.\d+\.\d+)(?P<rest>.*)$")


def sections(text: str) -> list[tuple[Version, str, str]]:
    """(version, the rest of the heading line, body) for each section, in
    file order -- Commitizen writes the newest first."""
    found: list[tuple[Version, str, list[str]]] = []
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading is not None:
            found.append((Version.parse(heading["version"]), heading["rest"], []))
        elif found:
            found[-1][2].append(line)
    return [
        (version, rest, "\n".join(body).strip()) for version, rest, body in found
    ]


def release_url(template: str, version: Version) -> str:
    base = template.rstrip("/").removesuffix(".git")
    return f"{base}/releases/tag/{version}"


def entries(text: str, after: Version, up_to: Version, template: str) -> str:
    """The sections with after < version <= up_to, newest first, each
    heading linking to its release. Empty when there are none."""
    parts = [
        f"## [{version}]({release_url(template, version)}){rest}\n\n{body}\n"
        for version, rest, body in sections(text)
        if after < version <= up_to
    ]
    return "\n".join(parts)
```

- [ ] **Step 4: Run the tests**

Run: `uv run --group dev pytest tests/cli/test_changelog.py -v && just lint`
Expected: all PASS; clean.

- [ ] **Step 5: Commit**

```bash
git add src/pyfr_cli/changelog.py tests/cli/test_changelog.py
git commit -m "feat(pyfr-cli): extract the changelog entries between two versions

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 8: `render.py` — clone at a tag, render with the recorded answers

**Files:**
- Create: `src/pyfr_cli/render.py`
- Test: `tests/cli/test_render.py`

**Interfaces:**
- Produces: `Render(clone: Path, project: Path, defaulted: dict[str, str])`; `clone_template(template: str, version: Version, into: Path, git: Git) -> Path`; `prompts(clone: Path) -> dict[str, object]` (the target's `cookiecutter.json` without the `_` keys, raw values); `render(clone: Path, version: Version, recorded: Answers, output_dir: Path) -> Render`.

- [ ] **Step 1: Write the failing tests**

`tests/cli/test_render.py`:

```python
"""Rendering the template at the target version with the recorded answers.

A tiny template stands in for the real one: the real body is rendered by
tests/test_update_e2e.py.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest
from cli.helpers import commit_all, git, make_repo

from pyfr_cli import answers, render
from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git
from pyfr_cli.versions import Version

BODY = "{{cookiecutter.project_slug}}"
HOOK = """\
import os
import pathlib

# An environmental side effect, like the real hook's `git init`: it must
# not happen under PYFR_REGEN.
if not os.environ.get("PYFR_REGEN"):
    pathlib.Path("side-effect.txt").write_text("ran\\n")
"""
ANSWERS_BODY = """\
_template: https://example.com/pyfr
_template_version: "{{ cookiecutter._template_version }}"
project_slug: "{{ cookiecutter.project_slug }}"
flavour: "{{ cookiecutter.flavour }}"
greeting: "{{ cookiecutter.greeting }}"
"""


def write_template(root: Path, *, with_greeting_in_answers: bool = True) -> Path:
    (root / BODY).mkdir(parents=True)
    (root / "hooks").mkdir()
    (root / "cookiecutter.json").write_text(
        json.dumps(
            {
                "project_slug": "demo",
                "flavour": ["plain", "spicy"],
                "greeting": "hello",
                "_template_version": "1.1.0",
            }
        )
    )
    (root / "hooks" / "post_gen_project.py").write_text(HOOK)
    (root / BODY / "hello.txt").write_text("{{ cookiecutter.greeting }} {{ cookiecutter.project_slug }}\n")
    body = ANSWERS_BODY if with_greeting_in_answers else ANSWERS_BODY.replace('greeting: "{{ cookiecutter.greeting }}"\n', "")
    (root / BODY / answers.FILE).write_text(body)
    return root


def recorded(tmp_path: Path, **overrides: str) -> answers.Answers:
    values = {
        "_template": "https://example.com/pyfr",
        "_template_version": "1.0.0",
        "project_slug": "demo2",
        "flavour": "spicy",
        **overrides,
    }
    return answers.Answers(tmp_path / answers.FILE, values["_template"], Version(1, 0, 0), values)


def test_render_uses_recorded_answers_defaults_new_prompts_and_prunes_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    template = write_template(tmp_path / "template")
    monkeypatch.delenv("PYFR_REGEN", raising=False)
    result = render.render(template, Version(1, 1, 0), recorded(tmp_path), tmp_path / "out")
    assert result.clone == template
    assert result.project == tmp_path / "out" / "demo2"
    assert (result.project / "hello.txt").read_text() == "hello demo2\n"
    # The prompt the target added took its default, and is reported ...
    assert result.defaulted == {"greeting": "hello"}
    # ... the render's answers file records everything at the target version ...
    written = answers.load(result.project)
    assert written.version == Version(1, 1, 0)
    assert written.values["flavour"] == "spicy"
    # ... the hook pruned and stopped: no side effect ...
    assert not (result.project / "side-effect.txt").exists()
    # ... and the environment is as it was.
    assert "PYFR_REGEN" not in os.environ


def test_render_reports_the_raw_default_when_the_answers_file_lacks_the_prompt(
    tmp_path: Path,
) -> None:
    template = write_template(tmp_path / "template", with_greeting_in_answers=False)
    result = render.render(template, Version(1, 1, 0), recorded(tmp_path), tmp_path / "out")
    assert result.defaulted == {"greeting": "hello"}


def test_render_surfaces_a_recorded_choice_the_target_no_longer_offers(
    tmp_path: Path,
) -> None:
    template = write_template(tmp_path / "template")
    with pytest.raises(UpdateError) as stop:
        render.render(template, Version(1, 1, 0), recorded(tmp_path, flavour="hot"), tmp_path / "out")
    assert "v1.1.0" in stop.value.cause
    assert "hot" in stop.value.cause
    assert "flavour" in stop.value.cause


def test_prompts_are_the_non_underscore_keys(tmp_path: Path) -> None:
    template = write_template(tmp_path / "template")
    assert list(render.prompts(template)) == ["project_slug", "flavour", "greeting"]


def test_clone_template_checks_out_the_tag(tmp_path: Path) -> None:
    remote = make_repo(tmp_path / "remote", {"marker.txt": "v1\n"})
    git(remote, "tag", "v1.0.0")
    (remote / "marker.txt").write_text("v2\n")
    commit_all(remote, "v2")
    git(remote, "tag", "v2.0.0")
    clone = render.clone_template(str(remote), Version(1, 0, 0), tmp_path / "clone", Git(tmp_path))
    assert (clone / "marker.txt").read_text() == "v1\n"
    assert (clone / ".git").exists()


def test_clone_template_refuses_a_missing_tag(tmp_path: Path) -> None:
    remote = make_repo(tmp_path / "remote")
    with pytest.raises(UpdateError) as stop:
        render.clone_template(str(remote), Version(9, 9, 9), tmp_path / "clone", Git(tmp_path))
    assert "could not clone" in stop.value.cause
    assert "v9.9.9" in stop.value.cause
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --group dev pytest tests/cli/test_render.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli.render'`.

- [ ] **Step 3: Implement**

`src/pyfr_cli/render.py`:

```python
"""The template at the target version, rendered with the recorded answers.

A shallow clone into a temporary directory, rendered by path -- never by
URL, so cookiecutter's own clone cache and its re-clone prompt are never
involved, and the clone's updates/ and CHANGELOG.md are on disk for the
later steps (spec section 4.4).
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from pyfr_cli import answers
from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git
from pyfr_cli.versions import Version


@dataclass(frozen=True)
class Render:
    clone: Path
    project: Path
    # Prompts the target added since the project was generated, and the
    # default each one took.
    defaulted: dict[str, str]


def clone_template(template: str, version: Version, into: Path, git: Git) -> Path:
    result = git.run(
        "clone", "--quiet", "--depth", "1", "--branch", str(version),
        template, str(into), check=False,
    )  # fmt: skip
    if result.returncode != 0:
        raise UpdateError(
            f"could not clone {template} at {version}: {result.stderr.strip()}",
            "check the _template URL in .pyfr-answers.yml (or --template), "
            "and that you are online",
        )
    return into


def prompts(clone: Path) -> dict[str, object]:
    """The target's prompts: cookiecutter.json without the `_` keys."""
    data = json.loads((clone / "cookiecutter.json").read_text())
    if not isinstance(data, dict):
        raise UpdateError(
            f"{clone / 'cookiecutter.json'} is not a JSON object",
            "the template is broken at this version; pick another --to",
        )
    return {str(key): value for key, value in data.items() if not key.startswith("_")}


def render(clone: Path, version: Version, recorded: answers.Answers, output_dir: Path) -> Render:
    # Imported here so the other modules' unit tests need no cookiecutter.
    from cookiecutter.main import cookiecutter

    declared = prompts(clone)
    extra, defaulted = answers.context(recorded, declared)
    # PYFR_REGEN: the target's post-generation hook prunes and stops -- no
    # git init, no uv sync (the hook's own contract, scripts/regen.py sets
    # it the same way). Restored afterwards, whatever happens.
    previous = os.environ.get("PYFR_REGEN")
    os.environ["PYFR_REGEN"] = "1"
    try:
        project = Path(
            cookiecutter(
                str(clone),
                no_input=True,
                extra_context=extra,
                output_dir=str(output_dir),
                # Never read ~/.cookiecutterrc: a contributor's defaults
                # must not reach a project's update.
                default_config=True,
            )
        )
    except Exception as exc:
        # cookiecutter's own hierarchy, and ValueError for a recorded
        # choice the target no longer offers; the hook's message went to
        # stderr already.
        raise UpdateError(
            f"the template at {version} could not be rendered: {exc}",
            "the message names the recorded answer the template refused; "
            f"change it in {answers.FILE}, or pick another --to",
        ) from exc
    finally:
        if previous is None:
            os.environ.pop("PYFR_REGEN", None)
        else:
            os.environ["PYFR_REGEN"] = previous
    return Render(clone, project, _defaults(project, declared, defaulted))


def _defaults(project: Path, declared: dict[str, object], names: list[str]) -> dict[str, str]:
    """What each defaulted prompt became: read from the render's answers
    file, or cookiecutter.json's raw default when that file lacks it."""
    written: dict[str, str] = {}
    file = project / answers.FILE
    if file.is_file():
        data = yaml.safe_load(file.read_text())
        if isinstance(data, dict):
            written = {str(key): str(value) for key, value in data.items()}
    defaults: dict[str, str] = {}
    for name in names:
        raw = declared[name]
        fallback = raw[0] if isinstance(raw, list) and raw else raw
        defaults[name] = written.get(name, str(fallback))
    return defaults
```

- [ ] **Step 4: Run the tests**

Run: `uv run --group dev pytest tests/cli/test_render.py -v && just lint`
Expected: all PASS; clean. `ruff format --check` may want the `clone_template` call reflowed — keep the `# fmt: skip` or accept ruff's layout; either is fine.

- [ ] **Step 5: Commit**

```bash
git add src/pyfr_cli/render.py tests/cli/test_render.py
git commit -m "feat(pyfr-cli): clone the template at a tag and render it

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 9: `vendor.py` — the `template` branch

**Files:**
- Create: `src/pyfr_cli/vendor.py`
- Test: `tests/cli/test_vendor.py`

**Interfaces:**
- Produces: `BRANCH = "template"`, `REMOTE = "origin"`, `TRAILER = "Pyfr-Template-Version"`; `Branch(version: Version, base: str, created: bool, notes: list[str])`; `ensure(git: Git, recorded: Version, target: Version) -> Branch` (find/fetch/create, then the guard; `version` is `recorded` or `target`); `describe(git) -> tuple[Version, str]`; `commit_for(git, version: Version, base: str) -> str` (the sha that renders `version` — Task 11 pins the merge base to it); `worktree(git, path) -> Iterator[Git]` context manager; `sync(rendered: Path, worktree: Git, ignore: Ignore) -> None`; `commit(worktree: Git, previous: Version, target: Version) -> str`; `push(git) -> None`; `trailer_version(git, rev) -> Version | None`; `recorded_in(git, rev) -> Version | None`.

- [ ] **Step 1: Write the failing tests**

`tests/cli/test_vendor.py`:

```python
"""The `template` branch: found, created, guarded, synced, committed, pushed."""

from __future__ import annotations

from pathlib import Path

import pytest
from cli.helpers import commit_all, git, make_repo

from pyfr_cli import vendor
from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git
from pyfr_cli.ignore import Ignore
from pyfr_cli.versions import Version

V10, V12 = Version(0, 10, 0), Version(0, 12, 0)


def answers_text(version: str) -> str:
    return f'_template: https://example.com/pyfr\n_template_version: "{version}"\n'


@pytest.fixture
def project(tmp_path: Path) -> Path:
    # A generated project with an origin, as the hook and a first push leave it.
    repo = make_repo(
        tmp_path / "project",
        {
            ".pyfr-answers.yml": answers_text("0.10.0"),
            "README.md": "ours\n",
            "ruff.toml": "line-length = 88\n",
            "src/pkg/domain/order.py": "class Order: ...\n",
            "old.txt": "goes away\n",
        },
    )
    git(tmp_path, "init", "-q", "--bare", str(tmp_path / "origin.git"))
    git(repo, "remote", "add", "origin", str(tmp_path / "origin.git"))
    git(repo, "push", "-q", "-u", "origin", "main")
    return repo


@pytest.fixture
def rendered(tmp_path: Path) -> Path:
    # What the template renders at v0.12.0: ruff.toml changed, README changed
    # (ignored), a new file, old.txt gone, the domain slice untouched.
    root = tmp_path / "render"
    for name, text in {
        ".pyfr-answers.yml": answers_text("0.12.0"),
        "README.md": "theirs\n",
        "ruff.toml": "line-length = 100\n",
        "src/pkg/domain/order.py": "class Order: ...\n",
        "new.txt": "new in v0.12.0\n",
    }.items():
        (root / name).parent.mkdir(parents=True, exist_ok=True)
        (root / name).write_text(text)
    return root


IGNORE = Ignore(["/.pyfr-answers.yml", "/README.md"])


def update_branch(project: Path, rendered: Path, tmp_path: Path) -> str:
    """One full round: ensure, sync, commit -- as update.py will do it."""
    repo = Git(project)
    branch = vendor.ensure(repo, V10, V12)
    with vendor.worktree(repo, tmp_path / "wt") as worktree:
        vendor.sync(rendered, worktree, IGNORE)
        return vendor.commit(worktree, branch.version, V12)


def test_ensure_creates_the_branch_from_the_root_commit(project: Path) -> None:
    repo = Git(project)
    root = git(project, "rev-parse", "HEAD")
    branch = vendor.ensure(repo, V10, V12)
    assert branch.created
    assert branch.version == V10
    assert branch.base == root
    assert branch.notes == [
        f'template: created from root commit {root[:12]} "chore: generate the project from pyfr"'
    ]
    assert git(project, "rev-parse", "template") == root
    # Running again finds it and says nothing new.
    again = vendor.ensure(repo, V10, V12)
    assert not again.created
    assert "not on origin" in again.notes[0]


def test_ensure_refuses_a_repository_with_two_roots(project: Path) -> None:
    git(project, "switch", "-q", "--orphan", "imported")
    (project / "imported.txt").write_text("x\n")
    commit_all(project, "imported history")
    git(project, "switch", "-q", "main")
    git(project, "merge", "-q", "--allow-unrelated-histories", "-m", "join", "imported")
    with pytest.raises(UpdateError) as stop:
        vendor.ensure(Git(project), V10, V12)
    assert "2 root commits" in stop.value.cause
    assert vendor.GUIDE in stop.value.fix


def test_ensure_refuses_a_branch_whose_version_matches_neither_side(
    project: Path,
) -> None:
    with pytest.raises(UpdateError) as stop:
        vendor.ensure(Git(project), Version(0, 9, 0), V12)
    assert "template is at v0.10.0" in stop.value.cause
    assert "records v0.9.0" in stop.value.cause


def test_sync_and_commit_write_the_render_respecting_the_ignore_list(
    project: Path, rendered: Path, tmp_path: Path
) -> None:
    sha = update_branch(project, rendered, tmp_path)
    show = lambda name: git(project, "show", f"template:{name}")  # noqa: E731
    assert show("ruff.toml") == "line-length = 100"  # template-owned: updated
    assert show("README.md") == "ours"  # ignored: left as the project had it
    assert show(".pyfr-answers.yml") == answers_text("0.10.0").strip()
    assert show("new.txt") == "new in v0.12.0"
    assert not Git(project).ok("cat-file", "-e", "template:old.txt")
    assert git(project, "rev-parse", "template") == sha
    assert Git(project).subject(sha) == "chore: template v0.10.0 -> v0.12.0"
    assert vendor.trailer_version(Git(project), sha) == V12
    assert vendor.describe(Git(project)) == (V12, git(project, "rev-list", "--max-parents=0", "HEAD"))
    # The worktree is gone and the project's own checkout never moved.
    assert not (tmp_path / "wt").exists()
    assert git(project, "rev-parse", "--abbrev-ref", "HEAD") == "main"
    assert (project / "ruff.toml").read_text() == "line-length = 88\n"


def test_commit_is_allowed_to_be_empty_so_the_version_is_recorded(
    project: Path, tmp_path: Path
) -> None:
    repo = Git(project)
    vendor.ensure(repo, V10, V12)
    unchanged = project.parent / "same"
    unchanged.mkdir()
    for name in (".pyfr-answers.yml", "README.md", "ruff.toml", "old.txt"):
        (unchanged / name).write_text((project / name).read_text())
    (unchanged / "src/pkg/domain").mkdir(parents=True)
    (unchanged / "src/pkg/domain/order.py").write_text("class Order: ...\n")
    with vendor.worktree(repo, tmp_path / "wt") as worktree:
        vendor.sync(unchanged, worktree, IGNORE)
        sha = vendor.commit(worktree, V10, V12)
    assert vendor.trailer_version(repo, sha) == V12
    assert git(project, "diff", "--stat", f"{sha}~1", sha) == ""


def test_push_publishes_the_branch_and_ensure_fetches_it_elsewhere(
    project: Path, rendered: Path, tmp_path: Path
) -> None:
    sha = update_branch(project, rendered, tmp_path)
    vendor.push(Git(project))
    assert git(project, "rev-parse", "origin/template") == sha
    # A second machine: a fresh clone with no local template branch.
    clone = tmp_path / "clone"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(clone))
    git(clone, "config", "user.name", "Test")
    git(clone, "config", "user.email", "test@example.com")
    branch = vendor.ensure(Git(clone), V10, V12)
    assert not branch.created
    assert branch.version == V12
    assert git(clone, "rev-parse", "template") == sha


def test_push_without_a_remote_is_an_error_naming_no_push(tmp_path: Path) -> None:
    repo = make_repo(tmp_path / "lonely", {".pyfr-answers.yml": answers_text("0.10.0")})
    with pytest.raises(UpdateError) as stop:
        vendor.push(Git(repo))
    assert "--no-push" in stop.value.fix


def test_ensure_refuses_diverged_local_and_remote_branches(
    project: Path, rendered: Path, tmp_path: Path
) -> None:
    update_branch(project, rendered, tmp_path)
    vendor.push(Git(project))
    # Someone rewinds the local branch and commits something else on it.
    root = git(project, "rev-list", "--max-parents=0", "HEAD")
    git(project, "branch", "--force", "template", root)
    git(project, "worktree", "add", "-q", str(tmp_path / "wt2"), "template")
    (tmp_path / "wt2" / "stray.txt").write_text("x\n")
    commit_all(tmp_path / "wt2", "stray")
    git(project, "worktree", "remove", "--force", str(tmp_path / "wt2"))
    with pytest.raises(UpdateError) as stop:
        vendor.ensure(Git(project), V12, Version(0, 13, 0))
    assert "diverged" in stop.value.cause


def test_guard_refuses_a_hand_made_commit_on_top_of_the_tool_s(
    project: Path, rendered: Path, tmp_path: Path
) -> None:
    update_branch(project, rendered, tmp_path)
    git(project, "worktree", "add", "-q", str(tmp_path / "wt2"), "template")
    (tmp_path / "wt2" / "ruff.toml").write_text("hand edit\n")
    commit_all(tmp_path / "wt2", "tweak the template by hand")
    git(project, "worktree", "remove", "--force", str(tmp_path / "wt2"))
    with pytest.raises(UpdateError) as stop:
        vendor.ensure(Git(project), V12, Version(0, 13, 0))
    assert "was not made by pyfr update" in stop.value.cause
    assert "tweak the template by hand" in stop.value.cause
    assert "git branch --force template" in stop.value.fix


def test_a_re_pointed_branch_is_accepted_with_its_answers_file_version(
    project: Path,
) -> None:
    # The manual procedure after a rewritten history: point `template` at a
    # commit that carries an answers file and no tool commits.
    (project / ".pyfr-answers.yml").write_text(answers_text("0.11.0"))
    (project / "ruff.toml").write_text("line-length = 90\n")
    later = commit_all(project, "chore: pretend this is v0.11.0 output")
    git(project, "branch", "template", later)
    branch = vendor.ensure(Git(project), Version(0, 11, 0), V12)
    assert (branch.version, branch.base) == (Version(0, 11, 0), later)


def test_a_base_without_an_answers_file_is_an_error(project: Path) -> None:
    git(project, "rm", "-q", ".pyfr-answers.yml")
    commit_all(project, "drop the answers")
    git(project, "branch", "template", "HEAD")
    with pytest.raises(UpdateError) as stop:
        vendor.ensure(Git(project), V10, V12)
    assert "has no .pyfr-answers.yml" in stop.value.cause


def test_commit_for_finds_the_commit_that_renders_a_version(
    project: Path, rendered: Path, tmp_path: Path
) -> None:
    repo = Git(project)
    root = git(project, "rev-parse", "HEAD")
    sha = update_branch(project, rendered, tmp_path)
    assert vendor.commit_for(repo, V12, root) == sha
    assert vendor.commit_for(repo, V10, root) == root
    with pytest.raises(UpdateError, match="no commit for v0.11.0"):
        vendor.commit_for(repo, Version(0, 11, 0), root)
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --group dev pytest tests/cli/test_vendor.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli.vendor'`.

- [ ] **Step 3: Implement**

`src/pyfr_cli/vendor.py`:

```python
"""The `template` branch: pristine rendered output and nothing else.

Every update's merge base lives here (spec section 4.3). The branch is
kept on the remote and pushed before every merge, and every commit the
tool makes on it carries the Pyfr-Template-Version trailer -- a
`Key: value` line at the end of the message -- so the tool can tell its
own commits from anyone else's.
"""

from __future__ import annotations

import shutil
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from pyfr_cli import answers
from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git
from pyfr_cli.ignore import Ignore
from pyfr_cli.versions import Version

BRANCH = "template"
REMOTE = "origin"
TRAILER = "Pyfr-Template-Version"
GUIDE = answers.GUIDE


@dataclass
class Branch:
    version: Version  # what the branch's tip renders
    base: str  # the first commit on it that the tool did not make
    created: bool
    notes: list[str] = field(default_factory=list)  # lines for the user


def trailer_version(git: Git, rev: str) -> Version | None:
    text = git.out(
        "show", "--no-patch", f"--format=%(trailers:key={TRAILER},valueonly)", rev
    )
    if not text:
        return None
    try:
        return Version.parse(text.splitlines()[0])
    except ValueError as exc:
        raise UpdateError(
            f"{BRANCH} commit {rev[:12]} has a broken {TRAILER} trailer: {exc}",
            f"see {GUIDE} for re-pointing the branch",
        ) from exc


def recorded_in(git: Git, rev: str) -> Version | None:
    """The _template_version of the answers file at `rev`, if it has one."""
    result = git.run("show", f"{rev}:{answers.FILE}", check=False)
    if result.returncode != 0:
        return None
    return answers.version_in(result.stdout)


def ensure(git: Git, recorded: Version, target: Version) -> Branch:
    """Find, fetch or create the branch, then check the guard.

    In order: the remote's branch wins when it exists; a local one is used
    (and pushed later) when it does not; otherwise the single root commit
    starts it (spec section 4.3).
    """
    notes: list[str] = []
    created = False
    # A run that died may have left a worktree entry behind.
    git.run("worktree", "prune")
    on_remote = git.remote_exists(REMOTE) and git.ok(
        "ls-remote", "--exit-code", "--heads", REMOTE, BRANCH
    )
    if on_remote:
        git.run("fetch", "--quiet", REMOTE, BRANCH)
        if not git.branch_exists(BRANCH):
            git.run("branch", BRANCH, "FETCH_HEAD")
        elif git.ok("merge-base", "--is-ancestor", BRANCH, "FETCH_HEAD"):
            git.run("branch", "--force", BRANCH, "FETCH_HEAD")
        elif not git.ok("merge-base", "--is-ancestor", "FETCH_HEAD", BRANCH):
            raise UpdateError(
                f"the local {BRANCH} branch and {REMOTE}/{BRANCH} have diverged",
                f"git branch --force {BRANCH} {REMOTE}/{BRANCH} keeps the "
                f"remote's, which every other machine uses; see {GUIDE}",
            )
        # Otherwise the local branch is ahead -- a --no-push run -- and the
        # push at the end of this run carries it.
    elif git.branch_exists(BRANCH):
        notes.append(f"{BRANCH}: exists locally but not on {REMOTE}; it will be pushed")
    else:
        roots = git.root_commits()
        if len(roots) != 1:
            raise UpdateError(
                f"the repository has {len(roots)} root commits, so the {BRANCH} "
                "branch cannot be created from the one that is template output",
                f"create it by hand: git branch {BRANCH} <that commit>; see {GUIDE}",
            )
        git.run("branch", BRANCH, roots[0])
        created = True
        notes.append(
            f'{BRANCH}: created from root commit {roots[0][:12]} "{git.subject(roots[0])}"'
        )
    version, base = describe(git)
    if version not in (recorded, target):
        raise UpdateError(
            f"{BRANCH} is at {version}, but {answers.FILE} records {recorded}",
            f"the two must agree; see {GUIDE} for re-pointing the branch",
        )
    return Branch(version, base, created, notes)


def describe(git: Git) -> tuple[Version, str]:
    """The branch's version and its base commit, checking the guard.

    Walking from the tip, every commit down to the first without the
    trailer must carry it; that first commit is the base. A tip without a
    trailer is the base itself -- the root, or a deliberate re-point --
    unless tool commits lie below it: then someone committed on top of
    them by hand, and the branch is refused (spec section 4.3).
    """
    shas = git.out("rev-list", BRANCH).split()
    tip_version: Version | None = None
    base = shas[-1]
    for sha in shas:
        version = trailer_version(git, sha)
        if version is None:
            base = sha
            break
        if tip_version is None:
            tip_version = version
    if tip_version is not None:
        return tip_version, base
    below = git.out("log", "--format=%H", f"--grep=^{TRAILER}: ", base).split()
    if below:
        raise UpdateError(
            f'{BRANCH}\'s tip {base[:12]} "{git.subject(base)}" was not made by '
            "pyfr update",
            f"git branch --force {BRANCH} {below[0][:12]} points it back at the "
            f"last commit pyfr update made; see {GUIDE}",
        )
    version = recorded_in(git, base)
    if version is None:
        raise UpdateError(
            f"{BRANCH}'s base commit {base[:12]} has no {answers.FILE}",
            f"point {BRANCH} at a commit that has one: git branch --force "
            f"{BRANCH} <commit>; see {GUIDE}",
        )
    return version, base


def commit_for(git: Git, version: Version, base: str) -> str:
    """The commit on the branch that renders `version`: the tool commit
    whose trailer names it, or the base when the base's answers file does."""
    for sha in git.out("rev-list", BRANCH).split():
        if sha == base:
            break
        if trailer_version(git, sha) == version:
            return sha
    if recorded_in(git, base) == version:
        return base
    raise UpdateError(
        f"{BRANCH} has no commit for {version}",
        f"the branch and {answers.FILE} disagree; see {GUIDE}",
    )


@contextmanager
def worktree(git: Git, path: Path) -> Iterator[Git]:
    """The branch checked out in `path`; removed afterwards, whatever happens."""
    git.run("worktree", "add", "--quiet", str(path), BRANCH)
    try:
        yield Git(path)
    finally:
        git.run("worktree", "remove", "--force", str(path), check=False)


def sync(rendered: Path, worktree: Git, ignore: Ignore) -> None:
    """Make the worktree's tree the render's, except for ignored paths.

    Every rendered file is copied over (with its mode: scripts keep their
    executable bit); every tracked file the render does not produce is
    deleted; both steps skip what `ignore` matches, so the template side
    never changes those paths and the merge never forms an opinion about
    them (spec section 4.5). Then everything is staged.
    """
    root = worktree.cwd
    wanted = {
        path.relative_to(rendered).as_posix(): path
        for path in rendered.rglob("*")
        if path.is_file()
    }
    for relative, source in wanted.items():
        if ignore.matches(relative):
            continue
        target = root / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(source, target)
    for relative in worktree.out("ls-files", "-z").split("\0"):
        if not relative or relative in wanted or ignore.matches(relative):
            continue
        stale = root / relative
        if stale.exists():
            stale.unlink()
        parent = stale.parent
        while parent != root and parent.is_dir() and not any(parent.iterdir()):
            parent.rmdir()
            parent = parent.parent
    worktree.run("add", "--all")


def commit(worktree: Git, previous: Version, target: Version) -> str:
    """`chore: template vA -> vB` with the trailer; allowed to be empty, so the
    version is recorded even when nothing in the body changed for these
    answers."""
    message = f"chore: template {previous} -> {target}\n\n{TRAILER}: {target}\n"
    return worktree.commit(message, allow_empty=True)


def push(git: Git) -> None:
    if not git.remote_exists(REMOTE):
        raise UpdateError(
            f"there is no {REMOTE} remote to push the {BRANCH} branch to",
            "add one (git remote add origin <url>), or pass --no-push",
        )
    result = git.run("push", "--quiet", REMOTE, f"{BRANCH}:{BRANCH}", check=False)
    if result.returncode != 0:
        raise UpdateError(
            f"pushing {BRANCH} to {REMOTE} failed: {result.stderr.strip()}",
            "check your access to the remote, then run pyfr update again -- "
            "the local branch is correct and the run resumes",
        )
```

- [ ] **Step 4: Run the tests**

Run: `uv run --group dev pytest tests/cli/test_vendor.py -v && just lint`
Expected: all PASS; clean. If `ruff` flags the lambda in the sync test (`E731` is silenced inline) or asks to reformat long strings, accept its formatting.

- [ ] **Step 5: Commit**

```bash
git add src/pyfr_cli/vendor.py tests/cli/test_vendor.py
git commit -m "feat(pyfr-cli): manage the template branch

Find or create it, guard it against hand-made commits, sync a render
into it under the ignore list, commit with the version trailer, push.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 10: `migrate.py` — `updates/<version>/before.py` and `after.py`

**Files:**
- Create: `src/pyfr_cli/migrate.py`
- Create: `updates/README.md`
- Test: `tests/cli/test_migrate.py`

**Interfaces:**
- Produces: `Migration(version: Version, before: Path | None, after: Path | None)`; `discover(clone: Path, after: Version, up_to: Version) -> list[Migration]` (versions in `(after, up_to]`, ascending); `run_before(migrations, project: Path, from_version, to_version, out: TextIO) -> None`; `run_after(...)` same signature; `run_script(script: Path, project: Path, from_version, to_version, out) -> None`.

Scripts run as `uv run --no-project python <script>`: they are standard-library only by contract, so no project environment is needed — and `uv run` *with* the project would first sync the project's dependencies, which is slow and fails in a fresh checkout. `--no-project` still honours the project's `.python-version`.

- [ ] **Step 1: Write the failing tests**

`tests/cli/test_migrate.py`:

```python
"""updates/<version>/: which scripts run for an update, and how."""

from __future__ import annotations

import io
from pathlib import Path

import pytest

from pyfr_cli import migrate
from pyfr_cli.errors import UpdateError
from pyfr_cli.versions import Version

MARK = """\
import os
import pathlib

NAME = "{name}"
log = pathlib.Path("migrations.log")
existing = log.read_text() if log.exists() else ""
line = f"{{os.environ['PYFR_UPDATE_FROM']}}->{{os.environ['PYFR_UPDATE_TO']}} {{NAME}}\\n"
# Idempotent: a second run leaves the log as it is.
if line not in existing:
    with log.open("a") as handle:
        handle.write(line)
print("hello from", NAME)
"""
FAIL = "import sys\nsys.exit('the schema is not what I expected')\n"


def script(clone: Path, version: str, name: str, text: str) -> Path:
    path = clone / "updates" / version / f"{name}.py"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


@pytest.fixture
def clone(tmp_path: Path) -> Path:
    root = tmp_path / "clone"
    (root / "updates").mkdir(parents=True)
    (root / "updates" / "README.md").write_text("the contract\n")
    script(root, "v1.1.0", "before", MARK.format(name="v1.1.0/before"))
    script(root, "v1.1.0", "after", MARK.format(name="v1.1.0/after"))
    script(root, "v1.2.0", "after", MARK.format(name="v1.2.0/after"))
    script(root, "v1.10.0", "before", MARK.format(name="v1.10.0/before"))
    script(root, "v2.0.0", "before", MARK.format(name="v2.0.0/before"))
    script(root, "1.3.0", "before", FAIL)  # no v: not a migration directory
    (root / "updates" / "notes.txt").write_text("not a directory\n")
    return root


@pytest.fixture
def project(tmp_path: Path) -> Path:
    root = tmp_path / "project"
    root.mkdir()
    (root / ".python-version").write_text("3.13\n")
    return root


def test_discover_takes_the_half_open_range_in_numeric_order(clone: Path) -> None:
    found = migrate.discover(clone, Version(1, 0, 0), Version(1, 10, 0))
    assert [m.version for m in found] == [
        Version(1, 1, 0),
        Version(1, 2, 0),
        Version(1, 10, 0),
    ]
    assert found[0].before is not None and found[0].after is not None
    assert found[1].before is None and found[1].after is not None
    assert found[2].after is None


def test_discover_is_empty_without_an_updates_directory(tmp_path: Path) -> None:
    assert migrate.discover(tmp_path, Version(0, 1, 0), Version(9, 0, 0)) == []


def test_run_before_and_after_run_their_scripts_in_order_with_the_env(
    clone: Path, project: Path
) -> None:
    found = migrate.discover(clone, Version(1, 0, 0), Version(1, 10, 0))
    out = io.StringIO()
    migrate.run_before(found, project, Version(1, 0, 0), Version(1, 10, 0), out)
    migrate.run_after(found, project, Version(1, 0, 0), Version(1, 10, 0), out)
    assert (project / "migrations.log").read_text() == (
        "v1.0.0->v1.10.0 v1.1.0/before\n"
        "v1.0.0->v1.10.0 v1.10.0/before\n"
        "v1.0.0->v1.10.0 v1.1.0/after\n"
        "v1.0.0->v1.10.0 v1.2.0/after\n"
    )
    text = out.getvalue()
    assert "migrations: v1.1.0/before.py" in text
    assert "hello from v1.2.0/after" in text


def test_a_failing_script_stops_the_update_with_its_message(
    clone: Path, project: Path
) -> None:
    script(clone, "v1.5.0", "before", FAIL)
    found = migrate.discover(clone, Version(1, 4, 0), Version(1, 5, 0))
    with pytest.raises(UpdateError) as stop:
        migrate.run_before(found, project, Version(1, 4, 0), Version(1, 5, 0), io.StringIO())
    assert "v1.5.0/before.py failed" in stop.value.cause
    assert "the schema is not what I expected" in stop.value.cause
    assert "git reset --hard HEAD" in stop.value.fix
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --group dev pytest tests/cli/test_migrate.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli.migrate'`.

- [ ] **Step 3: Implement**

`src/pyfr_cli/migrate.py`:

```python
"""Migration scripts: updates/<version>/before.py and after.py in the template.

Some template changes cannot be expressed as a merge -- a file that moves,
a setting that changes shape. For each version in (recorded, target] the
template may ship a `before.py`, run on the project's tree before the
merge, and an `after.py`, run after it (spec section 6; updates/README.md
is the contract for the scripts' authors).
"""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from pyfr_cli.errors import UpdateError
from pyfr_cli.versions import Version


@dataclass(frozen=True)
class Migration:
    version: Version
    before: Path | None
    after: Path | None


def discover(clone: Path, after: Version, up_to: Version) -> list[Migration]:
    """The migrations for versions in (after, up_to], oldest first."""
    updates = clone / "updates"
    if not updates.is_dir():
        return []
    found: list[Migration] = []
    for entry in updates.iterdir():
        if not entry.is_dir():
            continue
        try:
            version = Version.parse(entry.name)
        except ValueError:
            continue
        # Exactly vX.Y.Z: the v is required, and no zero padding.
        if entry.name != str(version) or not after < version <= up_to:
            continue
        before, after_script = entry / "before.py", entry / "after.py"
        found.append(
            Migration(
                version,
                before if before.is_file() else None,
                after_script if after_script.is_file() else None,
            )
        )
    return sorted(found, key=lambda migration: migration.version)


def run_script(
    script: Path,
    project: Path,
    from_version: Version,
    to_version: Version,
    out: TextIO,
) -> None:
    """One script, in the project root, with the update's versions in the
    environment. `--no-project`: scripts are standard-library only, and a
    project sync here would be slow and would fail in a fresh checkout."""
    label = f"{script.parent.name}/{script.name}"
    out.write(f"migrations: {label}\n")
    env = {
        **os.environ,
        "PYFR_UPDATE_FROM": str(from_version),
        "PYFR_UPDATE_TO": str(to_version),
    }
    result = subprocess.run(
        ["uv", "run", "--no-project", "python", str(script)],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
    )
    if result.stdout:
        out.write(result.stdout)
    if result.returncode != 0:
        raise UpdateError(
            f"{label} failed (exit {result.returncode}): {result.stderr.strip()}",
            "fix what it reports; `git reset --hard HEAD` reverts what it "
            "changed, then run pyfr update again",
        )


def run_before(
    migrations: list[Migration],
    project: Path,
    from_version: Version,
    to_version: Version,
    out: TextIO,
) -> None:
    for migration in migrations:
        if migration.before is not None:
            run_script(migration.before, project, from_version, to_version, out)


def run_after(
    migrations: list[Migration],
    project: Path,
    from_version: Version,
    to_version: Version,
    out: TextIO,
) -> None:
    for migration in migrations:
        if migration.after is not None:
            run_script(migration.after, project, from_version, to_version, out)
```

- [ ] **Step 4: Write the contract for script authors**

`updates/README.md`:

````markdown
# Migration scripts

Some template changes cannot be expressed as a merge: a file that moves, a
setting that changes shape. When a release needs one, it ships a directory
here named after the version, and `pyfr update` runs its scripts for every
version greater than the project's recorded one and not greater than the
target, in ascending order.

```
updates/
  v0.13.0/
    before.py   # runs on the project's tree before the merge
    after.py    # runs after the merge is committed
```

Either file may be absent. Nothing here is rendered into a project:
`updates/` sits outside `{{cookiecutter.project_slug}}/`.

## The contract

- **Where and how they run.** `uv run --no-project python <script>`, with
  the project root as the working directory and `PYFR_UPDATE_FROM` and
  `PYFR_UPDATE_TO` (with the `v`, for example `v0.12.0`) in the
  environment. `--no-project` means the project's own dependencies are not
  installed first: **standard library only.**
- **`before.py`** makes the merge line up — typically `git mv` through
  `subprocess`, so a file the template moved is moved in the project too
  and git merges the two renames as one file. It may edit files. `pyfr
  update` commits what it leaves staged or modified as
  `chore: prepare for template <target>`; a new file must be `git add`ed
  by the script itself.
- **`after.py`** rewrites contents once the template's version of a file
  is in place. `pyfr update` commits what it changed as
  `chore: finish template <target>`.
- **Idempotent.** Running a script twice must equal running it once: a
  failed update is re-run, and a script that already did its work exits 0
  without doing it again. Check before you act (`if dst.exists(): exit(0)`).
- **Exit non-zero to stop the update.** Whatever the script prints to
  stderr is shown to the user, followed by "`git reset --hard HEAD` reverts
  what it changed".
- **A deleted file is not an error.** Teams delete example files; a script
  that finds its target missing exits 0.

## Testing one

`tests/test_update_e2e.py` builds a two-version template in a temporary
directory, with fixture scripts under `updates/v100.1.0/`, and asserts the
project's tree after the update. Copy that pattern: generate at the
previous version, edit the project the way a team would, update, assert.
````

- [ ] **Step 5: Run the tests**

Run: `uv run --group dev pytest tests/cli/test_migrate.py -v && just lint`
Expected: all PASS; clean. (Each script runs through `uv run --no-project`; the first call may download the pinned Python if the machine lacks it.)

- [ ] **Step 6: Commit**

```bash
git add src/pyfr_cli/migrate.py tests/cli/test_migrate.py updates/README.md
git commit -m "feat(pyfr-cli): run the template's migration scripts

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 11: `update.py` — `check()`, and the `pyfr` subcommands

**Files:**
- Create: `src/pyfr_cli/update.py` (with `check()` and the full `update()` — the latter is exercised by Tasks 12 and 13)
- Modify: `src/pyfr_cli/__main__.py`
- Test: `tests/cli/test_main.py` (extend), `tests/cli/test_update.py` (preconditions and the cheap paths of `update()`)

**Interfaces:**
- Produces: `Options(to: str | None = None, push: bool = True, template: str | None = None)`; `check(project: Path, options: Options, out: TextIO, *, as_json: bool = False) -> int`; `update(project: Path, options: Options, out: TextIO) -> int`; `CONFLICT_HELP: str`. `main(["update", …])` and `main(["update-check", …])` call them with `Path.cwd()` and `sys.stdout`.
- Output lines with stable prefixes (spec 3.2): `template: …`, `render: new prompt <name> defaulted to <value>`, `ignore: …`, `migrations: …`, `commit: …`, `merge: …`, `conflict: <path>`, `resume: …`, `recorded: <version>`, `already current at <version>`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/cli/test_main.py`:

```python


def test_update_check_reports_the_versions_and_exits_by_state(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    from cli.helpers import git, make_repo

    template = make_repo(tmp_path / "template")
    git(template, "tag", "v0.10.0")
    project = tmp_path / "project"
    project.mkdir()
    (project / ".pyfr-answers.yml").write_text(
        f'_template: {template}\n_template_version: "0.10.0"\n'
    )
    monkeypatch.chdir(project)

    assert main(["update-check"]) == 0
    assert capsys.readouterr().out == "recorded v0.10.0, newest v0.10.0\n"

    git(template, "tag", "v0.11.0")
    assert main(["update-check", "--json"]) == 1
    assert json.loads(capsys.readouterr().out) == {
        "recorded": "v0.10.0",
        "newest": "v0.11.0",
        "behind": True,
        "template": str(template),
    }
    # --template overrides the recorded URL.
    other = make_repo(tmp_path / "other")
    git(other, "tag", "v0.10.0")
    assert main(["update-check", "--template", str(other)]) == 0


def test_an_error_is_two_lines_on_stderr_and_exit_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.chdir(tmp_path)
    assert main(["update-check"]) == 2
    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err.startswith("error: .pyfr-answers.yml not found in ")
    assert "\n  fix: run from the project root" in captured.err


def test_pyfr_debug_re_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from pyfr_cli.errors import UpdateError

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYFR_DEBUG", "1")
    with pytest.raises(UpdateError):
        main(["update-check"])


def test_a_subcommand_is_required() -> None:
    with pytest.raises(SystemExit) as stop:
        main([])
    assert stop.value.code == 2
```

and add `import json` and `from pathlib import Path` to that file's imports.

Create `tests/cli/test_update.py`:

```python
"""`update()` before it touches the network or the template: preconditions
and the cheap answers. The full flow is tests/test_update_e2e.py."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
from cli.helpers import commit_all, git, make_repo

from pyfr_cli import update
from pyfr_cli.errors import UpdateError


@pytest.fixture
def template(tmp_path: Path) -> Path:
    remote = make_repo(tmp_path / "template")
    git(remote, "tag", "v0.9.0")
    (remote / "README.md").write_text("v0.10.0\n")
    commit_all(remote, "feat: more")
    git(remote, "tag", "v0.10.0")
    return remote


@pytest.fixture
def project(tmp_path: Path, template: Path) -> Path:
    return make_repo(
        tmp_path / "project",
        {".pyfr-answers.yml": f'_template: {template}\n_template_version: "0.10.0"\n'},
    )


def run(project: Path, **options: object) -> tuple[int, str]:
    out = io.StringIO()
    code = update.update(project, update.Options(**options), out)  # type: ignore[arg-type]
    return code, out.getvalue()


def refused(project: Path, cause: str, **options: object) -> UpdateError:
    with pytest.raises(UpdateError) as stop:
        run(project, **options)
    assert cause in stop.value.cause, stop.value.cause
    return stop.value


def test_already_current(project: Path) -> None:
    assert run(project) == (0, "already current at v0.10.0\n")


def test_a_downgrade_is_refused(project: Path) -> None:
    error = refused(project, "v0.9.0 is older than the recorded v0.10.0", to="v0.9.0")
    assert "downgrades are not supported" in error.fix


def test_an_unknown_target_is_refused(project: Path) -> None:
    refused(project, "no tag v3.0.0", to="3.0.0")


def test_not_a_repository(tmp_path: Path, template: Path) -> None:
    loose = tmp_path / "loose"
    loose.mkdir()
    (loose / ".pyfr-answers.yml").write_text(f'_template: {template}\n_template_version: "0.10.0"\n')
    refused(loose, "not inside a git repository")


def test_must_run_at_the_repository_root(project: Path) -> None:
    sub = project / "src"
    sub.mkdir()
    (sub / ".pyfr-answers.yml").write_text((project / ".pyfr-answers.yml").read_text())
    refused(sub, "is not the repository root")


def test_a_detached_head_is_refused(project: Path) -> None:
    git(project, "checkout", "-q", "--detach")
    refused(project, "HEAD is detached")


def test_a_missing_identity_is_refused(project: Path) -> None:
    git(project, "config", "--unset", "user.email")
    error = refused(project, "no user.name or user.email")
    assert "git config user.email" in error.fix


def test_uncommitted_tracked_changes_are_refused_but_untracked_files_are_fine(
    project: Path,
) -> None:
    (project / "notes.txt").write_text("untracked\n")
    assert run(project)[0] == 0
    (project / "README.md").write_text("edited\n")
    refused(project, "uncommitted changes")


def test_a_merge_in_progress_that_is_not_ours_is_refused(project: Path) -> None:
    git(project, "branch", "other")
    (project / "README.md").write_text("ours\n")
    commit_all(project, "ours")
    git(project, "switch", "-q", "other")
    (project / "README.md").write_text("theirs\n")
    commit_all(project, "theirs")
    git(project, "switch", "-q", "main")
    assert not update.Git(project).ok("merge", "other")
    error = refused(project, "a merge is in progress")
    assert "git merge --abort" in error.fix
```

- [ ] **Step 2: Run them to verify they fail**

Run: `uv run --group dev pytest tests/cli/test_main.py tests/cli/test_update.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'pyfr_cli.update'`, and the `main` tests fail on the missing subcommands.

- [ ] **Step 3: Implement `update.py`**

`src/pyfr_cli/update.py` — the whole module; Tasks 12 and 13 test the parts this task's tests do not reach:

```python
"""`pyfr update` and `pyfr update-check`: spec section 4, step by step."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from pyfr_cli import answers, changelog, ignore, migrate, render, state, vendor, versions
from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git, require_tools
from pyfr_cli.versions import Version

CONFLICT_HELP = """\
merge: conflicts in the files above
  1. resolve them, then stage them:  git add <the files>
  2. commit the merge:               git commit   (the message is prepared)
  3. run the same command again:     pyfr update  (runs what is left)
"""


@dataclass(frozen=True)
class Options:
    to: str | None = None
    push: bool = True
    template: str | None = None


def check(
    project: Path, options: Options, out: TextIO, *, as_json: bool = False
) -> int:
    """`pyfr update-check`: 0 when current, 1 when behind, 2 on error."""
    require_tools("git")
    recorded = answers.load(project)
    template = options.template or recorded.template
    newest = versions.remote_versions(template, Git(project))[-1]
    behind = recorded.version < newest
    if as_json:
        record = {
            "recorded": str(recorded.version),
            "newest": str(newest),
            "behind": behind,
            "template": template,
        }
        out.write(json.dumps(record) + "\n")
    else:
        out.write(f"recorded {recorded.version}, newest {newest}\n")
    return 1 if behind else 0


def update(project: Path, options: Options, out: TextIO) -> int:
    """`pyfr update`: 0 when updated or current, 1 when a merge waits for
    the user, 2 on error (raised as UpdateError)."""
    require_tools("git", "uv")
    git = Git(project)
    _preconditions(git, project)
    recorded = answers.load(project)
    template = options.template or recorded.template

    pending = state.load(git)
    if pending is not None:
        _ungraft(git, pending)
        resumed = _resume(git, project, recorded, template, pending, out)
        if resumed is not None:
            return resumed

    operation = git.operation_in_progress()
    if operation is not None:
        raise UpdateError(
            f"a {operation} is in progress",
            f"finish it, or abort it with git {operation} --abort, then run again",
        )
    if git.has_tracked_changes():
        raise UpdateError(
            "the working tree has uncommitted changes",
            "commit or discard them first: a clean tree is what makes every "
            "step of the update reversible with git reset --hard HEAD",
        )

    available = versions.remote_versions(template, git)
    target = versions.resolve_target(options.to, available)
    if target == recorded.version:
        out.write(f"already current at {target}\n")
        return 0
    if target < recorded.version:
        raise UpdateError(
            f"{target} is older than the recorded {recorded.version}",
            "downgrades are not supported; pass a newer --to, or none for the newest",
        )

    branch = vendor.ensure(git, recorded.version, target)
    for note in branch.notes:
        out.write(f"{note}\n")
    # The merge base: the template commit that renders the recorded version.
    previous = vendor.commit_for(git, recorded.version, branch.base)

    with tempfile.TemporaryDirectory(prefix="pyfr-update-") as scratch:
        tmp = Path(scratch)
        clone = render.clone_template(template, target, tmp / "template", git)
        # Always rendered: step 10's answers file comes from it. The sync,
        # commit and push are skipped when the branch is already there.
        rendered = render.render(clone, target, recorded, tmp / "render")
        for name, value in rendered.defaulted.items():
            out.write(f"render: new prompt {name} defaulted to {value}\n")

        if branch.version == target:
            out.write(f"template: already at {target}\n")
        else:
            spec, from_file = ignore.load(project, recorded)
            if not from_file:
                out.write(f"ignore: no {ignore.FILE}; using the built-in default\n")
            with vendor.worktree(git, tmp / "worktree") as worktree:
                vendor.sync(rendered.project, worktree, spec)
                sha = vendor.commit(worktree, branch.version, target)
            out.write(f"template: committed {branch.version} -> {target} ({sha[:12]})\n")
            if options.push:
                vendor.push(git)
                out.write(f"template: pushed to {vendor.REMOTE}\n")
            else:
                out.write("template: not pushed (--no-push)\n")

        migrations = migrate.discover(clone, recorded.version, target)
        migrate.run_before(migrations, project, recorded.version, target, out)
        _commit_changes(git, f"chore: prepare for template {target}", out)

        body = _changelog(clone, recorded.version, target, template)
        clean = _merge(git, previous, body, recorded.version, target, out)
        # Step 10, clean or not: the answers file is an ignored path, so the
        # merge never touched it, and staged here it rides in the merge commit.
        answers.install(rendered.project, project)
        git.run("add", answers.FILE)
        if not clean:
            state.save(git, state.State(recorded.version, target, "merging"))
            out.write(CONFLICT_HELP)
            return 1
        git.run(
            "commit", "--quiet", "--no-verify",
            "--file", str(git.git_dir() / "MERGE_MSG"),
        )  # fmt: skip
        out.write(f"merge: clean, committed as {git.out('rev-parse', '--short=12', 'HEAD')}\n")
        state.save(git, state.State(recorded.version, target, "after-scripts"))
        _finish(git, project, migrations, recorded.version, target, out)

    out.write(f"recorded: {target}\n")
    return 0


def _preconditions(git: Git, project: Path) -> None:
    if not git.ok("rev-parse", "--git-dir"):
        raise UpdateError(
            f"{project} is not inside a git repository",
            "run pyfr update at the root of the generated project",
        )
    if git.toplevel() != project.resolve():
        raise UpdateError(
            f"{project} is not the repository root ({git.toplevel()} is)",
            "cd to the root and run again",
        )
    if git.current_branch() is None:
        raise UpdateError("HEAD is detached", "switch to a branch first: git switch main")
    if not git.has_identity():
        raise UpdateError(
            "git has no user.name or user.email configured",
            'git config user.name "Your Name" && git config user.email you@example.com',
        )


def _resume(
    git: Git,
    project: Path,
    recorded: answers.Answers,
    template: str,
    pending: state.State,
    out: TextIO,
) -> int | None:
    """A previous run stopped. Either the merge still waits (1), the merge is
    committed and the after-scripts remain (run them, 0), or the merge was
    aborted (clear the state and start over: None)."""
    if git.operation_in_progress() == "merge":
        for path in git.out("diff", "--name-only", "--diff-filter=U").splitlines():
            out.write(f"conflict: {path}\n")
        out.write(CONFLICT_HELP)
        return 1
    if recorded.version == pending.to_version:
        out.write(f"resume: finishing the update to {pending.to_version}\n")
        with tempfile.TemporaryDirectory(prefix="pyfr-update-") as scratch:
            clone = render.clone_template(
                template, pending.to_version, Path(scratch) / "template", git
            )
            migrations = migrate.discover(clone, pending.from_version, pending.to_version)
            _finish(git, project, migrations, pending.from_version, pending.to_version, out)
        out.write(f"recorded: {pending.to_version}\n")
        return 0
    state.clear(git)
    out.write("resume: the previous merge was aborted; starting over\n")
    return None


def _ungraft(git: Git, pending: state.State) -> None:
    """A run that died between grafting and un-grafting left a replacement
    ref behind; drop it before anything reads history."""
    if pending.graft is not None:
        git.run("replace", "--delete", pending.graft, check=False)


def _merge(
    git: Git,
    previous: str,
    body: str,
    recorded: Version,
    target: Version,
    out: TextIO,
) -> bool:
    """`git merge --no-ff --no-commit template` with its base pinned to
    `previous`, the template commit at the recorded version (spec 4.7).

    Git finds that base by itself only when `previous` is in HEAD's
    history. After a squash-merged update pull request it is not, so a
    temporary graft -- an extra parent, seen by git but not written into
    the commit -- makes it the base; the graft is deleted right after the
    merge, whatever happened. Returns True when the merge is clean.
    """
    grafted: str | None = None
    if not git.ok("merge-base", "--is-ancestor", previous, "HEAD"):
        head = git.out("rev-parse", "HEAD")
        parents = git.out("rev-parse", f"{head}^@").split()
        state.save(git, state.State(recorded, target, "merging", graft=head))
        git.run("replace", "--graft", head, *parents, previous)
        grafted = head
        out.write(
            f"merge: base pinned to template commit {previous[:12]} "
            "(the last update was squash-merged)\n"
        )
    try:
        result = git.run("merge", "--no-ff", "--no-commit", vendor.BRANCH, check=False)
    finally:
        if grafted is not None:
            git.run("replace", "--delete", grafted, check=False)
    message = f"chore: update template {recorded} -> {target}\n"
    if body:
        message += f"\n{body}"
    (git.git_dir() / "MERGE_MSG").write_text(message)
    if result.returncode == 0:
        return True
    if git.operation_in_progress() != "merge":
        # Refused before it started: untracked files in the way, typically.
        raise UpdateError(
            f"git merge could not start: {result.stderr.strip()}",
            "move the files it names out of the way, then run again",
        )
    for path in git.out("diff", "--name-only", "--diff-filter=U").splitlines():
        out.write(f"conflict: {path}\n")
    return False


def _commit_changes(git: Git, message: str, out: TextIO) -> None:
    """Commit what the migration scripts changed in tracked files, if anything."""
    git.run("add", "--update")
    if git.has_staged_changes():
        sha = git.commit(message)
        out.write(f"commit: {message} ({sha[:12]})\n")


def _finish(
    git: Git,
    project: Path,
    migrations: list[migrate.Migration],
    recorded: Version,
    target: Version,
    out: TextIO,
) -> None:
    migrate.run_after(migrations, project, recorded, target, out)
    _commit_changes(git, f"chore: finish template {target}", out)
    state.clear(git)


def _changelog(clone: Path, after: Version, up_to: Version, template: str) -> str:
    file = clone / "CHANGELOG.md"
    if not file.is_file():
        return ""
    return changelog.entries(file.read_text(), after, up_to, template)
```

- [ ] **Step 4: Wire the subcommands**

Replace `src/pyfr_cli/__main__.py` with:

```python
"""The `pyfr` command."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Sequence
from pathlib import Path

from pyfr_cli import __version__, update
from pyfr_cli.errors import UpdateError

TEMPLATE_HELP = "the template repository (default: _template in .pyfr-answers.yml)"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pyfr",
        description="Keep a project generated from PyFr up to date with the template.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    commands = parser.add_subparsers(dest="command", required=True)

    run = commands.add_parser(
        "update", help="pull in a newer template version through a git merge"
    )
    run.add_argument(
        "--to", metavar="VERSION", help="the version to update to (default: the newest)"
    )
    run.add_argument(
        "--no-push",
        action="store_true",
        help="do not push the template branch to origin (the next run will)",
    )
    run.add_argument("--template", metavar="URL", help=TEMPLATE_HELP)

    check = commands.add_parser(
        "update-check", help="exit 1 when a newer template version exists"
    )
    check.add_argument(
        "--json", action="store_true", help="print a JSON object instead of a sentence"
    )
    check.add_argument("--template", metavar="URL", help=TEMPLATE_HELP)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    project = Path.cwd()
    try:
        if args.command == "update":
            options = update.Options(
                to=args.to, push=not args.no_push, template=args.template
            )
            return update.update(project, options, sys.stdout)
        options = update.Options(template=args.template)
        return update.check(project, options, sys.stdout, as_json=args.json)
    except UpdateError as exc:
        if os.environ.get("PYFR_DEBUG"):
            raise
        print(f"error: {exc.cause}", file=sys.stderr)
        print(f"  fix: {exc.fix}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 5: Run the tests**

Run: `uv run --group dev pytest tests/cli -v && just lint`
Expected: all PASS; clean. The `test_update.py` fixture's `# type: ignore[arg-type]` is for mypy's view of `**options: object`; ruff does not run mypy on tests, so it is only documentation — remove it if `just lint` complains about an unused ignore.

- [ ] **Step 6: Commit**

```bash
git add src/pyfr_cli/update.py src/pyfr_cli/__main__.py tests/cli/test_main.py tests/cli/test_update.py
git commit -m "feat(pyfr-cli): add pyfr update and pyfr update-check

The update runs spec section 4 in order: preconditions, target, the
template branch, render, sync, migrations, a merge whose base is pinned
to the template commit at the recorded version, and the record. A
paused run resumes with the same command.

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 12: End-to-end — the clean update, and what stays local

**Files:**
- Create: `tests/test_update_e2e.py` (fixtures and the first five scenarios; Task 13 adds three more)

**Interfaces:**
- Consumes: `pyfr_cli.__main__.main`, `cli.helpers.git/commit_all`, the real template body, `cookiecutter`.
- Produces (fixtures other tests in this file use): `template_remote` (module scope: a git repository with tags `v100.0.0`, `v100.1.0`, `v100.2.0`), `project` (function scope: rendered at `v100.0.0`, one commit, pushed to a bare `origin`, then the team's first week committed), `run(project, monkeypatch, capsys, *args) -> tuple[int, str, str]`.

- [ ] **Step 1: Write the fixtures and the first scenarios**

`tests/test_update_e2e.py`:

```python
"""pyfr update, end to end, against the real template body -- no network.

A local template remote stands in for github.com: this checkout's
cookiecutter.json, hooks/ and template body, committed and tagged
v100.0.0, then changed twice and tagged v100.1.0 and v100.2.0. A project is
rendered at v100.0.0 the way Backstage's publish action leaves one (one
commit, no `uv sync`), given a bare origin, and edited the way every team
edits a new service in its first week. Then it updates (spec section 8.2).
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml
from cli.helpers import commit_all, git

from pyfr_cli.__main__ import main

ROOT = Path(__file__).resolve().parent.parent
BODY = "{{cookiecutter.project_slug}}"
ANSWERS = {
    key: str(value)
    for key, value in yaml.safe_load(
        (ROOT / "tests" / "reference-answers.yaml").read_text()
    ).items()
}
PACKAGE = ANSWERS["package_name"]

# The fixture template's history, newest first, as Commitizen would write it.
CHANGELOG = {
    "v100.2.0": "### Fix\n\n- ruff: one more line\n",
    "v100.1.0": "### Feat\n\n- move lychee.toml under config/\n- add the team_channel prompt\n",
    "v100.0.0": "### Feat\n\n- everything so far\n",
}
BEFORE = '''\
"""Move lychee.toml under config/, where template v100.1.0 keeps it."""

import subprocess
import sys
from pathlib import Path

source, target = Path("lychee.toml"), Path("config/lychee.toml")
if target.exists() or not source.exists():
    sys.exit(0)  # already moved, or deleted by the team: nothing to do
target.parent.mkdir(exist_ok=True)
subprocess.run(["git", "mv", str(source), str(target)], check=True)
'''
AFTER = '''\
"""Append the migration marker to config/lychee.toml, once."""

import os
import sys
from pathlib import Path

path = Path("config/lychee.toml")
if not path.exists():
    sys.exit(0)
marker = f"# migrated by after.py to {os.environ['PYFR_UPDATE_TO']}\\n"
text = path.read_text()
if marker not in text:
    path.write_text(text + marker)
'''


@pytest.fixture(scope="module", autouse=True)
def isolated_git(tmp_path_factory: pytest.TempPathFactory) -> Iterator[None]:
    # Module scope, because template_remote is module-scoped and runs git
    # before any function-scoped monkeypatch exists. Same isolation as
    # tests/cli/conftest.py, restored by hand.
    saved = {name: os.environ.get(name) for name in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")}
    config = tmp_path_factory.mktemp("git") / "gitconfig"
    config.write_text("")
    os.environ["GIT_CONFIG_GLOBAL"] = str(config)
    os.environ["GIT_CONFIG_NOSYSTEM"] = "1"
    yield
    for name, value in saved.items():
        if value is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = value


def set_template_version(remote: Path, version: str, **prompts: str) -> None:
    data = json.loads((remote / "cookiecutter.json").read_text())
    data.update(prompts)
    data["_template_version"] = version
    (remote / "cookiecutter.json").write_text(json.dumps(data, indent=2) + "\n")


def write_changelog(remote: Path, up_to: str) -> None:
    versions = list(CHANGELOG)
    kept = versions[versions.index(up_to) :]
    text = "# Changelog\n\n" + "".join(
        f"## {version} (2026-10-{10 + index})\n\n{CHANGELOG[version]}\n"
        for index, version in enumerate(kept)
    )
    (remote / "CHANGELOG.md").write_text(text)


def release(remote: Path, version: str) -> None:
    write_changelog(remote, version)
    commit_all(remote, f"feat: {version}")
    git(remote, "tag", version)


@pytest.fixture(scope="module")
def template_remote(tmp_path_factory: pytest.TempPathFactory) -> Path:
    remote = tmp_path_factory.mktemp("template") / "pyfr"
    remote.mkdir()
    skip = shutil.ignore_patterns("__pycache__", ".venv", ".*_cache")
    shutil.copytree(ROOT / BODY, remote / BODY, ignore=skip)
    shutil.copytree(ROOT / "hooks", remote / "hooks", ignore=skip)
    shutil.copy(ROOT / "cookiecutter.json", remote / "cookiecutter.json")
    (remote / "updates").mkdir()
    (remote / "updates" / "README.md").write_text("the contract\n")
    git(remote, "init", "-q", "-b", "main")
    git(remote, "config", "user.name", "Template")
    git(remote, "config", "user.email", "template@example.com")
    set_template_version(remote, "100.0.0")
    release(remote, "v100.0.0")

    # v100.1.0: a template-owned line changes, a file is added, a file is
    # removed, a file moves (with a before.py to move it in the project, and
    # an after.py to rewrite it), and a prompt is added with a default.
    body = remote / BODY
    ruff = body / "ruff.toml"
    ruff.write_text(ruff.read_text() + "# template v100.1.0\n")
    (body / "TEMPLATE_NOTES.md").write_text("Added in v100.1.0\n")
    (body / ".trivyignore.yaml").unlink()
    (body / "config").mkdir()
    (body / "lychee.toml").rename(body / "config" / "lychee.toml")
    recorded = body / ".pyfr-answers.yml"
    recorded.write_text(recorded.read_text() + 'team_channel: "{{ cookiecutter.team_channel }}"\n')
    (remote / "updates" / "v100.1.0").mkdir()
    (remote / "updates" / "v100.1.0" / "before.py").write_text(BEFORE)
    (remote / "updates" / "v100.1.0" / "after.py").write_text(AFTER)
    set_template_version(remote, "100.1.0", team_channel="#platform")
    release(remote, "v100.1.0")

    # v100.2.0: one more template-owned line.
    ruff.write_text(ruff.read_text() + "# template v100.2.0\n")
    set_template_version(remote, "100.2.0")
    release(remote, "v100.2.0")
    return remote


def append(path: Path, text: str) -> None:
    path.write_text(path.read_text() + text)


def first_week(project: Path) -> None:
    """What every team does before the first update (spec section 8.2)."""
    # The example slice's tests, outside the ignore list -- the case the
    # whole mechanism exists for: deletions must stay deleted.
    (project / "tests" / "unit" / "test_order_repository.py").unlink()
    (project / "tests" / "integration" / "test_order_repository.py").unlink()
    append(project / "README.md", "\n## Team notes\n\nOurs.\n")
    pyproject = project / "pyproject.toml"
    pyproject.write_text(
        pyproject.read_text().replace(
            "dependencies = [\n", 'dependencies = [\n    "httpx>=0.27",\n', 1
        )
    )
    append(project / "lychee.toml", "# team note\n")
    commit_all(project, "chore: first week")


@pytest.fixture
def project(tmp_path: Path, template_remote: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    from cookiecutter.main import cookiecutter

    clone = tmp_path / "template-v100.0.0"
    git(tmp_path, "clone", "-q", "--branch", "v100.0.0", str(template_remote), str(clone))
    monkeypatch.setenv("PYFR_REGEN", "1")
    rendered = Path(
        cookiecutter(
            str(clone),
            no_input=True,
            extra_context=ANSWERS,
            output_dir=str(tmp_path / "out"),
            default_config=True,
        )
    )
    monkeypatch.delenv("PYFR_REGEN")
    project = tmp_path / "service"
    rendered.rename(project)
    git(project, "init", "-q", "-b", "main")
    git(project, "config", "user.name", "Team")
    git(project, "config", "user.email", "team@example.com")
    commit_all(project, "chore: generate the project from pyfr")
    origin = tmp_path / "origin.git"
    git(tmp_path, "init", "-q", "--bare", str(origin))
    git(project, "remote", "add", "origin", str(origin))
    git(project, "push", "-q", "-u", "origin", "main")
    first_week(project)
    return project


def run(
    project: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    *args: str,
) -> tuple[int, str, str]:
    monkeypatch.chdir(project)
    code = main(list(args))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def recorded_version(project: Path) -> str:
    return str(yaml.safe_load((project / ".pyfr-answers.yml").read_text())["_template_version"])


def trailer(project: Path, rev: str) -> str:
    return git(project, "show", "--no-patch", "--format=%(trailers:key=Pyfr-Template-Version,valueonly)", rev)


def test_a_clean_update_merges_the_template_and_keeps_the_team_s_work(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = run(project, monkeypatch, capsys, "update", "--template", str(template_remote), "--to", "v100.1.0")
    assert code == 0, out

    # What the tool said, in order.
    assert "template: created from root commit" in out
    assert "ignore: no .pyfr-update-ignore; using the built-in default" in out
    assert "render: new prompt team_channel defaulted to #platform" in out
    assert "template: committed v100.0.0 -> v100.1.0" in out
    assert "template: pushed to origin" in out
    assert "migrations: v100.1.0/before.py" in out
    assert "merge: clean" in out
    assert "migrations: v100.1.0/after.py" in out
    assert out.rstrip().endswith("recorded: v100.1.0")
    assert "conflict:" not in out

    # The team's work survived ...
    assert not (project / "tests" / "unit" / "test_order_repository.py").exists()
    assert not (project / "tests" / "integration" / "test_order_repository.py").exists()
    assert "## Team notes" in (project / "README.md").read_text()
    assert '"httpx>=0.27",' in (project / "pyproject.toml").read_text()
    # ... the template's changes arrived ...
    assert (project / "ruff.toml").read_text().endswith("# template v100.1.0\n")
    assert (project / "TEMPLATE_NOTES.md").read_text() == "Added in v100.1.0\n"
    assert not (project / ".trivyignore.yaml").exists()
    # ... the moved file kept the team's line and got after.py's ...
    assert not (project / "lychee.toml").exists()
    moved = (project / "config" / "lychee.toml").read_text()
    assert "# team note\n" in moved
    assert moved.endswith("# migrated by after.py to v100.1.0\n")
    # ... and the answers record the new version and the new prompt.
    assert recorded_version(project) == "100.1.0"
    assert yaml.safe_load((project / ".pyfr-answers.yml").read_text())["team_channel"] == "#platform"

    # The commits: prepare (before.py), the merge with the changelog body,
    # finish (after.py).
    subjects = git(project, "log", "--format=%s", "-4").splitlines()
    assert subjects == [
        "chore: finish template v100.1.0",
        "chore: update template v100.0.0 -> v100.1.0",
        "chore: prepare for template v100.1.0",
        "chore: first week",
    ]
    body = git(project, "log", "-1", "--format=%b", "HEAD~1")
    assert "## [v100.1.0](" in body
    assert "- add the team_channel prompt" in body
    assert "v100.0.0" not in body.split("\n", 1)[1]  # only the range's entries
    assert git(project, "rev-parse", "HEAD~1^2") == git(project, "rev-parse", "template")
    # The template branch is on origin with the trailer; nothing is left over.
    assert trailer(project, "origin/template") == "v100.1.0"
    assert git(project, "status", "--porcelain") == ""
    assert not (project / ".git" / "pyfr-update.json").exists()
    assert git(project, "worktree", "list").count("\n") == 0
    assert git(project, "replace", "-l") == ""


def test_a_second_run_is_current_and_update_check_sees_the_newer_tag(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    assert run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")[0] == 0
    code, out, _ = run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")
    assert (code, out) == (0, "already current at v100.1.0\n")
    code, out, _ = run(project, monkeypatch, capsys, "update-check", *template, "--json")
    assert code == 1
    assert json.loads(out) == {
        "recorded": "v100.1.0",
        "newest": "v100.2.0",
        "behind": True,
        "template": str(template_remote),
    }


def test_a_fresh_clone_fetches_the_pushed_template_branch(
    project: Path,
    template_remote: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    assert run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")[0] == 0
    # Another machine -- or the weekly workflow's checkout: origin's main is
    # still at the first week, origin/template is at v100.1.0.
    clone = tmp_path / "elsewhere"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(clone))
    git(clone, "config", "user.name", "Colleague")
    git(clone, "config", "user.email", "colleague@example.com")
    code, out, _ = run(clone, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")
    assert code == 0, out
    assert "template: already at v100.1.0" in out
    assert "created from root commit" not in out
    assert "template: committed" not in out
    assert (clone / "ruff.toml").read_text().endswith("# template v100.1.0\n")
    assert recorded_version(clone) == "100.1.0"


def test_the_project_s_own_ignore_file_is_honoured(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (project / ".pyfr-update-ignore").write_text("# ours to keep\n/ruff.toml\n")
    commit_all(project, "chore: keep ruff.toml ours")
    code, out, _ = run(project, monkeypatch, capsys, "update", "--template", str(template_remote), "--to", "v100.1.0")
    assert code == 0, out
    assert "using the built-in default" not in out
    assert "# template v100.1.0" not in (project / "ruff.toml").read_text()
    assert (project / "TEMPLATE_NOTES.md").exists()


def test_a_hand_made_commit_on_template_is_refused_before_anything_changes(
    project: Path,
    template_remote: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    assert run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")[0] == 0
    worktree = tmp_path / "wt"
    git(project, "worktree", "add", "-q", str(worktree), "template")
    (worktree / "ruff.toml").write_text("hand edit\n")
    commit_all(worktree, "tweak the template by hand")
    git(project, "worktree", "remove", "--force", str(worktree))
    head = git(project, "rev-parse", "HEAD")
    code, out, err = run(project, monkeypatch, capsys, "update", *template, "--to", "v100.2.0")
    assert code == 2
    assert "was not made by pyfr update" in err
    assert "git branch --force template" in err
    assert git(project, "rev-parse", "HEAD") == head
    assert git(project, "status", "--porcelain") == ""
```

- [ ] **Step 2: Run them**

Run: `uv run --group dev --group docs pytest tests/test_update_e2e.py -v`
Expected: all five PASS in well under a minute (five renders of the real body). If the first test fails, read the tool's output in the assertion message first — it names the step.

Likely first-run problems and their fixes:
- `git clone --branch v100.0.0 <path>` prints a "--depth is ignored in local clones" warning only when `--depth` is given; the fixture does not pass it. The tool's own clone does, and the warning is harmless.
- A `FailedHookException` from the render means `hooks/post_gen_project.py`'s pruning table did not find a path: the fixture removed or moved a file the table names. Choose another file (the table is the `PRUNED` dict in the hook).
- If `git(project, "worktree", "list").count("\n") == 0` fails, `git worktree remove` left an entry: check `vendor.worktree`'s `finally`.

- [ ] **Step 3: Lint and commit**

Run: `just lint`
Expected: clean (long assertion lines are within 88 columns or wrapped by `ruff format` — accept its formatting).

```bash
git add tests/test_update_e2e.py
git commit -m "test(pyfr-cli): update a rendered project end to end, without the network

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 13: End-to-end — squash merges, conflicts and resuming, `--no-push`

**Files:**
- Modify: `tests/test_update_e2e.py` (append three scenarios)

**Interfaces:**
- Consumes: the fixtures and helpers of Task 12 (`project`, `template_remote`, `run`, `recorded_version`, `trailer`, `append`), `pyfr_cli.git.Git`.

- [ ] **Step 1: Write the scenarios**

Append to `tests/test_update_e2e.py` (and add `from pyfr_cli.git import Git` to its imports):

```python


def test_squash_merged_history_does_not_conflict_again(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    assert run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")[0] == 0
    # What a squash-merged pull request leaves on main: one commit with the
    # update's tree and none of its history. The template commit the merge
    # was based on survives only on origin/template.
    before_merge = git(project, "rev-parse", "HEAD~1^1")
    git(project, "reset", "-q", "--soft", before_merge)
    commit_all(project, "chore: update template v100.0.0 -> v100.1.0 (#7)")
    template_v1 = git(project, "rev-parse", "template")
    assert not Git(project).ok("merge-base", "--is-ancestor", template_v1, "HEAD")

    # Without the pinned base this would conflict on ruff.toml: the squash
    # added "# template v100.1.0" at the end, and v100.2.0 adds a line after
    # it -- two different changes at the same place, against the root.
    code, out, _ = run(project, monkeypatch, capsys, "update", *template, "--to", "v100.2.0")
    assert code == 0, out
    assert "merge: base pinned to template commit" in out
    assert "conflict:" not in out
    assert (project / "ruff.toml").read_text().endswith(
        "# template v100.1.0\n# template v100.2.0\n"
    )
    assert recorded_version(project) == "100.2.0"
    # The graft was temporary: no replacement refs remain, and the merge
    # commit's parents are the real HEAD and the template commit.
    assert git(project, "replace", "-l") == ""
    merge = git(project, "log", "--format=%H", "--merges", "-1")
    assert git(project, "rev-parse", f"{merge}^2") == git(project, "rev-parse", "template")


def test_a_conflict_pauses_the_update_and_the_same_command_resumes(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    # The team appends a line where v100.1.0 appends a different one.
    append(project / "ruff.toml", "# team ruff\n")
    commit_all(project, "chore: our ruff line")

    code, out, _ = run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")
    assert code == 1, out
    assert "conflict: ruff.toml\n" in out
    assert "merge: conflicts in the files above" in out
    assert git(project, "diff", "--name-only", "--diff-filter=U") == "ruff.toml"
    # The answers file is staged at the new version, the state is written,
    # the template branch was pushed before the merge, and the after-script
    # has not run yet.
    assert ".pyfr-answers.yml" in git(project, "diff", "--cached", "--name-only").splitlines()
    assert recorded_version(project) == "100.1.0"
    assert (project / ".git" / "pyfr-update.json").exists()
    assert trailer(project, "origin/template") == "v100.1.0"
    assert "migrated by after.py" not in (project / "config" / "lychee.toml").read_text()

    # Running again before resolving only repeats the instructions.
    code, out, _ = run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")
    assert code == 1
    assert "conflict: ruff.toml" in out
    assert "merge: conflicts in the files above" in out

    # The user resolves -- keeps both lines -- and commits with the prepared
    # message.
    theirs = git(project, "show", "template:ruff.toml")
    (project / "ruff.toml").write_text(theirs + "\n# team ruff\n")
    git(project, "add", "ruff.toml")
    git(project, "commit", "-q", "--no-verify", "--no-edit")
    assert git(project, "log", "-1", "--format=%s") == "chore: update template v100.0.0 -> v100.1.0"
    assert "- add the team_channel prompt" in git(project, "log", "-1", "--format=%b")

    # The same command finishes: after.py runs, its commit lands, the state
    # is gone.
    code, out, _ = run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")
    assert code == 0, out
    assert "resume: finishing the update to v100.1.0" in out
    assert "migrations: v100.1.0/after.py" in out
    assert out.rstrip().endswith("recorded: v100.1.0")
    assert (project / "config" / "lychee.toml").read_text().endswith(
        "# migrated by after.py to v100.1.0\n"
    )
    assert git(project, "log", "-1", "--format=%s") == "chore: finish template v100.1.0"
    assert not (project / ".git" / "pyfr-update.json").exists()
    assert git(project, "status", "--porcelain") == ""
    # And now it is current.
    code, out, _ = run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")
    assert (code, out) == (0, "already current at v100.1.0\n")


def test_no_push_keeps_the_branch_local_until_the_next_run(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    code, out, _ = run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0", "--no-push")
    assert code == 0, out
    assert "template: not pushed (--no-push)" in out
    assert git(project, "ls-remote", "--heads", "origin", "template") == ""

    code, out, _ = run(project, monkeypatch, capsys, "update", *template, "--to", "v100.2.0")
    assert code == 0, out
    assert "template: exists locally but not on origin; it will be pushed" in out
    assert "template: pushed to origin" in out
    assert trailer(project, "origin/template") == "v100.2.0"
```

- [ ] **Step 2: Run them**

Run: `uv run --group dev --group docs pytest tests/test_update_e2e.py -v`
Expected: all eight PASS.

If `test_squash_merged_history_does_not_conflict_again` fails with `conflict: ruff.toml` in the output and no "base pinned" line, `_merge`'s ancestor check took the wrong branch: check that `vendor.commit_for` returned the `v100.1.0` template commit (not the root) — its `base` argument must be the branch's base, and the recorded version at that point is `v100.1.0`.

- [ ] **Step 3: Lint and commit**

Run: `just lint && just test`
Expected: clean; the whole root suite passes (the generation tests, golden diff and the release-bump test included).

```bash
git add tests/test_update_e2e.py
git commit -m "test(pyfr-cli): prove squash-merge survival, conflict resume and --no-push

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 14: Packaging in CI, and publishing on release

**Files:**
- Modify: `justfile` (a `wheel` recipe)
- Modify: `.github/workflows/ci.yml` (the `docs` job)
- Modify: `.github/workflows/release.yml` (a `publish-pypi` job)

**Interfaces:**
- Consumes: `needs.release.outputs.version` (bare, set only when a tag was settled on).

- [ ] **Step 1: The `wheel` recipe**

In `justfile`, after the `typecheck` recipe:

```
# Build the pyfr-cli wheel and run its console script from it, exactly as
# CI does (M8 spec, section 8.4). Needs the network: uvx resolves the
# wheel's dependencies into a throwaway environment.
wheel:
    #!/usr/bin/env bash
    set -euo pipefail
    rm -rf dist
    uv build --wheel
    uvx --from dist/pyfr_cli-*.whl pyfr --version
```

Run: `just wheel`
Expected: `Successfully built dist/pyfr_cli-0.10.0-py3-none-any.whl` then `pyfr 0.10.0`. (`dist/` is already in `.gitignore`.)

- [ ] **Step 2: The CI step**

In `.github/workflows/ci.yml`, in the `docs` job, after the step `Run every root-level gate`, add:

```yaml
      - name: Build the wheel and run its console script
        # The package this repository publishes (M8 spec, section 8.4):
        # the wheel builds from src/pyfr_cli alone, and `pyfr` runs from it.
        run: just wheel
```

Also update the `docs` job's leading comment: after "and the golden diff (`regen-check`)" add ", then `just typecheck` through `just check` and the wheel build".

- [ ] **Step 3: The publish job**

In `.github/workflows/release.yml`, after the `publish-images` job (at the end of the file), add:

```yaml
  publish-pypi:
    # pyfr-cli on PyPI at the version just released (M8 spec, section 3.5).
    # Trusted Publishing: PyPI accepts the short-lived OpenID Connect token
    # GitHub mints for this job, so no PyPI token is stored as a secret. The
    # publisher was registered on pypi.org by hand, once: project pyfr-cli,
    # owner EmadMokhtar, repository pyfr, workflow release.yml, no
    # environment. PyPI is asked first whether the version is already
    # there, so a rerun of a partly failed release publishes nothing twice
    # -- the same shape as the registry probe that gates publish-images.
    # Last, and nothing depends on it: while the publisher is missing, only
    # this job is red.
    needs: release
    if: needs.release.outputs.version != ''
    runs-on: ubuntu-latest
    permissions:
      contents: read
      id-token: write   # the OpenID Connect token Trusted Publishing verifies
    env:
      VERSION: ${{ needs.release.outputs.version }}
    steps:
      - uses: actions/checkout@v7
        with:
          # The tag, not main: main may already have moved on.
          ref: v${{ needs.release.outputs.version }}

      - name: Install uv
        uses: astral-sh/setup-uv@v7

      - name: Decide whether PyPI already has this version
        id: pypi
        run: |
          if curl --fail --silent --show-error --output /dev/null \
              "https://pypi.org/pypi/pyfr-cli/${VERSION}/json"; then
            echo "pyfr-cli ${VERSION} is on PyPI already."
            echo "publish=false" >> "$GITHUB_OUTPUT"
          else
            echo "publish=true" >> "$GITHUB_OUTPUT"
          fi

      - name: Build the sdist and the wheel
        if: steps.pypi.outputs.publish == 'true'
        run: uv build

      - name: Publish to PyPI
        if: steps.pypi.outputs.publish == 'true'
        # `uv publish` detects GitHub Actions and uses Trusted Publishing on
        # its own; no token argument, no secret.
        run: uv publish
```

- [ ] **Step 4: Check the workflow files and the hooks**

Run: `uv run --group dev pre-commit run --files .github/workflows/ci.yml .github/workflows/release.yml justfile`
Expected: `check yaml` passes; nothing rewritten.

- [ ] **Step 5: Commit**

```bash
git add justfile .github/workflows/ci.yml .github/workflows/release.yml
git commit -m "ci: build the pyfr-cli wheel on every push and publish it on release

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
```

---

### Task 15: Final verification and the pull request

**Files:** none new.

- [ ] **Step 1: Every gate, from the root**

Run, in this order, and paste each result into the PR description's "Verification" section:

```bash
just lint
```
Expected: ruff clean, mypy `Success: no issues found`.

```bash
just check
```
Expected: `mkdocs build --strict` passes, `mypy` passes, the whole `tests/` suite passes (the new `tests/cli/` and `tests/test_update_e2e.py` included), `examples/reference-service matches the template.`

```bash
just precommit
```
Expected: every hook passes over every tracked file — including `uv lock --check (repository)` on the changed lock.

```bash
just wheel
```
Expected: `pyfr 0.10.0` printed from the built wheel.

- [ ] **Step 2: The spec's definition of done, PR 1's share**

Check against spec section 1: item 1 (the package, its version) is ready but not yet on PyPI — that happens when this PR merges; item 2 (the end-to-end proof) and item 3 (squash survival) are green; item 6's root-side pieces (unit, e2e, packaging) are green. Items 4 and 5 belong to PRs 2 and 3.

- [ ] **Step 3: Push, issue, pull request**

The repository's rules: every PR links an issue (create one first if none exists), is assigned to `EmadMokhtar` with the bare login, and has a Conventional Commits title.

```bash
git push -u origin claude/m8-work-20802b
```

```bash
gh issue create --title "M8: template updates for generated projects" --body "Tracks M8 (docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md): pyfr-cli on PyPI (PR 1), the generated project's side (PR 2), closing docs (PR 3)." --assignee EmadMokhtar
```

Then, with the issue number `N` it printed:

```bash
gh pr create --assignee EmadMokhtar --title "feat: add pyfr-cli with pyfr update and update-check (m8 pr 1)" --body-file - <<'BODY'
## What

The first of M8's three pull requests (spec section 9). A `pyfr-cli` package, built from `src/pyfr_cli/` and published to PyPI on release, exposing:

- `pyfr update [--to V] [--no-push] [--template URL]` — re-renders the template at the target version with the project's recorded answers, commits the result on the `template` branch (pushed to `origin`), runs the version's migration scripts, and merges with the base pinned to the template commit at the recorded version, so squash-merged update PRs do not conflict twice.
- `pyfr update-check [--json]` — exit 1 when a newer template version exists.

Nothing under `{{cookiecutter.project_slug}}/` changes; PR 2 adds the recipes, the ignore file and the weekly workflow.

Spec: `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md` (amended in this PR: pinned merge base, hook skip, own-line comments in the ignore file). Plan: `docs/superpowers/plans/2026-09-14-pyfr-m8-pr1-pyfr-cli.md`.

## Before merging

Register the pending Trusted Publisher on pypi.org: project `pyfr-cli`, owner `EmadMokhtar`, repository `pyfr`, workflow `release.yml`, no environment. Until then the release's last job, `publish-pypi`, is red and nothing else is affected.

## Verification

(paste the outputs of `just lint`, `just check`, `just precommit`, `just wheel`)

Closes #N

🤖 Generated with [Claude Code](https://claude.com/claude-code)
BODY
```

- [ ] **Step 4: Verify the links registered**

```bash
gh pr view --json assignees,closingIssuesReferences --jq '{assignees: [.assignees[].login], closes: [.closingIssuesReferences[].number]}'
```
Expected: `{"assignees":["EmadMokhtar"],"closes":[N]}`. If `closes` is empty, edit the body so `Closes #N` is on its own line; if `assignees` is empty, `gh pr edit --add-assignee EmadMokhtar`.

- [ ] **Step 5: Wait for CI, then hand over**

The `docs` job runs `just check` and `just wheel`; `precommit` runs the hooks; `golden` is unaffected (the body did not change). When all are green, the PR is ready for review. On merge, `release.yml` bumps to v0.11.0, tags, and `publish-pypi` uploads `pyfr-cli 0.11.0` — check https://pypi.org/project/pyfr-cli/ afterwards, and that `uvx --from pyfr-cli@latest pyfr --version` prints `pyfr 0.11.0`.

---

## Self-review against the spec

- **3.1 layout** — Tasks 1–11 create every listed module; `errors.py` is added (the spec's layout omitted it) and the test package is `tests/cli/` for the import-collision reason in Global Constraints.
- **3.2 commands and exit codes** — Task 11; `--version` Task 1. Stable prefixes: Task 11's `update()`.
- **3.3 dependencies** — Task 1's `pyproject.toml`.
- **3.4 root pyproject** — Task 1; `test_release_bump.py` re-run there.
- **3.5 publishing** — Task 14 (`uv publish` rather than the `pypa` action: one tool fewer, same Trusted Publishing).
- **4.1 preconditions** — Task 11 `_preconditions` + the dirty-tree and operation checks; tested in `tests/cli/test_update.py`.
- **4.2 target** — Task 2 `resolve_target`, Task 11's current/downgrade checks.
- **4.3 template branch** — Task 9 (`ensure`, `describe`, the guard, the remote); the pinned base Task 11 `_merge` + amendment Task 1.
- **4.4 render** — Task 8.
- **4.5 sync and commit** — Task 9 `sync`/`commit`/`push`; `--allow-empty` tested.
- **4.6 migrations** — Task 10; `--no-project` documented in `updates/README.md`.
- **4.7 merge and record** — Task 11 `_merge`, `answers.install`, MERGE_MSG.
- **4.8 resuming** — Task 5 state, Task 11 `_resume`, Task 13's conflict scenario.
- **4.9 changelog** — Task 7.
- **5.2 default ignore list** — Task 6 (anchored; spec aligned in Task 6 step 5).
- **6 migration contract** — Task 10's `updates/README.md`.
- **8.1 unit tests** — Tasks 2–11.
- **8.2 end-to-end** — Tasks 12–13: scenarios 1–6 of the spec are covered (scenario 6, "no ignore file", is every fixture project in PR 1; the "ignore file honoured" test covers the other side).
- **8.4 packaging** — Task 14.
- **9 PR 1 contents** — all present; pending publisher named in Task 15's PR body.
- Not in this PR (by design): 5.1, 5.3, 5.4, 7 — PR 2 and PR 3.
