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
from pyfr_cli.git import Git

ROOT = Path(__file__).resolve().parent.parent
BODY = "{{cookiecutter.project_slug}}"
ANSWERS = {
    key: str(value)
    for key, value in yaml.safe_load(
        (ROOT / "tests" / "reference-answers.yaml").read_text()
    ).items()
}

# The fixture template's history, newest first, as Commitizen would write it.
CHANGELOG = {
    "v100.2.0": "### Fix\n\n- ruff: one more line\n",
    "v100.1.0": "### Feat\n\n- move lychee.toml under config/\n"
    "- add the team_channel prompt\n",
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
    saved = {
        name: os.environ.get(name)
        for name in ("GIT_CONFIG_GLOBAL", "GIT_CONFIG_NOSYSTEM")
    }
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
    recorded.write_text(
        recorded.read_text() + 'team_channel: "{{ cookiecutter.team_channel }}"\n'
    )
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
def project(
    tmp_path: Path, template_remote: Path, monkeypatch: pytest.MonkeyPatch
) -> Path:
    from cookiecutter.main import cookiecutter

    clone = tmp_path / "template-v100.0.0"
    git(
        tmp_path,
        "clone",
        "-q",
        "--branch",
        "v100.0.0",
        str(template_remote),
        str(clone),
    )
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
    # HEAD -> main, as on GitHub; the isolated git config has no defaultBranch.
    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
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
    return str(
        yaml.safe_load((project / ".pyfr-answers.yml").read_text())["_template_version"]
    )


def trailer(project: Path, rev: str) -> str:
    return git(
        project,
        "show",
        "--no-patch",
        "--format=%(trailers:key=Pyfr-Template-Version,valueonly)",
        rev,
    )


def test_a_clean_update_merges_the_template_and_keeps_the_team_s_work(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, out, _ = run(
        project,
        monkeypatch,
        capsys,
        "update",
        "--template",
        str(template_remote),
        "--to",
        "v100.1.0",
    )
    assert code == 0, out

    # What the tool said, in order.
    assert "template: created from root commit" in out
    assert "render: new prompt team_channel defaulted to #platform" in out
    assert "ignore: no .pyfr-update-ignore; using the built-in default" in out
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
    assert (
        yaml.safe_load((project / ".pyfr-answers.yml").read_text())["team_channel"]
        == "#platform"
    )

    # The commits: prepare (before.py), the merge with the changelog body,
    # finish (after.py).
    # --first-parent: main's own line, not the template commit the merge
    # brought in (which is newer than "chore: first week").
    subjects = git(project, "log", "--first-parent", "--format=%s", "-4").splitlines()
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
    assert git(project, "rev-parse", "HEAD~1^2") == git(
        project, "rev-parse", "template"
    )
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
    assert (
        run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")[0]
        == 0
    )
    code, out, _ = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0"
    )
    assert (code, out) == (0, "already current at v100.1.0\n")
    code, out, _ = run(
        project, monkeypatch, capsys, "update-check", *template, "--json"
    )
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
    assert (
        run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")[0]
        == 0
    )
    # Another machine -- or the weekly workflow's checkout: origin's main is
    # still the generated project (the first week was never pushed), and
    # origin/template is at v100.1.0.
    clone = tmp_path / "elsewhere"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(clone))
    git(clone, "config", "user.name", "Colleague")
    git(clone, "config", "user.email", "colleague@example.com")
    code, out, _ = run(
        clone, monkeypatch, capsys, "update", *template, "--to", "v100.1.0"
    )
    assert code == 0, out
    assert "template: already at v100.1.0" in out
    assert "created from root commit" not in out
    assert "template: committed" not in out
    assert (clone / "ruff.toml").read_text().endswith("# template v100.1.0\n")
    assert recorded_version(clone) == "100.1.0"


