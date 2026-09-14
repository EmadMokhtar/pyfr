"""The `template` branch: found, created, guarded, synced, committed, pushed."""

from __future__ import annotations

import re
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
        f"template: created from root commit {root[:12]} "
        '"chore: generate the project from pyfr"'
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
    assert vendor.describe(Git(project)) == (
        V12,
        git(project, "rev-list", "--max-parents=0", "HEAD"),
    )
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


def test_ensure_stops_when_origin_cannot_be_reached(
    project: Path, rendered: Path, tmp_path: Path
) -> None:
    # The branch is on origin; then the network goes away. Without the
    # distinction between "absent" and "unreachable", ensure would create
    # a second branch from the root and the push at the end would fail.
    update_branch(project, rendered, tmp_path)
    vendor.push(Git(project))
    git(project, "branch", "-D", "template")
    git(project, "remote", "set-url", "origin", "/nonexistent/repo.git")
    with pytest.raises(UpdateError) as stop:
        vendor.ensure(Git(project), V10, V12)
    assert "could not reach origin" in stop.value.cause
    assert "--no-push" in stop.value.fix
    assert not Git(project).branch_exists("template")


def test_ensure_offline_treats_an_unreachable_origin_as_absent(
    project: Path,
) -> None:
    git(project, "remote", "set-url", "origin", "/nonexistent/repo.git")
    root = git(project, "rev-parse", "HEAD")
    branch = vendor.ensure(Git(project), V10, V12, offline=True)
    assert branch.created
    assert git(project, "rev-parse", "template") == root
    # And a local branch is found the same way.
    again = vendor.ensure(Git(project), V10, V12, offline=True)
    assert not again.created
    assert "not on origin" in again.notes[0]


def test_push_if_ahead_pushes_only_what_origin_lacks(
    project: Path, rendered: Path, tmp_path: Path
) -> None:
    repo = Git(project)
    assert not vendor.push_if_ahead(repo)  # no branch yet
    sha = update_branch(project, rendered, tmp_path)  # a --no-push run's result
    assert vendor.push_if_ahead(repo)
    assert git(project, "rev-parse", "origin/template") == sha
    assert not vendor.push_if_ahead(repo)  # nothing left to push
    # Diverged: someone rewound the local branch and committed on it. Not
    # pushed here; ensure() names the fix on the next update.
    root = git(project, "rev-list", "--max-parents=0", "HEAD")
    git(project, "branch", "--force", "template", root)
    git(project, "worktree", "add", "-q", str(tmp_path / "wt2"), "template")
    (tmp_path / "wt2" / "stray.txt").write_text("x\n")
    commit_all(tmp_path / "wt2", "stray")
    git(project, "worktree", "remove", "--force", str(tmp_path / "wt2"))
    assert not vendor.push_if_ahead(repo)
    assert git(project, "ls-remote", "--heads", "origin", "template").startswith(sha)


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
    with pytest.raises(UpdateError, match=re.escape("no commit for v0.11.0")):
        vendor.commit_for(repo, Version(0, 11, 0), root)
