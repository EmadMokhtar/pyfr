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
    assert (
        state.path(repo) == (tmp_path / "repo" / ".git" / "pyfr-update.json").resolve()
    )
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
