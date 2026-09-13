"""Image pins come from compose.yaml and the Dockerfiles, and only from there.

Before M6 the integration tests carried their own copies of every image
tag, each with a comment saying "pinned to the same version compose
uses". Dependabot updates compose.yaml and the Dockerfiles; it cannot
update a string literal in a test. Reading the pins from the files it
DOES update is what turns "CI runs the versions a developer runs" from a
comment into a property (ADR 0014).
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[1]
COMPOSE_FILE = PROJECT_ROOT / "compose.yaml"
DOCKERFILE_MIGRATIONS = PROJECT_ROOT / "Dockerfile.migrations"


def compose_image(service: str) -> str:
    """The `image:` of one compose service, as written."""
    services = yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))["services"]
    return str(services[service]["image"])


def dockerfile_base_image(dockerfile: Path = DOCKERFILE_MIGRATIONS) -> str:
    """The image named by the first `FROM` line."""
    for line in dockerfile.read_text(encoding="utf-8").splitlines():
        match = re.match(r"^FROM\s+(\S+)", line)
        if match:
            return match.group(1)
    raise ValueError(f"no FROM line in {dockerfile}")
