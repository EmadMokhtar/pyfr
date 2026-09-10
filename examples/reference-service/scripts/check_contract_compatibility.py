"""Fail the build when a breaking API change ships without a version bump.

`oasdiff` says whether the API broke. `pyproject.toml`'s version says what
the release claims. These can disagree — someone removes a response field
and leaves the version alone — and when they do, a client pinned to a
compatible range breaks in production. This is the gate that stops it
(spec 10.2).

M5 replaces the version comparison here with the Conventional Commits
range check, once tags and Commitizen exist. The oasdiff half stays.
"""

from __future__ import annotations

import json
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


class Version(tuple[int, int, int]):
    """A semantic version, compared as a tuple."""

    @classmethod
    def parse(cls, raw: str) -> Version:
        parts = raw.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise ValueError(f"not a semantic version: {raw!r}")
        return cls(int(part) for part in parts)


def bump_is_sufficient(baseline: Version, current: Version) -> bool:
    """Does the version change admit a breaking API change?

    Below 1.0.0 semver puts no compatibility promise on the major number,
    and the convention every tool follows is that the MINOR number carries
    breaking changes: 0.1.0 -> 0.2.0. At and above 1.0.0 it is the major.
    Getting this wrong in the lenient direction would let every pre-1.0
    break through unnoticed, which is most of this project's life so far.
    """
    if baseline[0] == 0:
        return current[:2] > baseline[:2]
    return current[0] > baseline[0]


def read_version(document: Path) -> Version:
    return Version.parse(json.loads(document.read_text())["info"]["version"])


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


def _render(version: Version) -> str:
    return ".".join(str(part) for part in version)


def main() -> int:
    baseline_version = read_version(BASELINE)
    current_version = read_version(CURRENT)
    findings = breaking_changes(BASELINE, CURRENT)

    if not findings:
        print(f"No breaking API changes against {_render(baseline_version)}.")
        return 0

    if bump_is_sufficient(baseline_version, current_version):
        print(
            f"{len(findings)} breaking change(s), and the version was bumped "
            f"{_render(baseline_version)} -> {_render(current_version)}. Allowed."
        )
        return 0

    print(
        f"BREAKING API CHANGE with no matching version bump.\n"
        f"  baseline: {_render(baseline_version)}\n"
        f"  current:  {_render(current_version)}\n",
        file=sys.stderr,
    )
    for finding in findings:
        print(
            f"  [{finding['id']}] {finding['operation']} {finding['path']}\n"
            f"      {finding['text']}",
            file=sys.stderr,
        )
    print(
        "\nEither undo the change, or bump the version in pyproject.toml and "
        "regenerate the contract with `just openapi`.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
