"""Every git call the tool makes goes through `Git.run`."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from pyfr_cli.errors import UpdateError


class GitError(UpdateError):
    """A git command the tool expected to succeed did not."""


@dataclass(frozen=True)
class Git:
    """git, run in one directory.

    Arguments are always fixed literals or paths the tool computed, never
    input typed by a user.
    """

    cwd: Path

    def run(self, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args], cwd=self.cwd, capture_output=True, text=True
        )
        if check and result.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip()
            raise GitError(
                f"git {' '.join(args)} failed in {self.cwd}: {detail}",
                "the git message above says what went wrong",
            )
        return result

    def out(self, *args: str) -> str:
        return self.run(*args).stdout.strip()

    def ok(self, *args: str) -> bool:
        return self.run(*args, check=False).returncode == 0

    def toplevel(self) -> Path:
        return Path(self.out("rev-parse", "--show-toplevel")).resolve()

    def git_dir(self) -> Path:
        # Relative for the main worktree (".git"), absolute for a linked
        # worktree; resolved against cwd either way.
        return (self.cwd / self.out("rev-parse", "--git-dir")).resolve()

    def current_branch(self) -> str | None:
        name = self.out("rev-parse", "--abbrev-ref", "HEAD")
        return None if name == "HEAD" else name

    def has_tracked_changes(self) -> bool:
        return bool(self.out("status", "--porcelain", "--untracked-files=no"))

    def has_staged_changes(self) -> bool:
        return not self.ok("diff", "--cached", "--quiet")

    def operation_in_progress(self) -> str | None:
        git_dir = self.git_dir()
        if (git_dir / "MERGE_HEAD").exists():
            return "merge"
        if (git_dir / "rebase-merge").exists() or (git_dir / "rebase-apply").exists():
            return "rebase"
        if (git_dir / "CHERRY_PICK_HEAD").exists():
            return "cherry-pick"
        return None

    def root_commits(self) -> list[str]:
        return self.out("rev-list", "--max-parents=0", "HEAD").split()

    def has_identity(self) -> bool:
        return self.ok("config", "user.name") and self.ok("config", "user.email")

    def branch_exists(self, name: str) -> bool:
        return self.ok("show-ref", "--verify", "--quiet", f"refs/heads/{name}")

    def remote_exists(self, name: str) -> bool:
        return self.ok("remote", "get-url", name)

    def commit(self, message: str, *, allow_empty: bool = False) -> str:
        """Commit what is staged and return the sha.

        `--no-verify`: the tool's commits are mechanical, and the template
        worktree shares .git/hooks with the project, where the generator
        installed pre-commit. CI runs the gates on the pull request.
        """
        args = ["commit", "--quiet", "--no-verify", "--message", message]
        if allow_empty:
            args.append("--allow-empty")
        self.run(*args)
        return self.out("rev-parse", "HEAD")

    def subject(self, rev: str) -> str:
        return self.out("show", "--no-patch", "--format=%s", rev)


def require_tools(*names: str) -> None:
    for name in names:
        if shutil.which(name) is None:
            raise UpdateError(
                f"{name} is not on PATH", f"install {name}, then run again"
            )
