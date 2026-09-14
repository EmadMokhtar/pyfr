"""Reject bad answers before cookiecutter writes a single file.

Cookiecutter renders this file through Jinja before running it, so the
constants below are literals by the time Python sees them. Each is
rendered with Jinja's `tojson` filter inside a raw triple-quoted string and
decoded with json.loads: `tojson` escapes every quote (including the
apostrophe, as \u0027) and every control character, so an answer
containing a double quote, a backslash or a line break reaches the checks
below instead of breaking this file's own syntax -- and the file stays
valid Python before rendering, so the repository's ruff can read it. A
non-zero exit aborts the generation and nothing is left on disk.
"""

from __future__ import annotations

import json
import keyword
import re
import sys

# The single quotes are load-bearing: the rendered JSON value begins and
# ends with a double quote, so a """ delimiter would close early.
# fmt: off
PROJECT_NAME = json.loads(r'''{{ cookiecutter.project_name | tojson }}''')
PROJECT_SLUG = json.loads(r'''{{ cookiecutter.project_slug | tojson }}''')
PACKAGE_NAME = json.loads(r'''{{ cookiecutter.package_name | tojson }}''')
DESCRIPTION = json.loads(r'''{{ cookiecutter.description | tojson }}''')
AUTHOR_NAME = json.loads(r'''{{ cookiecutter.author_name | tojson }}''')
AUTHOR_EMAIL = json.loads(r'''{{ cookiecutter.author_email | tojson }}''')
HTTP_PORT = json.loads(r'''{{ cookiecutter.http_port | tojson }}''')
DATABASE = json.loads(r'''{{ cookiecutter.database | tojson }}''')
CACHE = json.loads(r'''{{ cookiecutter.cache | tojson }}''')
OBJECT_STORAGE = json.loads(r'''{{ cookiecutter.object_storage | tojson }}''')
# fmt: on

# Free-text answers are pasted into pyproject.toml basic strings, Python
# docstrings, Markdown and licence texts exactly as typed. None of those
# formats is escaped by the template, so the characters that would break
# one of them are refused up front.
FREE_TEXT = {
    "project_name": PROJECT_NAME,
    "description": DESCRIPTION,
    "author_name": AUTHOR_NAME,
    "author_email": AUTHOR_EMAIL,
}
UNREPRESENTABLE = re.compile(r'["\\\x00-\x1f\x7f]')

SLUG_PATTERN = re.compile(r"[a-z][a-z0-9-]*")
PORT_PATTERN = re.compile(r"[1-9][0-9]*")

# The package name is spelled out in import lines, module paths and test
# identifiers throughout the render. Every render up to this length is
# proven format-clean at 88 columns (tests/test_generation.py); one
# character more and lines cross the limit.
MAX_PACKAGE_NAME_LENGTH = 25

# Host ports the generated project's own tooling binds -- compose.yaml's
# services and the documentation preview. A service told to listen on one
# of them could never run beside its own stack, and the collision would
# surface as a failed `just up`, long after generation. Keys are the
# answer's own spelling: a plain decimal string, checked below before this
# table is consulted.
RESERVED_PORTS = {
    "8001": "the documentation preview (`just docs`)",
    "9099": "the payment stub (compose.yaml)",
    "3000": "Grafana (compose.yaml, the o11y profile)",
    "4317": "the OTLP gRPC collector (compose.yaml, the o11y profile)",
    "4318": "the OTLP HTTP collector (compose.yaml, the o11y profile)",
    "9090": "Prometheus (compose.yaml, the o11y profile)",
}
# Bound only while the backend is in the stack; a project without it may
# use the port.
BACKEND_PORTS = {
    "postgres": {"5432": "PostgreSQL (compose.yaml)"},
    "redis": {"6379": "Redis (compose.yaml)"},
    "s3": {
        "9000": "MinIO (compose.yaml)",
        "9001": "the MinIO console (compose.yaml)",
    },
}


def problems() -> list[str]:
    found: list[str] = []
    for key, value in FREE_TEXT.items():
        if UNREPRESENTABLE.search(value):
            found.append(
                f"{key} {value!r} must not contain a double quote, a "
                "backslash or a control character such as a line break; "
                "the template pastes it into pyproject.toml, Python and "
                "Markdown as is."
            )
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
    else:
        reserved = dict(RESERVED_PORTS)
        for backend in (DATABASE, CACHE, OBJECT_STORAGE):
            reserved.update(BACKEND_PORTS.get(backend, {}))
        if HTTP_PORT in reserved:
            found.append(
                f"http_port {HTTP_PORT} is taken by {reserved[HTTP_PORT]}; "
                "the service could not run beside its own stack."
            )
    return found


def main() -> int:
    found = problems()
    for line in found:
        print(line, file=sys.stderr)
    return 1 if found else 0


if __name__ == "__main__":
    sys.exit(main())
