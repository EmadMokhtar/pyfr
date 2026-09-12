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
PORT_PATTERN = re.compile(r"[1-9][0-9]*")

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
    # Stricter than int(): the answer is pasted into the render as-is, so
    # "08000" would render `default=08000` (a SyntaxError in settings.py)
    # and " 8000" would break compose.yaml's port mapping, even though
    # int() accepts both.
    if not PORT_PATTERN.fullmatch(HTTP_PORT):
        found.append(
            f"http_port {HTTP_PORT!r} must be a plain decimal integer: "
            "digits only, no leading zero, no spaces."
        )
    elif not 1 <= int(HTTP_PORT) <= 65535:
        found.append(f"http_port {HTTP_PORT} is outside 1-65535.")
    return found


def main() -> int:
    found = problems()
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
