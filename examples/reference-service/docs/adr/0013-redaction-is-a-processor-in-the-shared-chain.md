---
last_reviewed: 2026-09-11
---

# 0013. Redact by key name, in the shared processor chain

**Status:** Accepted
**Date:** 2026-09-11

## Context

Spec 7.6 and spec 12 item 6 ask that a field like `password` or
`card_number` cannot reach the log backend by accident — including one
logged by a third-party library the application does not control. Three
designs were possible: each call site masks what it logs; a processor in
structlog's chain masks by field name, after the call but before the
record is rendered; or a filter scans every rendered string for
secret-shaped values, independent of the key a value was stored under.

## Decision

We mask by key name, in one processor appended **last** to the shared
processor chain in `observability/logging.py`. Last means it runs after
every other processor — including `structlog.contextvars.merge_contextvars`,
which binds request-scoped values such as the correlation id — so it sees
the fully assembled record, bound context included. That same processor
list is also the standard library's `foreign_pre_chain`, wired in through
`structlog.stdlib.ProcessorFormatter`, so a record a third-party library
emits through the standard `logging` module is masked by the identical
rule. Matching is exact, case-insensitive, and treats `-` and `_` alike,
at any depth of nested dicts and lists — `redaction.py`'s `_normalise` and
`_redact_value` walk the record recursively to do this. The OTLP export
handler copies a standard-library record's `extra=` attributes across
without the processor chain, so `RedactingFilter` on that handler runs the
same rule over them first. The field names to mask live in
`APP_LOG__REDACT_FIELDS`, which replaces `redaction.py`'s
`DEFAULT_REDACT_FIELDS` rather than extending it.

## Alternatives considered

- **Call-site masking.** Rejected: the one call site where masking is
  forgotten is the one that matters. A rule enforced by convention at
  dozens of call sites fails exactly when someone is in a hurry or new to
  the codebase, instead of holding everywhere by construction.
- **A filter that scans rendered values for secret-shaped strings.**
  Rejected: it needs a regex per secret shape, produces false positives on
  ordinary hexadecimal identifiers, and still cannot reliably tell a token
  from a trace id — both are opaque strings that look alike.
- **Extending the default field list instead of replacing it.** Rejected:
  two sources would describe one setting, with no way to reason about the
  effective list from either alone, and no way to *remove* a default name
  that collides with a legitimate field the service happens to use.

## Consequences

A field named `token` is always masked, even when it is an unrelated
value such as a pagination token — the fix is to rename the field or
configure `APP_LOG__REDACT_FIELDS` to exclude it. A secret interpolated
into a message string, as in `log.info(f"token {token}")`, is **not**
covered: nothing reads message text, only keys. `SecretStr` and
`load_settings`'s `include_input=False` close the two value-shaped holes
that remain in our own code. The limitation is documented in
`docs/reference/logging.md`.

Full reasoning: [the M6 plan's Design section](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/plans/2026-09-11-pyfr-m6-supply-chain.md).
