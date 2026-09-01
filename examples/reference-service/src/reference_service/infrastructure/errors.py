"""Errors raised by the infrastructure layer itself.

Deliberately NOT a DomainError. A DomainError says a business rule was
broken, which is a statement about the caller's request and maps to a 4xx.
What lives here says storage handed back something the domain refuses to
accept, which is this service's fault, not the caller's, and maps to a 5xx.
Keeping it out of both DomainError's hierarchy and services/errors.py's
ServiceDefectError is what stops it being mistaken for either in
api/errors.py — and it lives here, in infrastructure/, rather than in
services/errors.py, because infrastructure must not import services (an
upward dependency the architecture forbids); a new error type needed only
by infrastructure belongs beside the code that raises it.
"""

from __future__ import annotations


class CorruptPersistedDataError(Exception):
    """A stored row failed the domain's own validation on the way back out.

    infrastructure/db/mappers.py's to_domain() rebuilds an Order through the
    real Pydantic model, which reruns every validator — including
    Order.total_must_match_lines — on load, not only on write. A row can
    fail that check without the application ever writing anything invalid:
    hand edits, a restore from a backup taken mid-migration, or a write from
    another service entirely can all leave a row PostgreSQL is perfectly
    willing to return but the domain is not willing to accept.

    That failure is a storage consistency problem, not something the caller
    who happened to ask for this order did wrong — so it must not become a
    pydantic.ValidationError that escapes to api/errors.py's
    _pydantic_validation_error handler, which exists for genuine client
    faults and (before this type existed) turned a corrupted row into a 422
    whose body quoted the row's own field values, including internal_note.
    No handler is registered for this type on purpose — it falls through to
    the catch-all in api/errors.py, which logs the full traceback and
    returns a 500 that describes none of our internals.
    """
