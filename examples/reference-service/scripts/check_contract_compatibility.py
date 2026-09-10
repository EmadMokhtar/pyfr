"""Fail the build when a breaking API change ships unannounced.

`oasdiff` says whether the API broke. The commit messages say whether
anyone meant to break it. These can disagree -- someone removes a response
field and writes `fix:` -- and when they do, a client pinned to a
compatible range breaks in production. This is the gate that stops it
(spec 10.2).

Before M5 the second half of this compared `info.version` between the
committed contract and the baseline. That check is gone: the repository is
now versioned by Commitizen from commit messages, and the reference
service's own version is a fixed 0.1.0 that nobody bumps, so the
comparison was reading a number with no meaning. The question is now asked
of the commits directly, which is what spec 10.2 describes.
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
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    arguments = parser.parse_args()

    findings = breaking_changes(BASELINE, CURRENT)
    if not findings:
        print("No breaking API changes against the committed baseline.")
        return 0

    if range_is_marked_breaking(arguments.base, arguments.head):
        print(
            f"{len(findings)} breaking change(s), and a commit in "
            f"{arguments.base}..{arguments.head} is marked breaking. Allowed."
        )
        return 0

    print(
        f"BREAKING API CHANGE with no commit marked breaking in "
        f"{arguments.base}..{arguments.head}.\n",
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
