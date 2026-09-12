"""The adapter's decisions: what is an answer, what is a failure, and
which of those the breaker is allowed to count."""

from __future__ import annotations

from collections.abc import Iterator
from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import stamina

from reference_service.domain.errors import PaymentDeclinedError
from reference_service.domain.order import Money, OrderId
from reference_service.infrastructure.errors import PaymentUnavailableError
from reference_service.infrastructure.http.breaker import CircuitBreaker
from reference_service.infrastructure.http.payment_gateway import (
    HttpPaymentGateway,
)

TOTAL = Money(amount=Decimal("42.00"), currency="EUR")


@pytest.fixture(autouse=True)
def _no_backoff() -> Iterator[None]:
    """Keep the configured attempt count, drop the waiting.

    NOT a plain `set_testing(True)`: that sets attempts to 1, which would
    make `test_a_retryable_failure_is_one_logical_failure` below pass
    while proving nothing. `cap=True` keeps the smaller configured value.
    """
    with stamina.set_testing(True, attempts=100, cap=True):
        yield


def build_gateway(
    handler: object, *, breaker: CircuitBreaker | None = None
) -> tuple[HttpPaymentGateway, httpx.AsyncClient]:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        base_url="http://gateway",
    )
    gateway = HttpPaymentGateway(
        client,
        breaker=breaker
        or CircuitBreaker(failure_threshold=2, reset_after_seconds=30.0),
        attempts=3,
        wait_initial_seconds=0.01,
        wait_max_seconds=0.02,
    )
    return gateway, client


async def test_an_authorised_payment_returns_its_reference() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "auth_abc123", "status": "authorised"})

    gateway, client = build_gateway(handler)
    try:
        authorisation = await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert authorisation.id == "auth_abc123"


async def test_a_decline_is_an_answer_not_a_failure() -> None:
    """One request, no retry, and the breaker stays closed. Retrying a
    decline re-submits a payment; counting it as a failure would open the
    circuit against a gateway that is working perfectly.

    `failure_threshold=1`, not some larger number: with threshold 1, a
    SINGLE failure opens the circuit, so if a future change made the
    decline count against the breaker after all, `breaker.state` would be
    `"open"` here and the assertion below would catch it. A higher
    threshold would let exactly that regression through silently — one
    call can never reach a threshold above 1, so the assertion would keep
    passing whether or not the decline was ever counted, proving nothing.
    """
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(402, json={"reason": "insufficient_funds"})

    breaker = CircuitBreaker(failure_threshold=1, reset_after_seconds=30.0)
    gateway, client = build_gateway(handler, breaker=breaker)
    try:
        with pytest.raises(PaymentDeclinedError, match="insufficient_funds"):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert calls == 1
    assert breaker.state.value == "closed"


async def test_a_decline_reason_is_bounded_to_200_characters() -> None:
    """Relaying the provider's decline reason into a public 402 body is
    deliberate (see test_a_decline_is_an_answer_not_a_failure above) —
    but the provider puts no limit on that field's length, and it is the
    least trustworthy input in this system. An unbounded relay would let
    an arbitrarily long (or malicious) provider response become an
    arbitrarily large response body from this service."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"reason": "x" * 10_000})

    breaker = CircuitBreaker(failure_threshold=1, reset_after_seconds=30.0)
    gateway, client = build_gateway(handler, breaker=breaker)
    try:
        with pytest.raises(PaymentDeclinedError) as excinfo:
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert len(excinfo.value.reason) == 200


async def test_a_retryable_failure_is_retried_and_counts_once() -> None:
    """Three upstream requests, ONE logical failure. The breaker counts
    logical calls; nested the other way round it would open three times
    faster than its threshold says."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={})

    breaker = CircuitBreaker(failure_threshold=2, reset_after_seconds=30.0)
    gateway, client = build_gateway(handler, breaker=breaker)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert calls == 3
    assert breaker.state.value == "closed", "one logical failure, threshold is two"


async def test_an_open_circuit_reports_unavailable_without_calling() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={})

    breaker = CircuitBreaker(failure_threshold=1, reset_after_seconds=30.0)
    gateway, client = build_gateway(handler, breaker=breaker)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
        calls_after_first = calls

        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert calls == calls_after_first, "an open circuit must not reach the gateway"


async def test_a_connect_failure_is_retried_then_reported_unavailable() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection refused", request=request)

    gateway, client = build_gateway(handler)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert calls == 3


