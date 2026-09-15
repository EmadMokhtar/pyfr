"""The template's CHANGELOG.md: Commitizen's `## vX.Y.Z (date)` sections.

The sections between the recorded version and the target become the merge
commit's body, and from there the weekly pull request's (spec section 4.9).
"""

from __future__ import annotations

import re

from pyfr_cli.versions import Version

HEADING = re.compile(r"^## v?(?P<version>\d+\.\d+\.\d+)(?P<rest>.*)$")
# An scp-like ssh clone URL: `[user@]host:path`, no scheme in front. The
# negative lookahead keeps a real URL (`https://host:port/path`) from
# matching -- that also has a `:` before the first `/`.
SCP_LIKE_URL = re.compile(
    r"^(?![A-Za-z][A-Za-z0-9+.-]*://)(?:[^@/]+@)?(?P<host>[^:/]+):(?P<path>.+)$"
)
# An ssh:// clone URL, any user, with an optional port that has no https
# equivalent -- the web UI lives on 443 whatever port ssh uses.
SSH_SCHEME_URL = re.compile(
    r"^ssh://(?:[^@/]+@)?(?P<host>[^:/]+)(?::\d+)?/(?P<path>.+)$"
)


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


def _https_base(template: str) -> str:
    """`template` as an https URL: an scp-like or `ssh://` clone URL is
    rewritten; anything else (https, http, a local path) is unchanged."""
    match = SCP_LIKE_URL.match(template) or SSH_SCHEME_URL.match(template)
    if match is None:
        return template
    return f"https://{match['host']}/{match['path']}"


def release_url(template: str, version: Version) -> str:
    """The release page for `version` at `template`, as an https URL --
    an ssh clone URL is turned into its https form first."""
    base = _https_base(template)
    base = base.rstrip("/").removesuffix(".git")
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
