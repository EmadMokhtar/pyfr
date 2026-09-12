"""Errors raised by the service layer itself.

Deliberately NOT a DomainError. A DomainError says a business rule was
broken, which is a statement about the caller's request and maps to a 4xx.
What lives here says this service is defective, which maps to a 5xx. Keeping
them in separate hierarchies is what stops one being mistaken for the other
in api/errors.py.
"""

from __future__ import annotations


class ServiceDefectError(Exception):
    """A use case could not build a valid domain object from a valid command.

    The command passed its own validation, so the caller's input was
    acceptable; the fault is in this service's assembly of the aggregate.
    No handler is registered for this type on purpose — it falls through to
    the catch-all in api/errors.py, which logs the full traceback and
    returns a 500 that describes none of our internals.
    """