def test_a_pending_template_branch_is_carried_forward(
    project: Path,
    template_remote: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    git(project, "push", "-q", "origin", "main")  # the first week is on origin
    assert (
        run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")[0]
        == 0
    )
    # The weekly workflow's situation a week later: its pull request for
    # v100.1.0 was never merged, so origin's main still records v100.0.0,
    # while origin/template sits at v100.1.0 -- and v100.2.0 is out now.
    # The branch is a pending update, not a disagreement: the sync goes on
    # from it, and the merge base is still the recorded version's commit.
    clone = tmp_path / "workflow"
    git(tmp_path, "clone", "-q", str(tmp_path / "origin.git"), str(clone))
    git(clone, "config", "user.name", "Workflow")
    git(clone, "config", "user.email", "workflow@example.com")
    assert recorded_version(clone) == "100.0.0"
    code, out, _ = run(
        clone, monkeypatch, capsys, "update", *template, "--to", "v100.2.0"
    )
    assert code == 0, out
    assert "template: committed v100.1.0 -> v100.2.0" in out
    assert "created from root commit" not in out
    assert "conflict:" not in out
    assert (
        (clone / "ruff.toml")
        .read_text()
        .endswith("# template v100.1.0\n# template v100.2.0\n")
    )
    assert recorded_version(clone) == "100.2.0"
    # Both versions' changes arrived, with the team's work intact.
    assert (clone / "TEMPLATE_NOTES.md").exists()
    assert '"httpx>=0.27",' in (clone / "pyproject.toml").read_text()
    assert not (clone / "tests" / "unit" / "test_order_repository.py").exists()
    assert trailer(clone, "origin/template") == "v100.2.0"


def test_the_project_s_own_ignore_file_is_honoured(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    (project / ".pyfr-update-ignore").write_text("# ours to keep\n/ruff.toml\n")
    commit_all(project, "chore: keep ruff.toml ours")
    code, out, _ = run(
        project,
        monkeypatch,
        capsys,
        "update",
        "--template",
        str(template_remote),
        "--to",
        "v100.1.0",
    )
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
    assert (
        run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")[0]
        == 0
    )
    worktree = tmp_path / "wt"
    git(project, "worktree", "add", "-q", str(worktree), "template")
    (worktree / "ruff.toml").write_text("hand edit\n")
    commit_all(worktree, "tweak the template by hand")
    git(project, "worktree", "remove", "--force", str(worktree))
    head = git(project, "rev-parse", "HEAD")
    code, _, err = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.2.0"
    )
    assert code == 2
    assert "was not made by pyfr update" in err
    assert "git branch --force template" in err
    assert git(project, "rev-parse", "HEAD") == head
    assert git(project, "status", "--porcelain") == ""


def test_squash_merged_history_does_not_conflict_again(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    assert (
        run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")[0]
        == 0
    )
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
    code, out, _ = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.2.0"
    )
    assert code == 0, out
    assert "merge: base pinned to template commit" in out
    assert "conflict:" not in out
    assert (
        (project / "ruff.toml")
        .read_text()
        .endswith("# template v100.1.0\n# template v100.2.0\n")
    )
    assert recorded_version(project) == "100.2.0"
    # The graft was temporary: no replacement refs remain, and the merge
    # commit's parents are the real HEAD and the template commit.
    assert git(project, "replace", "-l") == ""
    merge = git(project, "log", "--format=%H", "--merges", "-1")
    assert git(project, "rev-parse", f"{merge}^2") == git(
        project, "rev-parse", "template"
    )
    # The state file, which recorded the graft, is gone with it.
    assert not (project / ".git" / "pyfr-update.json").exists()


def test_a_replacement_ref_on_head_is_refused_before_the_merge(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    assert (
        run(project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0")[0]
        == 0
    )
    # A squash-merged update, as above, so the next merge needs a graft ...
    before_merge = git(project, "rev-parse", "HEAD~1^1")
    git(project, "reset", "-q", "--soft", before_merge)
    commit_all(project, "chore: update template v100.0.0 -> v100.1.0 (#7)")
    # ... and the user already has a replacement ref on HEAD, which the
    # graft would overwrite and the next run's clean-up would then delete.
    git(project, "replace", "--graft", "HEAD")
    head = git(project, "rev-parse", "HEAD")
    code, _, err = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.2.0"
    )
    assert code == 2
    assert "HEAD already has a replacement ref" in err
    assert f"git replace -d {head[:12]}" in err
    # The user's ref is untouched and nothing is left half done.
    assert git(project, "replace", "-l") == head
    assert git(project, "rev-parse", "HEAD") == head
    assert Git(project).operation_in_progress() is None
    assert git(project, "status", "--porcelain") == ""
    assert not (project / ".git" / "pyfr-update.json").exists()


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

    code, out, _ = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0"
    )
    assert code == 1, out
    assert "conflict: ruff.toml\n" in out
    assert "merge: conflicts in the files above" in out
    # --no-edit, or the editor's default clean-up strips the `## [vX]` and
    # `### Feat` headings of the prepared message.
    assert "git commit --no-edit" in out
    assert git(project, "diff", "--name-only", "--diff-filter=U") == "ruff.toml"
    # The answers file is staged at the new version, the state is written,
    # the template branch was pushed before the merge, and the after-script
    # has not run yet.
    assert (
        ".pyfr-answers.yml"
        in git(project, "diff", "--cached", "--name-only").splitlines()
    )
    assert recorded_version(project) == "100.1.0"
    assert (project / ".git" / "pyfr-update.json").exists()
    assert trailer(project, "origin/template") == "v100.1.0"
    assert (
        "migrated by after.py" not in (project / "config" / "lychee.toml").read_text()
    )

    # Running again before resolving only repeats the instructions.
    code, out, _ = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0"
    )
    assert code == 1
    assert "conflict: ruff.toml" in out
    assert "merge: conflicts in the files above" in out

    # The user gives up for now: `git merge --abort` puts the tree back
    # (the answers file included), and the next run notices the stale
    # state, starts over, and conflicts at the same place again.
    git(project, "merge", "--abort")
    assert recorded_version(project) == "100.0.0"
    assert git(project, "status", "--porcelain") == ""
    code, out, _ = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0"
    )
    assert code == 1, out
    assert out.startswith("resume: the previous merge was aborted; starting over\n")
    assert "template: already at v100.1.0" in out
    assert "conflict: ruff.toml\n" in out

    # The user resolves -- keeps both lines -- and commits with the prepared
    # message, as the help text says.
    theirs = git(project, "show", "template:ruff.toml")
    (project / "ruff.toml").write_text(theirs + "\n# team ruff\n")
    git(project, "add", "ruff.toml")
    git(project, "commit", "-q", "--no-verify", "--no-edit")
    assert (
        git(project, "log", "-1", "--format=%s")
        == "chore: update template v100.0.0 -> v100.1.0"
    )
    body = git(project, "log", "-1", "--format=%b")
    assert "## [v100.1.0](" in body  # the heading survived the commit
    assert "- add the team_channel prompt" in body

    # The same command finishes: after.py runs, its commit lands, the state
    # is gone.
    code, out, _ = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0"
    )
    assert code == 0, out
    assert "resume: finishing the update to v100.1.0" in out
    assert "migrations: v100.1.0/after.py" in out
    assert out.rstrip().endswith("recorded: v100.1.0")
    assert (
        (project / "config" / "lychee.toml")
        .read_text()
        .endswith("# migrated by after.py to v100.1.0\n")
    )
    assert git(project, "log", "-1", "--format=%s") == "chore: finish template v100.1.0"
    assert not (project / ".git" / "pyfr-update.json").exists()
    assert git(project, "status", "--porcelain") == ""
    # And now it is current.
    code, out, _ = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0"
    )
    assert (code, out) == (0, "already current at v100.1.0\n")


