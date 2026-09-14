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
) -> Path:
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
    # A GitHub runner has no git identity, and the hook's first commit
    # would be refused with "empty ident name"; a user's machine has one.
    # Set through the environment, which every process the hook starts
    # inherits, so the test does not depend on the machine it runs on.
    for variable in ("GIT_AUTHOR_NAME", "GIT_COMMITTER_NAME"):
        monkeypatch.setenv(variable, "PyFr full suite")
    for variable in ("GIT_AUTHOR_EMAIL", "GIT_COMMITTER_EMAIL"):
        monkeypatch.setenv(variable, "full-suite@pyfr.invalid")
    # Neither the host's global git configuration nor the system one --
    # signing, a hooks path -- reaches a commit this test makes (the same
    # isolation as tests/test_regen.py's fixture).
    global_config = tmp_path_factory.mktemp("git") / "config"
    global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    # Imported here so the marker's deselection never needs cookiecutter.
    from cookiecutter.main import cookiecutter

    output = tmp_path_factory.mktemp(request.param)

    # Registered before the render, so a render or hook that raises leaves
    # its half-made project in place for inspection, exactly like a
    # failing gate does.
    def keep_only_a_failure() -> None:
        if getattr(request.node, "failed", False):
            print(f"\nThe failed render is kept under {output}")
        else:
            shutil.rmtree(output)

    request.addfinalizer(keep_only_a_failure)
    return Path(
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


def git(*args: str, cwd: Path) -> str:
    return subprocess.run(
        ["git", *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def test_a_generated_project_passes_every_one_of_its_gates(project: Path) -> None:
    # The hook's side effects, in the order it runs them: `git init`,
    # `uv sync`, `pre-commit install`, then one commit of everything. Each
    # is best effort -- a failure prints "run it later" and the hook goes
    # on -- so each is checked on its own: the commit (which `just check`
    # needs; it ends in `git diff --exit-code`), the installed hook, and
    # an environment that already matches the project, which `uv sync
    # --check` proves without touching it. Without that check, the first
    # `uv run` inside `check-all` would quietly repair a sync that failed.
    assert git("log", "--format=%s", cwd=project).splitlines() == [FIRST_COMMIT]
    assert (project / ".git" / "hooks" / "pre-commit").is_file()
    assert git("status", "--porcelain", cwd=project) == ""
    subprocess.run(["uv", "sync", "--check"], cwd=project, check=True)
    # `check-all` runs `check` first (lint, types, imports, tests, hooks),
    # then the site build, the container tier and the three gate recipes:
    # the six jobs the project's CI runs separately, in one command.
    subprocess.run(["just", "check-all"], cwd=project, check=True)
