""".pyfr-update-ignore: the paths an update leaves exactly as the project has them.

gitignore syntax, matched with pathspec. A project generated before the
template shipped the file uses the built-in default below, rendered for its
answers (spec section 5.2 and decision M8-5).
"""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from pathspec import GitIgnoreSpec

from pyfr_cli.answers import Answers

FILE = ".pyfr-update-ignore"

HEADER = """\
# Paths `just update` leaves exactly as this project has them: yours from
# the first day, or artifacts of your code. Add paths as you diverge --
# one gitignore pattern per line, comments on their own lines.
# Everything not listed is template-owned and receives fixes by default.

# Written by the update itself.
/.pyfr-answers.yml
# This file.
/.pyfr-update-ignore
/README.md
/CHANGELOG.md
# Resolver output; run `uv lock` after an update that touched pyproject.toml.
/uv.lock
"""
SCHEMA = """\
# Your schema.
/migrations/
/schema.sql
"""
FOOTER = """\
# Artifacts of your code: the contract, and the baseline your release promotes.
/openapi.json
/openapi.baseline.json
# Your decisions.
/docs/adr/
# The example slice, then your business model.
/src/{package}/domain/
/src/{package}/services/
/src/{package}/api/v1/
"""


def default_text(package: str, database: str) -> str:
    """The built-in default, as the template body ships it for these answers.

    The schema lines exist only when the project has a database: the
    generator prunes migrations/ and schema.sql otherwise.
    """
    schema = SCHEMA if database == "postgres" else ""
    return HEADER + schema + FOOTER.format(package=package)


class Ignore:
    def __init__(self, lines: Iterable[str]) -> None:
        self._spec = GitIgnoreSpec.from_lines(lines)

    @classmethod
    def from_text(cls, text: str) -> Ignore:
        return cls(text.splitlines())

    def matches(self, relative: str) -> bool:
        """Whether a path (POSIX, relative to the project root) is left alone."""
        return bool(self._spec.match_file(relative))


def load(project: Path, recorded: Answers) -> tuple[Ignore, bool]:
    """The project's ignore file, or the default rendered for its answers.

    Returns the spec and whether the file existed, so the caller can say
    which one applied.
    """
    file = project / FILE
    if file.is_file():
        return Ignore.from_text(file.read_text()), True
    package = recorded.values.get("package_name", "")
    database = recorded.values.get("database", "none")
    return Ignore.from_text(default_text(package, database)), False
