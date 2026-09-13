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

import argparse
import subprocess
from collections.abc import Iterable, Sequence

# A generated project's source lives at src/. PyFr's own root run points
# --source at the template body's src/ instead, and --docs at both sites.
DEFAULT_SOURCE_PREFIXES = ("src/",)
# What counts as having documented the change.
DEFAULT_DOCS_PATHS = ("docs/", "README.md", "mkdocs.yml")

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


def source_changes(paths: Iterable[str], prefixes: Sequence[str]) -> list[str]:
    """The changed paths that live inside a watched source tree."""
    return [path for path in paths if path.startswith(tuple(prefixes))]


def touches_docs(
    paths: Iterable[str],
    docs_paths: Sequence[str],
    excluded_prefix: str | None,
) -> bool:
    """True when any changed path is a documented surface.

    `excluded_prefix` names a documented-looking path that does not count
    (PyFr's own root run passes `docs/superpowers/`: an archive of design
    specs and implementation plans, and adding one is not the same as
    documenting a change for readers). `None` means nothing is excluded.
    """
    return any(
        path.startswith(tuple(docs_paths))
        and (excluded_prefix is None or not path.startswith(excluded_prefix))
        for path in paths
    )


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source",
        action="append",
        metavar="PREFIX",
        help=(
            "a watched source prefix, repeatable "
            f"(default: {DEFAULT_SOURCE_PREFIXES[0]})"
        ),
    )
    parser.add_argument(
        "--docs",
        action="append",
        metavar="PATH",
        help=(
            "a documented-surface path, repeatable "
            f"(default: {', '.join(DEFAULT_DOCS_PATHS)})"
        ),
    )
    parser.add_argument(
        "--exclude-docs",
        default=None,
        metavar="PREFIX",
        help="a documented-looking path that does not count as documentation",
    )
    parser.add_argument("base", help="the base ref of the range to check")
    parser.add_argument("head", help="the head ref of the range to check")
    args = parser.parse_args(argv)

    source_prefixes = tuple(args.source) if args.source else DEFAULT_SOURCE_PREFIXES
    docs_paths = tuple(args.docs) if args.docs else DEFAULT_DOCS_PATHS

    paths = changed_files(args.base, args.head)
    sources = source_changes(paths, source_prefixes)
    if not sources or touches_docs(paths, docs_paths, args.exclude_docs):
        return 0

    listed = "\n".join(f"  - {path}" for path in sources)
    docs_listed = "\n".join(f"  - {path}" for path in docs_paths)
    print(
        "This pull request changes service source but no documentation:\n"
        f"{listed}\n\n"
        "Update whichever of these the change affects:\n"
        f"{docs_listed}\n\n"
        f"If the change genuinely needs no documentation, add the `{LABEL}` "
        "label to the pull request."
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
