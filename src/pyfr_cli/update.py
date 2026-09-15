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
        outcome = _merge(git, previous, body, recorded.version, target, out)
        # Step 10, clean or not: the answers file is an ignored path, so the
        # merge never touched it, and staged here it rides in the merge commit.
        # The recorded URL, not --template: that flag is a one-off override
        # (a maintainer testing an unreleased template from a local clone),
        # and a recorded local path would break the weekly workflow's
        # ls-remote in CI.
        answers.install(rendered.project, project, recorded.template)
        git.run("add", answers.FILE)
        # Same for the ignore file, when the project has none yet: the
        # built-in default ignores it, so the merge could not bring it.
        if ignore.install(rendered.project, project):
            git.run("add", ignore.FILE)
            out.write(f"ignore: installed {ignore.FILE} from the template\n")
        if outcome.graft_error is not None:
            # Reported only now, with the merge message written and the
            # answers file staged: a `git commit --no-edit` after this must
            # still produce a proper merge commit, not git's own default
            # message and a stale answers file. The graft entry is
            # re-recorded (it was already there from inside _merge) so the
            # next run's _ungraft retries the delete before anything else.
            state.save(
                git,
                state.State(recorded.version, target, "merging", graft=outcome.grafted),
            )
            out.write(
                "merge: the merge is ready but the temporary graft is still "
                "in place; remove it, then run pyfr update again\n"
            )
            raise outcome.graft_error
        if not outcome.clean:
            out.write(CONFLICT_HELP)
            return 1
        # No merge in progress after a clean exit: git said "Already up to
        # date" because the template commit is in HEAD's history already
        # (merged by hand, say). Only the answers file changes then, and
        # the commit is a plain one, not a merge.
        merged = git.operation_in_progress() == "merge"
        git.run(
            "commit", "--quiet", "--no-verify",
            "--file", str(git.git_dir() / "MERGE_MSG"),
        )  # fmt: skip
        if merged:
            sha = git.out("rev-parse", "--short=12", "HEAD")
            out.write(f"merge: clean, committed as {sha}\n")
        else:
            out.write(f"merge: nothing to merge; recording {target}\n")
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
    # Before the branch and root checks: both read HEAD, and a repository
    # with no commits has none to read.
    if not git.ok("rev-parse", "--verify", "--quiet", "HEAD"):
        raise UpdateError(
            "the repository has no commits",
            "commit the generated project first: git add -A && "
            "git commit -m 'chore: generate the project from pyfr'",
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
    if pending.graft is None:
        return
    deleted = git.run("replace", "--delete", pending.graft, check=False)
    if deleted.returncode != 0 and _has_replacement(git, pending.graft):
        # The common case is the ref is already gone and only the state
        # entry was stale (the previous run deleted it) -- that fails here
        # too, but harmlessly, so only a ref that is still really there is
        # worth stopping for.
        raise UpdateError(
            f"the temporary graft on {pending.graft[:12]} could not be "
            f"removed: {deleted.stderr.strip()}",
            f"remove it by hand: git replace -d {pending.graft[:12]}, "
            "then run pyfr update again",
        )


def _report_conflicts(git: Git, out: TextIO) -> list[str]:
    """The unmerged paths of the merge in progress, printed as `conflict:`
    lines and returned -- empty when a killed run left a clean merge
    uncommitted rather than a real conflict."""
    paths = git.out("diff", "--name-only", "--diff-filter=U").splitlines()
    for path in paths:
        out.write(f"conflict: {path}\n")
    return paths


@dataclass(frozen=True)
class MergeOutcome:
    """What `_merge` did. `graft_error` is set, not raised, so the caller
    can finish preparing the merge (the message, the staged answers file)
    before reporting it -- see the comment where `_merge` builds it."""

    clean: bool
    grafted: str | None
    graft_error: UpdateError | None


def _merge(
    git: Git,
    previous: str,
    body: str,
    recorded: Version,
    target: Version,
    out: TextIO,
) -> MergeOutcome:
    """`git merge --no-ff --no-commit template` with its base pinned to
    `previous`, the template commit at the recorded version (spec 4.7).

    Git finds that base by itself only when `previous` is in HEAD's
    history. After a squash-merged update pull request it is not, so a
    temporary graft -- an extra parent, seen by git but not written into
    the commit -- makes it the base; the graft is deleted right after the
    merge, whatever happened.
    """
    grafted: str | None = None
    if not git.ok("merge-base", "--is-ancestor", previous, "HEAD"):
        head = git.out("rev-parse", "HEAD")
        if _has_replacement(git, head):
            # The graft would replace the user's ref, and the state file
            # would then send the next run's clean-up to delete it. Nothing
            # has started, so the state saved for this merge goes too.
            state.clear(git)
            raise UpdateError(
                "HEAD already has a replacement ref (git replace), which the "
                "merge would have to change",
                f"remove it with git replace -d {head[:12]}, or update from a "
                "commit without one",
            )
        parents = git.out("rev-parse", f"{head}^@").split()
        state.save(git, state.State(recorded, target, "merging", graft=head))
        git.run("replace", "--graft", head, *parents, previous)
        grafted = head
        out.write(
            f"merge: base pinned to template commit {previous[:12]} "
            "(the last update was squash-merged)\n"
        )
    graft_error: UpdateError | None = None
    try:
        result = git.run("merge", "--no-ff", "--no-commit", vendor.BRANCH, check=False)
    finally:
        # Recorded here, not raised: raising in `finally` would run before
        # the merge message is written and the answers file is staged
        # below, in `update()`, and skip both -- a `git commit --no-edit`
        # afterwards (the merge itself is real and still needs finishing)
        # would then get git's own default message and miss the answers
        # file. The caller raises `graft_error` once that is done. Either
        # way, the state file's graft entry (saved above) is left in
        # place, so the next run's _ungraft retries the delete.
        if grafted is not None:
            deleted = git.run("replace", "--delete", grafted, check=False)
            if deleted.returncode != 0:
                graft_error = UpdateError(
                    f"the temporary graft on {grafted[:12]} could not be "
                    f"removed: {deleted.stderr.strip()}",
                    f"remove it by hand: git replace -d {grafted[:12]}, "
                    "then run pyfr update again",
                )
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
        return MergeOutcome(True, grafted, graft_error)
    _report_conflicts(git, out)
    return MergeOutcome(False, grafted, graft_error)


def _has_replacement(git: Git, sha: str) -> bool:
    """Whether a `git replace` ref exists for the commit `sha`."""
    return bool(git.out("replace", "--list", sha))


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
