"""Mask secret-bearing fields before a record is rendered.

A processor in the SHARED chain (observability/logging.py), not a
call-site responsibility: it runs on every record however it was
produced — a structlog call, a value bound into context variables by
middleware, or a standard-library record bridged from a third-party
library through `foreign_pre_chain` — so a `password` cannot reach the
log backend because one call site forgot (spec 7.6, spec 12 item 6).

Matching is by KEY NAME only: exact, case-insensitive, `-` and `_`
treated alike, at any depth of nested dicts and lists. It does not scan
string values. A secret interpolated into a message string is not
something a key-name rule can see, and spec 7.6 asks for key names; the
two other ways a secret enters our own records as a value —
`SecretStr`'s representation and `load_settings`'s `include_input=False`
— are already closed in settings.py.
"""

from __future__ import annotations

import logging
from collections.abc import Collection, MutableMapping
from typing import Any

from structlog.types import Processor

REDACTED = "[REDACTED]"

# The attribute names every standard-library record carries, computed once
# at import from a bare record. Anything else on a record came from
# `extra={...}` at the call site, which is what RedactingFilter masks.
_STDLIB_RECORD_ATTRIBUTES = frozenset(
    vars(logging.LogRecord("", 0, "", 0, "", (), None))
)

# Replaced, not extended, by APP_LOG__REDACT_FIELDS (settings.py): one rule
# for what the effective list is, with no hidden merge to reason about.
DEFAULT_REDACT_FIELDS: frozenset[str] = frozenset(
    {
        "password",
        "passwd",
        "secret",
        "secret_key",
        "secret_access_key",
        "token",
        "access_token",
        "refresh_token",
        "api_key",
        "apikey",
        "authorization",
        "cookie",
        "set_cookie",
        "card_number",
        "cvv",
    }
)


def _normalise(key: str) -> str:
    return key.replace("-", "_").lower()


def _redact_value(value: Any, names: frozenset[str]) -> Any:
    """Return `value` with every matching key at any depth masked."""
    if isinstance(value, dict):
        return {
            key: (
                REDACTED
                if isinstance(key, str) and _normalise(key) in names
                else _redact_value(item, names)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_value(item, names) for item in value]
    return value


def make_redactor(field_names: Collection[str]) -> Processor:
    """A structlog processor masking every configured field name."""
    names = frozenset(_normalise(name) for name in field_names)

    def redact_sensitive_fields(
        logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
    ) -> MutableMapping[str, Any]:
        for key in list(event_dict):
            if _normalise(key) in names:
                event_dict[key] = REDACTED
            else:
                event_dict[key] = _redact_value(event_dict[key], names)
        return event_dict

    return redact_sensitive_fields


class RedactingFilter(logging.Filter):
    """Mask matching `extra=` attributes on a standard-library record.

    The OTLP handler copies a record's attributes into the exported
    record's attributes without passing them through the processor chain;
    this filter runs the same rule over them first. Attached only to that
    handler: the stdout handler sees the processor output, not the
    record's attributes.
    """

    def __init__(self, field_names: Collection[str]) -> None:
        super().__init__()
        self._names = frozenset(_normalise(name) for name in field_names)

    def filter(self, record: logging.LogRecord) -> bool:
        for key, value in list(vars(record).items()):
            if key in _STDLIB_RECORD_ATTRIBUTES:
                continue
            if _normalise(key) in self._names:
                setattr(record, key, REDACTED)
            else:
                setattr(record, key, _redact_value(value, self._names))
        return True
