"""`pyfr update` and `pyfr update-check`: spec section 4, step by step."""

from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import TextIO

from pyfr_cli import (
    answers,
    changelog,
    ignore,
    migrate,
    render,
    state,
    vendor,
    versions,
)
from pyfr_cli.errors import UpdateError
from pyfr_cli.git import Git, require_tools
from pyfr_cli.versions import Version

# `--no-edit`: the prepared message holds the changelog's `## [vX]` and
# `### Feat` headings, and the editor's default clean-up (`--cleanup=strip`)
# would delete every line that starts with `#`.
CONFLICT_HELP = """\
merge: conflicts in the files above
  1. resolve them, then stage them:  git add <the files>
  2. commit the merge:               git commit --no-edit   (the message is prepared)
  3. run the same command again:     pyfr update            (runs what is left)
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
    _require_clean(git)

    available = versions.remote_versions(template, git)
    target = versions.resolve_target(options.to, available)
    if target == recorded.version:
        # A --no-push run promised that the next run pushes the branch --
        # this run too, although it has nothing else to do (spec 3.2).
        if options.push and vendor.push_if_ahead(git):
            out.write(f"template: pushed to {vendor.REMOTE}\n")
        out.write(f"already current at {target}\n")
        return 0
    if target < recorded.version:
        raise UpdateError(
            f"{target} is older than the recorded {recorded.version}",
            "downgrades are not supported; pass a newer --to, or none for the newest",
        )

    # --no-push says the network may be missing: an unreachable origin then
    # means "work from the local branch", not "stop".
    branch = vendor.ensure(git, recorded.version, target, offline=not options.push)
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
            # A --no-push run got the branch here; this run carries it.
            if options.push and vendor.push_if_ahead(git):
                out.write(f"template: pushed to {vendor.REMOTE}\n")
        else:
            spec, from_file = ignore.load(project, recorded)
            if not from_file:
                out.write(f"ignore: no {ignore.FILE}; using the built-in default\n")
            with vendor.worktree(git, tmp / "worktree") as worktree:
                vendor.sync(rendered.project, worktree, spec)
                sha = vendor.commit(worktree, branch.version, target)
            out.write(
                f"template: committed {branch.version} -> {target} ({sha[:12]})\n"
            )
            if options.push:
                vendor.push(git)
                out.write(f"template: pushed to {vendor.REMOTE}\n")
            else:
                out.write(
                    "template: not pushed (--no-push); push it before this "
                    f"update is merged: git push {vendor.REMOTE} {vendor.BRANCH}\n"
                )

        migrations = migrate.discover(clone, recorded.version, target)
        migrate.run_before(migrations, project, recorded.version, target, out)
        _commit_changes(git, f"chore: prepare for template {target}", out)

        body = _changelog(clone, recorded.version, target, template)
        # Recorded before the merge starts: a run killed between here and the
        # merge commit (Ctrl-C, or a broken pipe under `pyfr update | head`)
        # must still leave a state file behind. Otherwise the next run either
        # sees a committed merge with no state and silently skips the
        # after-scripts, or sees an uncommitted tool merge and reports it as
        # a foreign one.
        state.save(git, state.State(recorded.version, target, "merging"))
        clean = _merge(git, previous, body, recorded.version, target, out)
        # Step 10, clean or not: the answers file is an ignored path, so the
        # merge never touched it, and staged here it rides in the merge commit.
        answers.install(rendered.project, project)
        git.run("add", answers.FILE)
        if not clean:
            out.write(CONFLICT_HELP)
            return 1
        git.run(
            "commit", "--quiet", "--no-verify",
            "--file", str(git.git_dir() / "MERGE_MSG"),
        )  # fmt: skip
        out.write(
            f"merge: clean, committed as {git.out('rev-parse', '--short=12', 'HEAD')}\n"
        )
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
        raise UpdateError(
            "HEAD is detached", "switch to a branch first: git switch main"
        )
    if not git.has_identity():
        raise UpdateError(
            "git has no user.name or user.email configured",
            'git config user.name "Your Name" && git config user.email you@example.com',
        )


def _require_clean(git: Git) -> None:
    if git.has_tracked_changes():
        raise UpdateError(
            "the working tree has uncommitted changes",
            "commit or discard them first: a clean tree is what makes every "
            "step of the update reversible with git reset --hard HEAD",
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
        conflicts = _report_conflicts(git, out)
        if conflicts:
            out.write(CONFLICT_HELP)
        else:
            out.write(
                "merge: an uncommitted merge is waiting; commit it with git "
                "commit --no-edit, then run pyfr update again\n"
            )
        return 1
    if recorded.version == pending.to_version:
        _require_clean(git)
        out.write(f"resume: finishing the update to {pending.to_version}\n")
        with tempfile.TemporaryDirectory(prefix="pyfr-update-") as scratch:
            clone = render.clone_template(
                template, pending.to_version, Path(scratch) / "template", git
            )
            migrations = migrate.discover(
                clone, pending.from_version, pending.to_version
            )
            _finish(
                git, project, migrations, pending.from_version, pending.to_version, out
            )
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


def _report_conflicts(git: Git, out: TextIO) -> list[str]:
    """The unmerged paths of the merge in progress, printed as `conflict:`
    lines and returned -- empty when a killed run left a clean merge
    uncommitted rather than a real conflict."""
    paths = git.out("diff", "--name-only", "--diff-filter=U").splitlines()
    for path in paths:
        out.write(f"conflict: {path}\n")
    return paths


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
    if result.returncode != 0 and git.operation_in_progress() != "merge":
        # Refused before it started: untracked files in the way, typically.
        # Nothing is in progress, so the state this run just saved is stale
        # and would otherwise be mistaken for a real paused merge.
        state.clear(git)
        raise UpdateError(
            f"git merge could not start: {result.stderr.strip()}",
            "move the files it names out of the way, then run again",
        )
    # Written only once the merge is actually in progress (or done): a
    # could-not-start merge above must leave no prepared message behind for
    # git to pre-fill into the user's next manual commit.
    message = f"chore: update template {recorded} -> {target}\n"
    if body:
        message += f"\n{body}"
    (git.git_dir() / "MERGE_MSG").write_text(message)
    if result.returncode == 0:
        return True
    _report_conflicts(git, out)
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
