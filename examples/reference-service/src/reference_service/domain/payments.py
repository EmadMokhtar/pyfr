"""The payment port: what the domain needs, not how it is done.

Imports Pydantic and the standard library, exactly as the rest of this
layer does. `httpx` lives on the far side of this file, in
infrastructure/http/payment_gateway.py — the domain names the operation
and never learns that it travels over HTTP.

Two errors can come out of an implementation, and they belong in
different places on purpose:

  - PaymentDeclinedError (domain/errors.py) — the gateway answered, and
    the answer was no. A statement about the caller's payment instrument,
    so a business rule, so 4xx.
  - PaymentUnavailableError (infrastructure/errors.py) — the gateway did
    not answer at all, or the circuit was open. A statement about our
    dependency, not the caller, so 5xx.

The second lives in infrastructure for the same reason
CorruptPersistedDataError does: it is raised by the adapter, and
infrastructure must not import services.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from reference_service.domain.order import AuthorisationId, Money, OrderId


class Authorisation(BaseModel):
    """Proof that a payment was authorised. A value object: no identity of
    its own beyond the reference the provider gave us."""

    model_config = ConfigDict(frozen=True)

    id: AuthorisationId


class PaymentGateway(Protocol):
    """Authorise a payment, or say why not.

    Raises `PaymentDeclinedError` when the provider says no, and
    `PaymentUnavailableError` when there is no answer to be had. Returning
    a "failed" Authorisation instead would let a caller forget to check
    it; raising cannot be ignored by accident.
    """

    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation: ...
