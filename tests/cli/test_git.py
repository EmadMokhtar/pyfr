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
