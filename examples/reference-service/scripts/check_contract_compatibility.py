"""Fail the build when a breaking API change ships unannounced.

`oasdiff` says whether the API broke. The commit messages say whether
anyone meant to break it. These can disagree -- someone removes a response
field and writes `fix:` -- and when they do, a client pinned to a
compatible range breaks in production. This is the gate that stops it
(spec 10.2).

This gate used to also compare `info.version` between the committed
contract and the baseline. That comparison is gone: the repository is
now versioned by Commitizen from commit messages, and the reference
service's own version is a fixed 0.1.0 that nobody bumps, so the
comparison was reading a number with no meaning. The question is now asked
of the commits directly, which is what spec 10.2 describes.

The commit range defaults to `since the last tag` rather than
`origin/main`, and `default_base()` below is why: the baseline half of
this gate only moves at a release, so the commit-range half has to cover
the same span, or a change marked breaking in one pull request stops
being visible to every pull request that follows it.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

OASDIFF_IMAGE = "tufin/oasdiff:v1.31.0"

# oasdiff's own severity scale: 3 is `error`, its word for breaking; 2 is
# `warning` and 1 is `info`, neither of which blocks.
BREAKING_LEVEL = 3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE = PROJECT_ROOT / "openapi.baseline.json"
CURRENT = PROJECT_ROOT / "openapi.json"

# A Conventional Commits subject marks a breaking change with `!` before
# the colon: `feat!:` or `feat(api)!:`. The `!` must be immediately before
# the colon -- an exclamation mark inside the description is prose.
_BREAKING_SUBJECT = re.compile(r"^[a-z]+(\([^)]*\))?!:")

# A footer marks it with a token at the START of a line. Matching anywhere
# would let a body explaining that something is NOT a breaking change mark
# itself as one, which quietly disarms the gate for the next real break.
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)


def message_is_breaking(message: str) -> bool:
    """Does this commit message declare a breaking change?"""
    subject = message.splitlines()[0] if message else ""
    return bool(_BREAKING_SUBJECT.match(subject) or _BREAKING_FOOTER.search(message))


def default_base(cwd: Path | None = None) -> str:
    """Where the commit-range half of this gate should start counting from.

    `breaking_changes()` compares the committed `openapi.baseline.json`
    against `openapi.json` -- a window that only moves at a release, via
    `just contract-release`. For the commit-message half to ask the SAME
    question -- "was a breaking change marked, since the thing we are
    diffing against was last updated" -- its range has to start at the
    same point: the last release, not `origin/main`. `origin/main` resets
    on every pull request branch, so a breaking change marked `feat(api)!:`
    in one pull request clears the baseline diff for good, but a LATER
    pull request's range no longer contains that marking commit -- and
    every pull request after it fails the same gate for a break someone
    already announced. That mismatch, not a typo, is the bug this
    resolves: the two halves of the gate must look at the same span of
    history, and comparing against `origin/main` could not guarantee that.

    A release always leaves a tag (`.github/workflows/release.yml` tags
    every release it cuts), so the most recent tag IS "the last release".
    With no tags at all -- a copy of this repository before its first
    release -- there has been no release at all, so the whole history
    counts as "since the last release": fall back to the repository's
    first commit.
    """
    described = subprocess.run(
        ["git", "describe", "--tags", "--abbrev=0"],
        capture_output=True,
        text=True,
        check=False,
        cwd=cwd,
    )
    if described.returncode == 0:
        return described.stdout.strip()

    root = subprocess.run(
        ["git", "rev-list", "--max-parents=0", "HEAD"],
        capture_output=True,
        text=True,
        check=True,
        cwd=cwd,
    )
    # A history with more than one root commit (a graft, or two histories
    # merged together) would print more than one line here; this
    # repository has exactly one, so the first line is always correct.
    return root.stdout.strip().splitlines()[0]


def range_is_marked_breaking(base: str, head: str) -> bool:
    """Is any commit in `base..head` marked as breaking?

    NUL-separated, not newline-separated: a commit body contains newlines,
    so splitting on them would treat every paragraph as its own commit --
    which happens to make the gate MORE permissive, and is therefore the
    kind of bug that never announces itself.
    """
    completed = subprocess.run(
        ["git", "log", "--format=%B%x00", f"{base}..{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return any(
        message_is_breaking(message.strip())
        for message in completed.stdout.split("\0")
        if message.strip()
    )


def breaking_changes(baseline: Path, current: Path) -> list[dict[str, object]]:
    """Run oasdiff in its pinned image and return only the breaking findings.

    The image rather than a local binary: oasdiff is a Go program, and
    requiring a Go toolchain to check a Python service's contract is a
    cost every contributor would pay forever.
    """
    completed = subprocess.run(
        [
            "docker",
            "run",
            "--rm",
            "-v",
            f"{baseline.parent}:/w",
            OASDIFF_IMAGE,
            "breaking",
            f"/w/{baseline.name}",
            f"/w/{current.name}",
            "-f",
            "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # oasdiff exits 1 when it FINDS breaking changes, which is not an
    # error. Anything above 1 is: a missing image, an unreadable file, a
    # malformed document. Distinguishing them is what stops a broken
    # docker install from quietly reading as "no breaking changes" — the
    # single most dangerous way for this gate to fail.
    if completed.returncode > 1:
        raise RuntimeError(
            f"oasdiff failed with exit {completed.returncode}: {completed.stderr}"
        )
    findings = json.loads(completed.stdout or "[]")
    return [f for f in findings if f.get("level") == BREAKING_LEVEL]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--base",
        default=None,
        help=(
            "Defaults to the most recent tag (the last release), or the "
            "repository's first commit if there are no tags at all."
        ),
    )
    parser.add_argument("--head", default="HEAD")
    arguments = parser.parse_args()
    base = arguments.base if arguments.base is not None else default_base()

    findings = breaking_changes(BASELINE, CURRENT)
    if not findings:
        print("No breaking API changes against the committed baseline.")
        return 0

    if range_is_marked_breaking(base, arguments.head):
        print(
            f"{len(findings)} breaking change(s), and a commit in "
            f"{base}..{arguments.head} is marked breaking. Allowed."
        )
        return 0

    print(
        f"BREAKING API CHANGE with no commit marked breaking in "
        f"{base}..{arguments.head}.\n",
        file=sys.stderr,
    )
    for finding in findings:
        print(
            f"  [{finding['id']}] {finding['operation']} {finding['path']}\n"
            f"      {finding['text']}",
            file=sys.stderr,
        )
    print(
        "\nEither undo the change, or mark the commit breaking -- `feat!:` "
        "in the subject, or a `BREAKING CHANGE:` footer. Marking it is a "
        "statement that clients will need to act, so mean it.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
