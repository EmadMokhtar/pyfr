#!/usr/bin/env python3
"""Fail a pull request that changes service source without touching docs.

This is deliberately a heuristic, not a proof. It cannot tell a stale
sentence from a fresh one; it only notices that source changed and no
documented surface did. Pure refactors, dependency bumps and internal-only
changes will trip it -- that is the accepted cost of catching the case that
matters. The escape hatch is the `no-docs-needed` label on the pull request,
checked in the workflow rather than here.

Stdlib only, so the CI job needs no dependency installation step.
"""

from __future__ import annotations

import subprocess
import sys
from collections.abc import Iterable, Sequence

# The reference service's own source. M7 moves this tree under
# `{{cookiecutter.project_slug}}/`; add that prefix here in the same change.
SOURCE_PREFIXES = ("examples/reference-service/src/",)

# What counts as having documented the change. docs/superpowers/ is
# deliberately absent: it is an archive of design specs and implementation
# plans, and adding one is not the same as documenting a change for readers.
DOCS_PATHS = ("docs/", "README.md", "mkdocs.yml")
EXCLUDED_DOCS_PREFIX = "docs/superpowers/"

LABEL = "no-docs-needed"


def changed_files(base: str, head: str) -> list[str]:
    """Paths changed between `base` and `head`, as git reports them."""
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return [line for line in completed.stdout.splitlines() if line]


def source_changes(paths: Iterable[str]) -> list[str]:
    """The changed paths that live inside a watched source tree."""
    return [path for path in paths if path.startswith(SOURCE_PREFIXES)]


def touches_docs(paths: Iterable[str]) -> bool:
    """True when any changed path is a documented surface."""
    return any(
        path.startswith(DOCS_PATHS) and not path.startswith(EXCLUDED_DOCS_PREFIX)
        for path in paths
    )


def main(argv: Sequence[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if len(args) != 2:
        print("usage: check_docs_updated.py <base-ref> <head-ref>")
        return 2

    paths = changed_files(args[0], args[1])
    sources = source_changes(paths)
    if not sources or touches_docs(paths):
        return 0

    listed = "\n".join(f"  - {path}" for path in sources)
    print(
        "This pull request changes service source but no documentation:\n"
        f"{listed}\n\n"
        "Update whichever of these the change affects:\n"
        "  - docs/       the documentation site\n"
        "  - README.md   the landing page\n"
        "  - mkdocs.yml  navigation\n\n"
        f"If the change genuinely needs no documentation, add the `{LABEL}` "
        "label to the pull request."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
