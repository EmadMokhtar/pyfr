"""The adapter against recorded responses from the stub upstream.

`record_mode` is `none` by default in pytest-recording, so a request with
no matching cassette FAILS rather than quietly reaching the network.
Verified: it raises vcr.errors.CannotOverwriteExistingCassetteException.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from reference_service.domain.errors import PaymentDeclinedError
from reference_service.domain.order import Money, OrderId
from reference_service.infrastructure.http.breaker import CircuitBreaker
from reference_service.infrastructure.http.client import build_http_client
from reference_service.infrastructure.http.payment_gateway import (
    HttpPaymentGateway,
)
from reference_service.settings import HttpClientSettings
from tests.recorded.conftest import PAYMENT_STUB_URL

# Fixed, not random: the cassette is matched on the request body, and the
# order id is in it. A uuid4() here would match nothing on replay.
ORDER_ID = OrderId(UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"))


def build_gateway() -> tuple[HttpPaymentGateway, object]:
    client = build_http_client(HttpClientSettings(), base_url=PAYMENT_STUB_URL)
    gateway = HttpPaymentGateway(
        client,
        breaker=CircuitBreaker(failure_threshold=5, reset_after_seconds=30.0),
        attempts=3,
        wait_initial_seconds=0.1,
        wait_max_seconds=1.0,
    )
    return gateway, client


@pytest.mark.vcr
async def test_an_authorisation_is_parsed_from_the_real_wire_format() -> None:
    gateway, client = build_gateway()
    try:
        authorisation = await gateway.authorise(
            order_id=ORDER_ID,
            total=Money(amount=Decimal("42.00"), currency="EUR"),
        )
    finally:
        await client.aclose()  # type: ignore[attr-defined]

    assert authorisation.id == "auth_stub_0001"


@pytest.mark.vcr
async def test_a_declined_payment_is_parsed_from_the_real_wire_format() -> None:
    gateway, client = build_gateway()
    try:
        with pytest.raises(PaymentDeclinedError, match="insufficient_funds"):
            await gateway.authorise(
                order_id=ORDER_ID,
                total=Money(amount=Decimal("999.99"), currency="EUR"),
            )
    finally:
        await client.aclose()  # type: ignore[attr-defined]
