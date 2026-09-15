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


def remote_tip(git: Git, *, offline: bool = False) -> str | None:
    """The sha of the branch as the remote has it right now, or None when
    the remote has no such branch.

    `git ls-remote --exit-code` exits 2 when the branch is absent and 128
    when the remote cannot be reached; the two must not be confused, or an
    offline run would rebuild the branch from the root although the remote
    has the real one. Unreachable is an error -- unless `offline`, the
    --no-push run's promise to work from the local branch: then it counts
    as absent.
    """
    if not git.remote_exists(REMOTE):
        return None
    # The full ref name, not the bare branch name: a pattern matches the
    # tail of a ref, so `template` alone also matches `feature/template`,
    # which sorts first and would be taken for the branch.
    result = git.run(
        "ls-remote", "--exit-code", "--heads", REMOTE, f"refs/heads/{BRANCH}",
        check=False,
    )  # fmt: skip
    if result.returncode == 0:
        return result.stdout.split()[0]
    if result.returncode == 2 or offline:
        return None
    raise UpdateError(
        f"could not reach {REMOTE} to look for the {BRANCH} branch: "
        f"{result.stderr.strip()}",
        "check the network, or pass --no-push to work from the local branch",
    )


def ensure(
    git: Git, recorded: Version, target: Version, *, offline: bool = False
) -> Branch:
    """Find, fetch or create the branch, then check the guard.

    In order: the remote's branch wins when it exists; a local one is used
    (and pushed later) when it does not; otherwise the single root commit
    starts it (spec section 4.3). `offline` is passed on to `remote_tip`.
    """
    notes: list[str] = []
    created = False
    # A run that died may have left a worktree entry behind -- and, when
    # it died before its clean-up, the worktree itself.
    git.run("worktree", "prune")
    for path in remove_stale_worktrees(git):
        notes.append(f"worktree: removed {path} (left by a killed run)")
    if remote_tip(git, offline=offline) is not None:
        git.run("fetch", "--quiet", REMOTE, BRANCH)
        if not git.branch_exists(BRANCH):
            git.run("branch", BRANCH, "FETCH_HEAD")
        elif git.ok("merge-base", "--is-ancestor", BRANCH, "FETCH_HEAD"):
            git.run("branch", "--force", BRANCH, "FETCH_HEAD")
        elif not git.ok("merge-base", "--is-ancestor", "FETCH_HEAD", BRANCH):
            local = git.out("rev-parse", BRANCH)[:12]
            remote = git.out("rev-parse", "FETCH_HEAD")[:12]
            raise UpdateError(
                f"the local {BRANCH} branch ({local}) and {REMOTE}/{BRANCH} "
                f"({remote}) have diverged",
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
            f"{BRANCH}: created from root commit {roots[0][:12]} "
            f'"{git.subject(roots[0])}"'
        )
    try:
        version, base = describe(git)
        _check_range(version, recorded, target)
    except UpdateError:
        # A branch this run created and then refused would make the next
        # run say "exists locally but not on origin" and then fail the
        # same way; deleting it leaves the repository as it was found.
        if created:
            git.run("branch", "-D", BRANCH, check=False)
        raise
    return Branch(version, base, created, notes)


def _check_range(version: Version, recorded: Version, target: Version) -> None:
    """The branch may sit anywhere from the recorded version to the target,
    inclusive. Between the two it is a pending update -- the weekly
    workflow synced and pushed it, and the project has not merged it yet
    -- and the sync continues from it. Below the recorded version, the
    branch was recreated (origin/template deleted, then rebuilt from the
    root) and the answers file knows better; `commit_for` would fail
    later anyway, this says why now."""
    if version > target:
        # The target is --to, or the newest release when none was given.
        raise UpdateError(
            f"the {BRANCH} branch is at {version}, ahead of the target {target}",
            f"pass --to {version} or newer, or wait for a newer template release",
        )
    if version < recorded:
        raise UpdateError(
            f"{BRANCH} is at {version} but {answers.FILE} records {recorded}, "
            "which is newer",
            f"see {GUIDE} for re-pointing the branch",
        )


def remove_stale_worktrees(git: Git) -> list[Path]:
    """Remove the tool's own leftover worktrees of the branch; return their
    paths. Any other worktree of the branch stops the run.

    A run killed before its clean-up (kill -9, a lost connection) leaves
    its temporary worktree on disk, and `git worktree prune` keeps an
    entry whose directory still exists. `worktree add` and `branch
    --force` would then fail with git's message about the branch being
    used elsewhere. Only a worktree in the tool's own layout is removed:
    one a user made on purpose may hold uncommitted files, and `remove
    --force` would discard them without a word. The main worktree and
    the one the tool runs in are never touched (`remove --force` would
    remove the current one too).
    """
    here = git.toplevel()
    removed: list[Path] = []
    entries = git.out("worktree", "list", "--porcelain").split("\n\n")
    for entry in entries[1:]:  # the first entry is the main worktree
        lines = entry.splitlines()
        if f"branch refs/heads/{BRANCH}" not in lines:
            continue
        path = Path(lines[0].removeprefix("worktree "))
        if path.resolve() == here:
            continue
        if not _is_tool_worktree(path):
            raise UpdateError(
                f"{BRANCH} is checked out in another worktree: {path}",
                f"git worktree remove {path} (after saving what it holds), "
                "then run again",
            )
        # A run killed mid-lock (`git worktree lock <path>`) leaves the entry
        # locked, and `remove --force` refuses a locked worktree outright.
        if any(line == "locked" or line.startswith("locked ") for line in lines):
            git.run("worktree", "unlock", str(path))
        result = git.run("worktree", "remove", "--force", str(path), check=False)
        if result.returncode != 0:
            raise UpdateError(
                f"could not remove the leftover worktree {path}: "
                f"{result.stderr.strip()}",
                f"remove it by hand -- git worktree unlock {path}; "
                f"git worktree remove --force {path} -- then run again",
            )
        removed.append(path)
    return removed


def _is_tool_worktree(path: Path) -> bool:
    """Whether `path` is where update.py puts the branch's worktree: a
    directory named `worktree` inside a `pyfr-update-*` temporary one."""
    return path.name == "worktree" and path.parent.name.startswith("pyfr-update-")


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
            "the local branch is correct and the next run pushes it",
        )


def push_if_ahead(git: Git) -> bool:
    """Push the local branch when it holds commits the remote lacks -- what
    a --no-push run leaves behind -- and say whether a push happened.

    Called by the runs that would otherwise touch the branch not at all
    (already current, or already at the target), so that the --no-push
    promise "the next run pushes it" holds for every next run, not only
    for one that finds a newer version. A branch that has diverged from
    the remote's is left alone here: `ensure` reports that, with the fix,
    on the next real update.
    """
    if not git.branch_exists(BRANCH) or not git.remote_exists(REMOTE):
        return False
    tip = remote_tip(git)
    if tip == git.out("rev-parse", BRANCH):
        return False
    if tip is not None and not git.ok("merge-base", "--is-ancestor", tip, BRANCH):
        return False
    push(git)
    return True
