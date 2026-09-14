#!/usr/bin/env python3
"""Warn about documentation that has gone unreviewed, or unreviewed code.

Two checks, both advisory, neither able to fail a build:

  last_reviewed:  a page nobody has looked at in MAX_REVIEW_AGE_DAYS
  covers:         a path a page claims to describe changed, and the page
                  did not

The precise counterpart to scripts/check_docs_updated.py, which is the
blunt version of the second check and IS a hard gate. This one names the
page and the path; that one only knows that source moved and prose did not.

Both stay for now. See the contributing page for what has to be true before
these warnings become failures -- the switch is deliberate and not taken
here, because a large refactor trips path coupling across many pages at
once, which lands exactly when a team is busiest.

Needs PyYAML -- declared as a direct `dev` dependency in the root
`pyproject.toml` precisely so this import does not depend on MkDocs
happening to pull PyYAML in transitively -- so this runs in the
documentation job after `uv sync --group docs` (which installs the
default `dev` group alongside it) rather than as a bare python3 script the
way check_docs_updated.py does.
"""

from __future__ import annotations

import argparse
import datetime as dt
import subprocess
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DOCS_ROOT = Path("docs")

# adr/ is history. An accepted decision record does not go stale: it
# records what was decided, when, and why. Asking someone to re-review one
# twice a year trains them to ignore the warning, and superseding a
# decision means writing a NEW record, never editing the old one.
EXCLUDED_PREFIXES = ("docs/adr/",)

# Six months. Long enough that an actively maintained page is never
# flagged, short enough that a page nobody has opened in a release cycle
# is. Not tuned against anything -- adjust it once there is evidence.
MAX_REVIEW_AGE_DAYS = 180


@dataclass(frozen=True)
class Page:
    """A published page and the two hygiene claims its frontmatter makes."""

    path: str
    last_reviewed: dt.date | None
    covers: list[str] = field(default_factory=list)


def parse_frontmatter(text: str) -> dict[str, Any]:
    """The YAML block between the leading `---` fences, or an empty dict.

    Deliberately strict about the opening fence being the FIRST line: a
    `---` used as a horizontal rule mid-page is ordinary Markdown, and
    treating it as frontmatter would swallow the prose after it.
    """
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    loaded = yaml.safe_load(text[4:end])
    return loaded if isinstance(loaded, dict) else {}


def load_pages(
    root: Path = DOCS_ROOT, excluded_prefixes: Sequence[str] = EXCLUDED_PREFIXES
) -> list[Page]:
    """Every published page, with whatever frontmatter it carries.

    `excluded_prefixes` defaults to `EXCLUDED_PREFIXES`; the caller may add
    to it (a generated project's own archive directory, if it has one) via
    the `--exclude` command-line option.
    """
    pages: list[Page] = []
    for path in sorted(root.rglob("*.md")):
        as_posix = path.as_posix()
        if as_posix.startswith(tuple(excluded_prefixes)):
            continue
        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
        reviewed = meta.get("last_reviewed")
        covers = meta.get("covers") or []
        pages.append(
            Page(
                path=as_posix,
                # yaml.safe_load already produces a date for an unquoted
                # ISO-8601 value; anything else is malformed and treated as
                # absent rather than crashing an advisory check.
                last_reviewed=reviewed if isinstance(reviewed, dt.date) else None,
                covers=[str(entry) for entry in covers],
            )
        )
    return pages


def stale_pages(pages: Iterable[Page], today: dt.date) -> list[Page]:
    """Pages whose review date is older than the maximum age.

    A page with NO review date is not stale -- it is undeclared, which is a
    different problem reported by its own warning. Conflating the two
    produces warnings citing dates that never existed.
    """
    cutoff = today - dt.timedelta(days=MAX_REVIEW_AGE_DAYS)
    return [
        page
        for page in pages
        if page.last_reviewed is not None and page.last_reviewed < cutoff
    ]


def undeclared_pages(pages: Iterable[Page]) -> list[Page]:
    """Published pages carrying no `last_reviewed` at all."""
    return [page for page in pages if page.last_reviewed is None]


def uncovered_changes(
    pages: Iterable[Page], changed: set[str]
) -> list[tuple[str, str]]:
    """(page, covered path) pairs where the path moved and the page did not.

    A `covers:` entry ending in `/` matches every file beneath it. Listing
    files one by one would make the frontmatter unmaintainable, and
    unmaintainable frontmatter goes stale -- which is the failure this
    whole mechanism exists to catch.
    """
    findings: list[tuple[str, str]] = []
    for page in pages:
        if page.path in changed:
            continue
        for covered in page.covers:
            if any(
                path == covered or (covered.endswith("/") and path.startswith(covered))
                for path in changed
            ):
                findings.append((page.path, covered))
    return findings


def changed_files(base: str, head: str) -> set[str]:
    """Paths changed between `base` and `head`, as git reports them.

    `--relative` makes the paths relative to the CURRENT directory rather
    than the repository root, so the same `covers:` paths serve this
    script from any directory the project is checked out in, or from a
    subdirectory of a larger repository that vendors it -- neither run
    carries a prefix the other one does not.
    """
    completed = subprocess.run(
        ["git", "diff", "--name-only", "--relative", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {line for line in completed.stdout.splitlines() if line}


def warn(path: str, message: str) -> None:
    """A GitHub Actions annotation, which is also readable as plain text."""
    print(f"::warning file={path}::{message}")


def main(argv: Sequence[str] | None = None) -> int:
    """Always returns 0. These checks advise; they never block."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--exclude",
        action="append",
        metavar="PREFIX",
        help=(
            "exclude pages under this prefix from every check; repeatable, "
            f"added to the default {EXCLUDED_PREFIXES}"
        ),
    )
    parser.add_argument("base", help="the base ref of the range to check")
    parser.add_argument("head", help="the head ref of the range to check")
    args = parser.parse_args(argv)

    excluded_prefixes = (*EXCLUDED_PREFIXES, *(args.exclude or ()))

    pages = load_pages(excluded_prefixes=excluded_prefixes)
    changed = changed_files(args.base, args.head)
    today = dt.date.today()

    for page in stale_pages(pages, today=today):
        age = (today - page.last_reviewed).days  # type: ignore[operator]
        warn(
            page.path,
            f"last reviewed {page.last_reviewed} ({age} days ago, maximum "
            f"{MAX_REVIEW_AGE_DAYS}). Re-read it and update last_reviewed.",
        )

    for page in undeclared_pages(pages):
        warn(page.path, "no `last_reviewed` in its frontmatter.")

    for page_path, covered in uncovered_changes(pages, changed):
        warn(
            page_path,
            f"covers `{covered}`, which changed in this pull request while "
            f"this page did not. Check whether it is still accurate.",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