def test_no_push_keeps_the_branch_local_until_the_next_run(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    code, out, _ = run(
        project,
        monkeypatch,
        capsys,
        "update",
        *template,
        "--to",
        "v100.1.0",
        "--no-push",
    )
    assert code == 0, out
    assert "template: not pushed (--no-push)" in out
    assert "git push origin template" in out
    assert git(project, "ls-remote", "--heads", "origin", "template") == ""

    code, out, _ = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.2.0"
    )
    assert code == 0, out
    assert "template: exists locally but not on origin; it will be pushed" in out
    assert "template: pushed to origin" in out
    assert trailer(project, "origin/template") == "v100.2.0"


def test_no_push_is_pushed_by_the_next_run_even_when_already_current(
    project: Path,
    template_remote: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    template = ("--template", str(template_remote))
    code, out, _ = run(
        project,
        monkeypatch,
        capsys,
        "update",
        *template,
        "--to",
        "v100.1.0",
        "--no-push",
    )
    assert code == 0, out
    assert git(project, "ls-remote", "--heads", "origin", "template") == ""

    # A run at the same version has nothing else to do, but the promise
    # "the next run pushes it" must hold for it too: after a squash merge
    # the template commit survives nowhere but this laptop (decision M8-3).
    code, out, _ = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0"
    )
    assert code == 0, out
    assert "template: pushed to origin" in out
    assert "already current at v100.1.0" in out
    assert trailer(project, "origin/template") == "v100.1.0"
    # Once pushed, a current run says nothing about the branch.
    code, out, _ = run(
        project, monkeypatch, capsys, "update", *template, "--to", "v100.1.0"
    )
    assert (code, out) == (0, "already current at v100.1.0\n")
