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

With --repo-root it checks a second kind of link the same way: every link
into this repository's tree on GitHub (`https://github.com/EmadMokhtar/pyfr/
edit/main/...`, `blob/main/...`, `tree/main/...`) found in the BUILT HTML
of both sites must name a path that exists in the checkout. Material
writes each page's edit link from `edit_uri`, so a wrong `edit_uri` -- the
nested site's points at the template body, whose braces it carries
percent-encoded -- is a dead link on every page, and lychee is told to
skip those.

usage: check_site_links.py [--site DIR] [--repo-root DIR] [--exclude DIR]...
                           PATH...

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
from urllib.parse import unquote

SITE_URL = "https://emadmokhtar.github.io/pyfr/"
REPOSITORY_URL = "https://github.com/EmadMokhtar/pyfr/"
# A URL on the Pages host, wherever it appears: a Markdown link target, an
# autolink in angle brackets, or bare prose. Stops at whitespace and at the
# characters that close those forms.
LINK = re.compile(re.escape(SITE_URL) + r"[^\s)>\"'`]*")
ELEMENT_ID = re.compile(r'\bid="([^"]+)"')
# A link into this repository's tree on GitHub, as the built HTML carries
# it: an edit link Material writes from `edit_uri`, or a `blob`/`tree` link
# a page wrote by hand. The path ends at the attribute's closing quote, a
# fragment or a query string.
REPOSITORY_LINK = re.compile(
    re.escape(REPOSITORY_URL) + r"(?:edit|blob|tree)/main/([^\s\"'<>#?]*)"
)
# Prose that shows the SHAPE of a link, not a link: `<page>`, `#…`.
PLACEHOLDERS = ("<", "…")
# The same, once Markdown has been rendered to HTML.
HTML_PLACEHOLDERS = ("&lt;", "…")


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


def unresolved_repository_links(site: Path, repo_root: Path) -> list[str]:
    """Links into this repository's tree on GitHub that name nothing here.

    Each URL is reported once, on the first page it is found in: an edit
    link is written from one `edit_uri` prefix, so a wrong prefix is the
    same broken link on every page. The path is percent-decoded before it
    is looked up, because the nested site's edit links carry the template
    body's `{{ }}` encoded.
    """
    problems: list[str] = []
    seen: set[str] = set()
    for page in sorted(site.rglob("*.html")):
        for match in REPOSITORY_LINK.finditer(page.read_text()):
            url, path = match.group(0), match.group(1)
            if url in seen or any(marker in url for marker in HTML_PLACEHOLDERS):
                continue
            seen.add(url)
            target = repo_root / unquote(path).rstrip("/")
            if not target.exists():
                problems.append(f"{page}: {url} -> nothing at {target}")
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
        "--repo-root",
        type=Path,
        default=None,
        help=(
            "this repository's checkout; when given, every link into its tree "
            "on GitHub found in the built HTML must name a path that exists there"
        ),
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
    if args.repo_root is not None and not args.repo_root.is_dir():
        print(f"{args.repo_root} is not a directory.")
        return 1
    cross_site = unresolved(markdown_files(args.paths, args.exclude), args.site)
    repository = (
        []
        if args.repo_root is None
        else unresolved_repository_links(args.site, args.repo_root)
    )
    for problem in cross_site + repository:
        print(problem)
    if cross_site:
        print(f"\n{len(cross_site)} cross-site link(s) do not resolve in {args.site}/.")
    if repository:
        print(
            f"\n{len(repository)} repository link(s) name nothing in {args.repo_root}/."
        )
    if cross_site or repository:
        return 1
    print(
        "Every cross-site link resolves in the built site"
        + (
            "; every repository link names a path in the checkout."
            if args.repo_root
            else "."
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
