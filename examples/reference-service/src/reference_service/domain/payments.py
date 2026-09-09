"""The payment port: what the domain needs, not how it is done.

Imports Pydantic and the standard library, exactly as the rest of this
layer does. `httpx` lives on the far side of this file, in
infrastructure/http/payment_gateway.py — the domain names the operation
and never learns that it travels over HTTP.

Two errors can come out of an implementation, and they belong in
different places on purpose because they are different KINDS of thing:

  - PaymentDeclinedError (domain/errors.py) — the gateway answered, and
    the answer was no. A statement about the caller's payment instrument:
    their fault, and a business outcome, not a failure.
  - PaymentUnavailableError (infrastructure/errors.py) — the gateway did
    not answer at all, or the circuit was open. A statement about our
    dependency: not the caller's fault, and the same request may well
    succeed if it is simply tried again later.

The second lives in infrastructure for the same reason
CorruptPersistedDataError does: it is raised by the adapter, and
infrastructure must not import services. Deciding what either of these
means for a caller over HTTP is not this file's job — that mapping lives
in api/errors.py.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from pydantic import BaseModel, ConfigDict

from reference_service.domain.order import AuthorisationId, Money, OrderId


class Authorisation(BaseModel):
    """Proof that a payment was authorised. A value object: no identity of
    its own beyond the reference the provider gave us."""

    model_config = ConfigDict(frozen=True)

    id: AuthorisationId


@runtime_checkable
class PaymentGateway(Protocol):
    """Authorise a payment, or say why not.

    Raises `PaymentDeclinedError` when the provider says no, and
    `PaymentUnavailableError` when there is no answer to be had. Returning
    a "failed" Authorisation instead would let a caller forget to check
    it; raising cannot be ignored by accident.

    `@runtime_checkable` lets `isinstance` confirm that an implementer has
    a method named `authorise` at all — see
    tests/unit/test_order.py::test_the_payment_gateway_port_is_structural
    for what that check does and does not prove.
    """

    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation: ...
