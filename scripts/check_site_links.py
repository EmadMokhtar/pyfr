#!/usr/bin/env python3
"""Check the absolute links between PyFr's two sites against the built site.

`mkdocs build --strict` resolves the relative links inside one site. A link
from a root page to the reference service's site, or back, is an absolute
URL on PyFr's Pages host (`https://emadmokhtar.github.io/pyfr/...`), which
`--strict` never resolves and which lychee is told to skip -- the URL only
exists once the deploy has happened. So nothing would notice a renamed page
or heading on the other side of that boundary.

This reads every such link out of the Markdown sources it is given and
resolves it against the `site/` directory `just docs-build` has just
written, where both sites sit side by side: the page must exist, and an
anchor must be an element id in it.

usage: check_site_links.py [--site DIR] [--exclude DIR]... PATH...

PATH is a Markdown file or a directory of them; --exclude skips a directory
inside one (the design archive under docs/superpowers/, which the site does
not publish). A URL that is a placeholder in prose -- one carrying `<page>`
or an ellipsis -- is not a link and is skipped. Exit 1 lists every link
that does not resolve.
"""

from __future__ import annotations

import argparse
import re
import sys
from collections.abc import Iterable, Sequence
from pathlib import Path

SITE_URL = "https://emadmokhtar.github.io/pyfr/"
# A URL on the Pages host, wherever it appears: a Markdown link target, an
# autolink in angle brackets, or bare prose. Stops at whitespace and at the
# characters that close those forms.
LINK = re.compile(re.escape(SITE_URL) + r"[^\s)>\"'`]*")
ELEMENT_ID = re.compile(r'\bid="([^"]+)"')
# Prose that shows the SHAPE of a link, not a link: `<page>`, `#…`.
PLACEHOLDERS = ("<", "…")


def markdown_files(paths: Iterable[Path], excluded: Iterable[Path] = ()) -> list[Path]:
    skipped = tuple(excluded)
    files: list[Path] = []
    for path in paths:
        candidates = sorted(path.rglob("*.md")) if path.is_dir() else [path]
        files.extend(
            candidate
            for candidate in candidates
            if not any(candidate.is_relative_to(directory) for directory in skipped)
        )
    return files


def links_in(path: Path) -> list[str]:
    return [
        url
        for url in LINK.findall(path.read_text())
        if not any(marker in url for marker in PLACEHOLDERS)
    ]


def page_for(url: str, site: Path) -> tuple[Path, str]:
    """The built page a URL names, and its anchor (empty when none).

    MkDocs writes directory URLs: `guides/x/` and `guides/x` both mean
    `guides/x/index.html`; the site root means `index.html`. A trailing
    `.` or `,` is prose punctuation the regex could not tell apart from
    the URL, not part of the path.
    """
    rest = url[len(SITE_URL) :]
    path, _, anchor = rest.partition("#")
    path = path.rstrip(".,").strip("/")
    return site / path / "index.html" if path else site / "index.html", anchor


def unresolved(files: Iterable[Path], site: Path) -> list[str]:
    problems: list[str] = []
    for path in files:
        for url in links_in(path):
            page, anchor = page_for(url, site)
            if not page.is_file():
                problems.append(f"{path}: {url} -> no page at {page}")
                continue
            if anchor and anchor not in ELEMENT_ID.findall(page.read_text()):
                problems.append(f"{path}: {url} -> no element with id {anchor!r}")
    return problems


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--site",
        type=Path,
        default=Path("site"),
        help="the built site directory (default: site)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        type=Path,
        help="a directory to skip inside the paths (repeatable)",
    )
    parser.add_argument(
        "paths", nargs="+", type=Path, help="Markdown files or directories"
    )
    args = parser.parse_args(argv)
    if not args.site.is_dir():
        print(f"{args.site} does not exist; run `just docs-build` first.")
        return 1
    problems = unresolved(markdown_files(args.paths, args.exclude), args.site)
    for problem in problems:
        print(problem)
    if problems:
        print(f"\n{len(problems)} cross-site link(s) do not resolve in {args.site}/.")
        return 1
    print("Every cross-site link resolves in the built site.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
