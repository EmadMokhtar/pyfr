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

from {{ cookiecutter.package_name }}.domain.errors import PaymentDeclinedError
from {{ cookiecutter.package_name }}.domain.order import AuthorisationId, Money, OrderId
from {{ cookiecutter.package_name }}.domain.payments import Authorisation
from {{ cookiecutter.package_name }}.infrastructure.errors import PaymentUnavailableError
from {{ cookiecutter.package_name }}.infrastructure.http.breaker import (
    CircuitBreaker,
    CircuitOpenError,
)
from {{ cookiecutter.package_name }}.infrastructure.http.client import is_retryable

# Statuses that are ANSWERS rather than failures: the gateway considered
# the request and replied. Everything else is a failure the breaker and
# the retry policy get to see.
_ANSWER_STATUSES = frozenset({200, 201, 402})

_AUTHORISATIONS_PATH = "/authorisations"

# `stamina.AsyncRetryingCaller`'s own defaults for the two arguments below
# that PaymentSettings has no field for. Named and passed explicitly in
# `HttpPaymentGateway.__init__` rather than left implicit, for the same
# reason client.py's `build_http_client` writes out all four
# `httpx.Timeout` phases instead of calling `httpx.Timeout(5.0)`: an
# explicit value is one a reviewer can see change; an implicit
# third-party default is one that can change under a routine `stamina`
# version bump with nobody noticing. Chosen to match stamina's current
# defaults exactly, so this commit changes what is visible, not what the
# service does.
_RETRY_WALL_CLOCK_TIMEOUT_SECONDS = 45.0
_RETRY_WAIT_JITTER_SECONDS = 1.0

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
        #
        # `timeout` and `wait_jitter` were left unpassed here until this
        # comment was added, which meant they were silently
        # `stamina.AsyncRetryingCaller`'s own defaults: `timeout=45.0`, a
        # WALL-CLOCK budget for the whole retry loop that acts as a second
        # stop condition alongside `attempts` — three attempts against a
        # gateway with a generous `wait_max_seconds` could in principle
        # stop on the clock rather than on the attempt count — and
        # `wait_jitter=1.0`, meaning the real backoff ceiling was
        # `wait_max_seconds` PLUS up to a further second of jitter, not
        # `wait_max_seconds` alone. See docs/reference/configuration.md's
        # row for `APP_PAYMENT__RETRY_MAX_WAIT_SECONDS` for the same
        # correction on the documentation side.
        self._retrying = stamina.AsyncRetryingCaller(
            attempts=attempts,
            wait_initial=wait_initial_seconds,
            wait_max=wait_max_seconds,
            timeout=_RETRY_WALL_CLOCK_TIMEOUT_SECONDS,
            wait_jitter=_RETRY_WAIT_JITTER_SECONDS,
        )

    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        # Two SEPARATE try blocks, not one, and that split is itself a fix
        # for a bug this comment used to describe as a documented
        # trade-off rather than what it actually was. The old single try
        # wrapped `breaker.call` (which raises CircuitOpenError,
        # httpx.HTTPError or httpx.InvalidURL) and the body-parsing below
        # (which raises ValueError/KeyError/TypeError/AttributeError) under
        # ONE except chain, on the unstated assumption that the second
        # group could only ever be raised by CODE AFTER `response` was
        # already bound. Nothing enforces that assumption: if `breaker.call`
        # or anything inside `self._retrying(...)` ever raised one of
        # ValueError/KeyError/TypeError/AttributeError itself — a plausible
        # library-internal failure, not merely a hypothetical one — the
        # handler below would run with `response` UNBOUND, and
        # `response.status_code` on the logging line would raise
        # `UnboundLocalError` from inside an exception handler, which is a
        # worse failure than the one it was trying to report. Splitting the
        # network call from the body-parsing into two tries removes the
        # possibility structurally: by the time the second try's `except`
        # can run, `response` is already bound, because the only way past
        # the first try without an exception is for `response = await
        # self._breaker.call(...)` to have already succeeded.
        try:
            response = await self._breaker.call(
                lambda: self._retrying(is_retryable, self._send, order_id, total)
            )
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

        # Body-parsing lives in its OWN try, not folded into the one above.
        # `_send` only promises that the status code is one it recognises
        # as an answer (`_ANSWER_STATUSES`); it says nothing about whether
        # the body is readable JSON, or has the shape we expect. Splitting
        # parsing out of a protected region entirely would let a malformed
        # body escape as whatever raw exception `.json()` or field access
        # happens to throw, uncaught by anything below and therefore
        # uncaught by api/errors.py's DomainError/PaymentUnavailableError
        # handlers too — see the `except` clause below for where each of
        # those would land instead.
        try:
            if response.status_code == httpx.codes.PAYMENT_REQUIRED:
                raw_reason = response.json().get("reason", "unknown")
                # Bounded to 200 characters, and coerced to `str` first: the
                # provider's JSON puts no constraint on either the type or
                # the length of this field, and it is relayed into a PUBLIC
                # 402 body below (via api/errors.py's `_domain_error`
                # handler, `detail=str(exc)`). Relaying it AT ALL is
                # deliberate here, and tested by
                # test_a_decline_is_an_answer_not_a_failure: unlike the
                # sibling `_payment_unavailable` handler in api/errors.py,
                # which documents at length why provider text must NEVER
                # reach a caller, a decline reason is meant for the
                # customer whose OWN payment it describes ("insufficient
                # funds"), not an operational detail about our
                # infrastructure. That is a real distinction, not
                # carelessness — but "safe to relay" was never "safe to
                # relay unbounded": an arbitrarily long or malicious string
                # from the least trustworthy input in this system has no
                # business becoming an arbitrarily large response body.
                reason = str(raw_reason)[:200]
                raise PaymentDeclinedError(order_id, reason)

            return Authorisation(id=AuthorisationId(response.json()["id"]))
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
