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
def repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    # The host's global git configuration -- signing, a hooks path -- must
    # not reach a commit this test makes.
    global_config = tmp_path / "gitconfig"
    global_config.write_text("")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(global_config))
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
    committed = set(
        git("show", "--name-only", "--format=", "HEAD", cwd=repository).split()
    )
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
