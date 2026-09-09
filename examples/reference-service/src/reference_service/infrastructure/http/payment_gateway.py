"""The HTTP implementation of the payment port.

Three layers, and their order is the design:

    breaker( retry( one HTTP request ) )

The breaker is OUTSIDE. Retries are attempts at one logical call, so
three retries against a dead gateway must register as one failure. Nested
the other way, the breaker would open at a third of its configured
threshold and nobody would understand why.

And a declined payment is neither: it is a successful call with a
negative answer. It never retries and never counts towards the breaker,
which is why `_send` returns 402 as a value rather than raising.
"""

from __future__ import annotations

import httpx
import stamina
import structlog

from reference_service.domain.errors import PaymentDeclinedError
from reference_service.domain.order import AuthorisationId, Money, OrderId
from reference_service.domain.payments import Authorisation
from reference_service.infrastructure.errors import PaymentUnavailableError
from reference_service.infrastructure.http.breaker import (
    CircuitBreaker,
    CircuitOpenError,
)
from reference_service.infrastructure.http.client import is_retryable

# Statuses that are ANSWERS rather than failures: the gateway considered
# the request and replied. Everything else is a failure the breaker and
# the retry policy get to see.
_ANSWER_STATUSES = frozenset({200, 201, 402})

_AUTHORISATIONS_PATH = "/authorisations"

_logger = structlog.get_logger(__name__)


class HttpPaymentGateway:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        breaker: CircuitBreaker,
        attempts: int,
        wait_initial_seconds: float,
        wait_max_seconds: float,
    ) -> None:
        self._client = client
        self._breaker = breaker
        # Built once. A RetryingCaller rather than the @stamina.retry
        # decorator because the numbers come from settings at runtime, and
        # a decorator would have to close over them at import time.
        self._retrying = stamina.AsyncRetryingCaller(
            attempts=attempts,
            wait_initial=wait_initial_seconds,
            wait_max=wait_max_seconds,
        )

    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        try:
            response = await self._breaker.call(
                lambda: self._retrying(is_retryable, self._send, order_id, total)
            )

            # Body-parsing lives INSIDE this try, not after it. `_send`
            # only promises that the status code is one it recognises as
            # an answer (`_ANSWER_STATUSES`); it says nothing about
            # whether the body is readable JSON, or has the shape we
            # expect. Splitting parsing out of the protected region would
            # let a malformed body escape as whatever raw exception
            # `.json()` or field access happens to throw, uncaught by
            # anything below and therefore uncaught by api/errors.py's
            # DomainError/PaymentUnavailableError handlers too — see the
            # `except` clause below for where each of those would land.
            if response.status_code == httpx.codes.PAYMENT_REQUIRED:
                reason = response.json().get("reason", "unknown")
                raise PaymentDeclinedError(order_id, reason)

            return Authorisation(id=AuthorisationId(response.json()["id"]))
        except CircuitOpenError as exc:
            # Not reaching the gateway at all still means "no answer" to
            # the caller, so it becomes the same error — but it is logged
            # distinctly, because "we refused to try" and "it did not
            # answer" need different responses from an operator.
            _logger.warning("payment.circuit_open", order_id=str(order_id))
            raise PaymentUnavailableError("payment provider circuit is open") from exc
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            _logger.warning(
                "payment.unreachable",
                order_id=str(order_id),
                error_type=type(exc).__name__,
            )
            raise PaymentUnavailableError(
                f"payment provider did not answer: {type(exc).__name__}"
            ) from exc
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            # The gateway DID answer — `_send` already accepted the status
            # code as one of `_ANSWER_STATUSES` — but the body it sent is
            # not one we can use: not JSON at all (`response.json()`
            # raises `json.JSONDecodeError`, a `ValueError` subclass), a
            # 402 whose body is not even a mapping so `.get` fails
            # (`AttributeError`), or a 201 missing the `id` field
            # (`KeyError`) or carrying it as the wrong type (pydantic's
            # `ValidationError` on `Authorisation(...)`, also a
            # `ValueError` subclass). `TypeError` covers the same family
            # from a different angle: a top-level JSON array instead of
            # an object makes `response.json()["id"]` fail with "list
            # indices must be integers", since a body can be malformed
            # by having the wrong shape even when it parses as valid
            # JSON.
            #
            # This is deliberately treated as "unavailable", the same as
            # a connection failure, and NOT as a bug on our side: a
            # `KeyError` here means the payment provider's contract broke,
            # not that our code has a defect. A payment gateway is the
            # least trustworthy input in this system — a proxy returning
            # an HTML error page, or a field changing shape on their end,
            # is ordinary, not exotic. Treating it as OUR bug would be
            # doubly wrong: it would mislabel their fault as ours, and (if
            # this exception were left to propagate instead) it would let
            # a raw `pydantic.ValidationError` reach api/errors.py's
            # registered `PydanticValidationError` handler, which reports
            # a 422 "Request validation failed" to the CALLER — telling
            # them their request was invalid, when the actual problem is
            # the gateway's response. See task-10-findings.md for the
            # measured escape routes this closes.
            #
            # The message stays body-free on purpose: log the status code,
            # which is diagnostic and not sensitive, never the body, which
            # could contain gateway-side account or transaction detail we
            # have no business relaying into our own logs or a caller's
            # response.
            _logger.warning(
                "payment.unreadable_response",
                order_id=str(order_id),
                status_code=response.status_code,
                error_type=type(exc).__name__,
            )
            raise PaymentUnavailableError(
                "payment provider returned an unreadable answer"
            ) from exc

    async def _send(self, order_id: OrderId, total: Money) -> httpx.Response:
        response = await self._client.post(
            _AUTHORISATIONS_PATH,
            json={
                "order_id": str(order_id),
                # Text, never a JSON number. 42.00 as a double can come
                # back as 42.000000000000004, and a payment amount is the
                # last place to accept that — the same reason MoneyOut
                # renders amounts as strings.
                "amount": str(total.amount),
                "currency": total.currency,
            },
            headers={
                # The order id is generated once, before the first
                # attempt, so every retry of this call carries the same
                # key. A gateway that honours it will not authorise twice.
                # We still do not retry read timeouts (see is_retryable):
                # this makes the connect-phase retries safe even against a
                # gateway that only sometimes honours the key.
                "Idempotency-Key": str(order_id)
            },
        )
        if response.status_code in _ANSWER_STATUSES:
            return response
        raise httpx.HTTPStatusError(
            f"payment gateway returned {response.status_code}",
            request=response.request,
            response=response,
        )
