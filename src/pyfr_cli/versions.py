"""Template versions: the vX.Y.Z tags, compared as numbers, printed with the v."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING

from pyfr_cli.errors import UpdateError

if TYPE_CHECKING:
    from pyfr_cli.git import Git

# A release tag on the template repository. The v is required: a tag
# without it is not one Commitizen made for a release (spec section 4.2).
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
# What people type after --to, and what .pyfr-answers.yml records
# (cookiecutter.json holds the version without the v): the v is optional.
LENIENT = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
# `git ls-remote --tags` prints "<sha>\trefs/tags/<name>"; an annotated tag
# adds a second line for the commit it points at, whose name ends in ^{}.
REF = re.compile(r"^[0-9a-f]+\trefs/tags/(?P<name>[^\s^]+)$")


@dataclass(frozen=True, order=True)
class Version:
    major: int
    minor: int
    patch: int

    @classmethod
    def parse(cls, text: str) -> Version:
        match = LENIENT.match(text.strip())
        if match is None:
            raise ValueError(f"{text.strip()!r} is not a version like v0.12.0")
        major, minor, patch = (int(part) for part in match.groups())
        return cls(major, minor, patch)

    def __str__(self) -> str:
        return f"v{self.major}.{self.minor}.{self.patch}"

    @property
    def bare(self) -> str:
        """Without the v, as cookiecutter.json and PyPI carry it."""
        return f"{self.major}.{self.minor}.{self.patch}"


def parse_ls_remote(output: str) -> list[Version]:
    """Every release tag in `git ls-remote --tags` output, oldest first."""
    found: set[Version] = set()
    for line in output.splitlines():
        ref = REF.match(line)
        if ref is None:
            continue
        tag = TAG.match(ref["name"])
        if tag is None:
            continue
        major, minor, patch = (int(part) for part in tag.groups())
        found.add(Version(major, minor, patch))
    return sorted(found)


def remote_versions(template: str, git: Git) -> list[Version]:
    """The template's release tags, oldest first; never empty."""
    result = git.run("ls-remote", "--tags", template, check=False)
    if result.returncode != 0:
        raise UpdateError(
            f"could not list the tags of {template}: {result.stderr.strip()}",
            "check the _template URL in .pyfr-answers.yml (or --template), "
            "and that you are online",
        )
    found = parse_ls_remote(result.stdout)
    if not found:
        raise UpdateError(
            f"{template} has no release tags (vX.Y.Z)",
            "check the _template URL in .pyfr-answers.yml, or pass --template",
        )
    return found


def resolve_target(requested: str | None, available: list[Version]) -> Version:
    """The version to update to: the newest, or the one --to names."""
    if requested is None:
        return available[-1]
    try:
        wanted = Version.parse(requested)
    except ValueError as exc:
        raise UpdateError(str(exc), "pass --to like v0.12.0") from exc
    if wanted not in available:
        newest = ", ".join(str(version) for version in available[-5:])
        raise UpdateError(
            f"the template has no tag {wanted}", f"the newest tags are {newest}"
        )
    return wanted