async def test_a_read_timeout_is_not_retried() -> None:
    """The gateway may have taken the payment and been slow to say so.
    Retrying that is a double charge — see is_retryable's docstring."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("too slow", request=request)

    gateway, client = build_gateway(handler)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert calls == 1


async def test_an_unparseable_body_is_reported_unavailable() -> None:
    """A 200 whose body is not JSON at all — e.g. a proxy's own HTML error
    page slipped in front of the real gateway. `response.json()` raises
    `json.JSONDecodeError` (a `ValueError`), which must become
    `PaymentUnavailableError`, not escape uncaught."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, content=b"<html>proxy error</html>")

    breaker = CircuitBreaker(failure_threshold=2, reset_after_seconds=30.0)
    gateway, client = build_gateway(handler, breaker=breaker)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    # The HTTP exchange itself succeeded — the breaker only sees
    # `breaker.call`'s callable return without raising, before this body
    # is ever parsed — so this must not count as a breaker failure any
    # more than a decline does.
    assert breaker.state.value == "closed"


async def test_a_response_missing_the_authorisation_id_is_reported_unavailable() -> (
    None
):
    """A 201 with a body that parses as JSON but has no `id` field.
    `response.json()["id"]` raises `KeyError`, which must become
    `PaymentUnavailableError` — a `KeyError` here is the provider's
    contract breaking, not evidence of a bug on our side."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"status": "authorised"})

    gateway, client = build_gateway(handler)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()


async def test_a_blank_authorisation_id_is_reported_unavailable() -> None:
    """A 201 carrying `{"id": ""}` is as unusable as one carrying no id.

    The domain refuses to build an Authorisation from a blank reference,
    which raises a pydantic ValidationError — a ValueError — so it lands
    in the same handler as every other unreadable answer.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "", "status": "authorised"})

    gateway, client = build_gateway(handler)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()


async def test_a_wrongly_typed_authorisation_id_is_reported_unavailable() -> None:
    """A 201 whose `id` is a JSON number rather than a string. This is the
    dangerous row: `Authorisation(id=...)` raises pydantic's
    `ValidationError`, and api/errors.py has a registered handler for
    exactly that type — one that reports a 422 "Request validation
    failed" to the CALLER. Left unmapped, an upstream fault would look to
    the client like their own request was invalid. It must become
    `PaymentUnavailableError` instead."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": 123, "status": "authorised"})

    gateway, client = build_gateway(handler)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()


async def test_a_malformed_decline_body_is_reported_unavailable_not_declined() -> None:
    """A 402 whose body is valid JSON but not a mapping — `.get("reason", ...)`
    raises `AttributeError` on a list. Only a MALFORMED 402 becomes
    unavailable; a well-formed one still raises `PaymentDeclinedError`,
    covered by test_a_decline_is_an_answer_not_a_failure above."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json=[])

    gateway, client = build_gateway(handler)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()


async def test_the_request_carries_an_idempotency_key_and_the_amount() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"id": "auth_abc123", "status": "authorised"})

    order_id = OrderId(uuid4())
    gateway, client = build_gateway(handler)
    try:
        await gateway.authorise(order_id=order_id, total=TOTAL)
    finally:
        await client.aclose()

    request = seen[0]
    assert request.headers["idempotency-key"] == str(order_id)
    # A string, never a float. 42.00 as JSON number round-trips through a
    # binary double and can arrive as 42.000000000000004; money is sent as
    # text for the same reason MoneyOut renders it as text.
    assert b'"amount":"42.00"' in request.content.replace(b" ", b"")


async def test_the_idempotency_key_is_the_same_on_every_retry() -> None:
    """The one property the whole "safe to retry" argument in
    infrastructure/http/client.py rests on: a gateway that honours
    `Idempotency-Key` will not authorise the same order twice ONLY if
    every retry of one logical call carries the SAME key. Nothing before
    this test asserted that directly — every other retry test only counts
    calls or checks the final outcome, never what the retried requests
    actually carried.

    Two 503s (retryable, per `RETRYABLE_STATUS` in client.py) then a
    success: three requests reach the handler, one logical call to
    `authorise`. If a future change generated a fresh key per HTTP attempt
    instead of once per logical call — the exact regression this guards
    against — the three captured headers would differ and the assertion
    below would fail.
    """
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if len(seen) < 3:
            return httpx.Response(503, json={})
        return httpx.Response(201, json={"id": "auth_abc123", "status": "authorised"})

    order_id = OrderId(uuid4())
    gateway, client = build_gateway(handler)
    try:
        await gateway.authorise(order_id=order_id, total=TOTAL)
    finally:
        await client.aclose()

    assert len(seen) == 3, "the handler above only reaches the 201 on the third call"
    keys = {request.headers["idempotency-key"] for request in seen}
    assert keys == {str(order_id)}, f"every retry must carry the SAME key; saw {keys}"
