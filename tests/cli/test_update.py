"""`update()` before it touches the network or the template: preconditions
and the cheap answers. The full flow is tests/test_update_e2e.py."""

from __future__ import annotations

import io
import json
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
    answers_yaml = f'_template: {template}\n_template_version: "0.10.0"\n'
    return make_repo(
        tmp_path / "project",
        {".pyfr-answers.yml": answers_yaml, "README.md": "hello\n"},
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
    (loose / ".pyfr-answers.yml").write_text(
        f'_template: {template}\n_template_version: "0.10.0"\n'
    )
    refused(loose, "not inside a git repository")


def test_a_repository_with_no_commits_is_refused(
    tmp_path: Path, template: Path
) -> None:
    fresh = tmp_path / "fresh"
    fresh.mkdir()
    git(fresh, "init", "-q", "-b", "main")
    (fresh / ".pyfr-answers.yml").write_text(
        f'_template: {template}\n_template_version: "0.10.0"\n'
    )
    error = refused(fresh, "the repository has no commits")
    assert "git commit" in error.fix


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


def test_resume_after_an_aborted_merge_starts_over(project: Path) -> None:
    # No real merge happened; the state file alone says one was in progress.
    # recorded (v0.10.0) != state.to (v0.11.0), so this is the "aborted"
    # branch: clear the state and fall through to the normal flow.
    state_path = update.state.path(update.Git(project))
    state_path.write_text(
        json.dumps(
            {"from": "v0.9.0", "to": "v0.11.0", "phase": "merging", "graft": None}
        )
    )
    code, out = run(project)
    assert code == 0
    assert out == (
        "resume: the previous merge was aborted; starting over\n"
        "already current at v0.10.0\n"
    )
    assert not state_path.exists()


def test_resume_with_a_clean_uncommitted_merge_reports_no_conflicts(
    project: Path,
) -> None:
    # A killed run can leave a merge that finished with zero conflicts but
    # was never committed (git merge --no-commit always stops before the
    # commit, clean or not). The next run must tell this apart from a real
    # conflict and not print CONFLICT_HELP, which talks about files to
    # resolve when there are none.
    git(project, "branch", "other")
    git(project, "switch", "-q", "other")
    (project / "extra.txt").write_text("extra\n")
    commit_all(project, "feat: extra file")
    git(project, "switch", "-q", "main")
    git(project, "merge", "--no-ff", "--no-commit", "other")
    state_path = update.state.path(update.Git(project))
    state_path.write_text(
        json.dumps(
            {"from": "v0.10.0", "to": "v0.11.0", "phase": "merging", "graft": None}
        )
    )
    code, out = run(project)
    assert code == 1
    assert "an uncommitted merge is waiting" in out
    assert "conflict:" not in out


def test_resume_after_the_merge_refuses_a_dirty_tree(project: Path) -> None:
    # recorded == state.to: the merge was already committed and only the
    # after-scripts remain. An edit made after that commit must not be
    # swept into the "finish" commit.
    updated = (project / ".pyfr-answers.yml").read_text().replace("0.10.0", "0.11.0")
    (project / ".pyfr-answers.yml").write_text(updated)
    commit_all(project, "chore: record 0.11.0")
    state_path = update.state.path(update.Git(project))
    state_path.write_text(
        json.dumps(
            {
                "from": "v0.10.0",
                "to": "v0.11.0",
                "phase": "after-scripts",
                "graft": None,
            }
        )
    )
    (project / "README.md").write_text("dirty\n")
    error = refused(project, "uncommitted changes")
    assert "reset --hard" in error.fix


def test_has_replacement_sees_only_a_replace_ref_for_that_commit(
    project: Path,
) -> None:
    repo = update.Git(project)
    first = git(project, "rev-parse", "HEAD")
    (project / "README.md").write_text("second\n")
    second = commit_all(project, "second")
    assert not update._has_replacement(repo, first)
    assert not update._has_replacement(repo, second)
    git(project, "replace", "--graft", second)  # the user made it a root
    assert update._has_replacement(repo, second)
    assert not update._has_replacement(repo, first)
