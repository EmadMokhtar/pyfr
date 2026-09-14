"""The template's CHANGELOG.md: Commitizen's `## vX.Y.Z (date)` sections.

The sections between the recorded version and the target become the merge
commit's body, and from there the weekly pull request's (spec section 4.9).
"""

from __future__ import annotations

import re

from pyfr_cli.versions import Version

HEADING = re.compile(r"^## v?(?P<version>\d+\.\d+\.\d+)(?P<rest>.*)$")


def sections(text: str) -> list[tuple[Version, str, str]]:
    """(version, the rest of the heading line, body) for each section, in
    file order -- Commitizen writes the newest first."""
    found: list[tuple[Version, str, list[str]]] = []
    for line in text.splitlines():
        heading = HEADING.match(line)
        if heading is not None:
            found.append((Version.parse(heading["version"]), heading["rest"], []))
        elif found:
            found[-1][2].append(line)
    return [(version, rest, "\n".join(body).strip()) for version, rest, body in found]


def release_url(template: str, version: Version) -> str:
    base = template.rstrip("/").removesuffix(".git")
    return f"{base}/releases/tag/{version}"


def entries(text: str, after: Version, up_to: Version, template: str) -> str:
    """The sections with after < version <= up_to, newest first, each
    heading linking to its release. Empty when there are none."""
    parts = [
        f"## [{version}]({release_url(template, version)}){rest}\n\n{body}\n"
        for version, rest, body in sections(text)
        if after < version <= up_to
    ]
    return "\n".join(parts)
