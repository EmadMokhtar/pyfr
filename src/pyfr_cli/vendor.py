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


def ensure(git: Git, recorded: Version, target: Version) -> Branch:
    """Find, fetch or create the branch, then check the guard.

    In order: the remote's branch wins when it exists; a local one is used
    (and pushed later) when it does not; otherwise the single root commit
    starts it (spec section 4.3).
    """
    notes: list[str] = []
    created = False
    # A run that died may have left a worktree entry behind.
    git.run("worktree", "prune")
    on_remote = git.remote_exists(REMOTE) and git.ok(
        "ls-remote", "--exit-code", "--heads", REMOTE, BRANCH
    )
    if on_remote:
        git.run("fetch", "--quiet", REMOTE, BRANCH)
        if not git.branch_exists(BRANCH):
            git.run("branch", BRANCH, "FETCH_HEAD")
        elif git.ok("merge-base", "--is-ancestor", BRANCH, "FETCH_HEAD"):
            git.run("branch", "--force", BRANCH, "FETCH_HEAD")
        elif not git.ok("merge-base", "--is-ancestor", "FETCH_HEAD", BRANCH):
            raise UpdateError(
                f"the local {BRANCH} branch and {REMOTE}/{BRANCH} have diverged",
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
    version, base = describe(git)
    if version not in (recorded, target):
        raise UpdateError(
            f"{BRANCH} is at {version}, but {answers.FILE} records {recorded}",
            f"the two must agree; see {GUIDE} for re-pointing the branch",
        )
    return Branch(version, base, created, notes)


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
            "the local branch is correct and the run resumes",
        )
