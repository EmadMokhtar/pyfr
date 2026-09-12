"""Reject bad answers before cookiecutter writes a single file.

Cookiecutter renders this file through Jinja before running it, so the
three constants below are literals by the time Python sees them. A
non-zero exit aborts the generation and nothing is left on disk.
"""

from __future__ import annotations

import keyword
import re
import sys

PROJECT_SLUG = "{{ cookiecutter.project_slug }}"
PACKAGE_NAME = "{{ cookiecutter.package_name }}"
HTTP_PORT = "{{ cookiecutter.http_port }}"

SLUG_PATTERN = re.compile(r"[a-z][a-z0-9-]*")

# The package name is spelled out in import lines, module paths and test
# identifiers throughout the render. Every render up to this length is
# proven format-clean at 88 columns (tests/test_generation.py); one
# character more and lines cross the limit.
MAX_PACKAGE_NAME_LENGTH = 25


def problems() -> list[str]:
    found: list[str] = []
    if not SLUG_PATTERN.fullmatch(PROJECT_SLUG):
        found.append(
            f"project_slug {PROJECT_SLUG!r} must match ^[a-z][a-z0-9-]*$: "
            "lower-case letters, digits and hyphens, starting with a letter."
        )
    if not PACKAGE_NAME.isidentifier():
        found.append(
            f"package_name {PACKAGE_NAME!r} is not a Python identifier: "
            "use lower-case letters, digits and underscores."
        )
    elif keyword.iskeyword(PACKAGE_NAME):
        found.append(f"package_name {PACKAGE_NAME!r} is a Python keyword.")
    elif PACKAGE_NAME in sys.stdlib_module_names:
        found.append(
            f"package_name {PACKAGE_NAME!r} shadows a standard library "
            "module; a service by that name breaks in confusing ways."
        )
    if len(PACKAGE_NAME) > MAX_PACKAGE_NAME_LENGTH:
        found.append(
            f"package_name {PACKAGE_NAME!r} is longer than "
            f"{MAX_PACKAGE_NAME_LENGTH} characters; longer names push "
            "generated lines past the 88-column limit."
        )
    try:
        port = int(HTTP_PORT)
    except ValueError:
        found.append(f"http_port {HTTP_PORT!r} is not an integer.")
    else:
        if not 1 <= port <= 65535:
            found.append(f"http_port {port} is outside 1-65535.")
    return found


def main() -> int:
    found = problems()
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
