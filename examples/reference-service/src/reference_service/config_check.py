"""Print the resolved configuration with every secret masked.

    just config-check
    docker compose run --rm app python -m reference_service.config_check

Loads settings exactly as the service does at startup, so a malformed
environment exits with the same readable message and the same exit code
(78, EX_CONFIG) -- which makes this the thing to run when the service
will not start (docs/runbook.md). A valid environment prints one JSON
object, keys sorted.

Two layers of masking. `model_dump(mode="json")` renders every
`SecretStr` as `**********`. That is not enough on its own (M6 plan,
Verified Fact 7): `APP_DATABASE__DSN` and `APP_CACHE__DSN` are URL
types, and a URL's password is plain text inside the dumped string.
`mask` walks the dump and blanks the password of any string that parses
as a URL carrying credentials -- generic, so a DSN field added later is
covered without opting in.
"""

from __future__ import annotations

import json
import sys
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from reference_service.settings import Settings, load_settings

# The same string pydantic prints for a SecretStr, so the output reads as
# one convention rather than two.
MASK = "**********"


def mask_url_credentials(value: str) -> str:
    """Blank the password of a URL that carries one; anything else unchanged.

    Works on the netloc as text rather than through `.hostname`/`.port`,
    which lower-case the host, strip IPv6 brackets and raise on a bad
    port -- this must print what is configured, only with the password
    removed.
    """
    try:
        parts = urlsplit(value)
    except ValueError:
        return value
    credentials, at, host_port = parts.netloc.rpartition("@")
    if not at or ":" not in credentials:
        return value
    user, _, _ = credentials.partition(":")
    return urlunsplit(parts._replace(netloc=f"{user}:{MASK}@{host_port}"))


def mask(value: Any) -> Any:
    """Apply `mask_url_credentials` to every string at any depth."""
    if isinstance(value, dict):
        return {key: mask(item) for key, item in value.items()}
    if isinstance(value, list):
        return [mask(item) for item in value]
    if isinstance(value, str):
        return mask_url_credentials(value)
    return value


def resolved_configuration(settings: Settings) -> dict[str, Any]:
    dumped: dict[str, Any] = settings.model_dump(mode="json")
    masked: dict[str, Any] = mask(dumped)
    return masked


def main(env_file: str | None = ".env") -> int:
    # Exits 78 with a readable, value-free message when the environment
    # is invalid -- see load_settings.
    settings = load_settings(env_file=env_file)
    print(json.dumps(resolved_configuration(settings), indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
