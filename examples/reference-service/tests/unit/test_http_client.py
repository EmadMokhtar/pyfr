"""The client's two policies: timeouts, and what may be retried."""

from __future__ import annotations

import httpx
import pytest

from reference_service.infrastructure.http.client import (
    build_http_client,
    is_retryable,
)
from reference_service.settings import HttpClientSettings


async def test_every_timeout_phase_is_set() -> None:
    """httpx's default is five seconds on every phase, but a client
    constructed with `timeout=None` anywhere waits forever, and that is
    the single most common way one slow dependency freezes a whole
    service (spec 12, item 5). Assert all four explicitly."""
    client = build_http_client(HttpClientSettings(), base_url="http://gateway")

    timeout = client.timeout
    assert timeout.connect is not None
    assert timeout.read is not None
    assert timeout.write is not None
    assert timeout.pool is not None
    await client.aclose()


async def test_the_timeouts_come_from_settings() -> None:
    settings = HttpClientSettings(
        connect_timeout_seconds=0.5,
        read_timeout_seconds=1.5,
        write_timeout_seconds=2.5,
        pool_timeout_seconds=3.5,
    )

    client = build_http_client(settings, base_url="http://gateway")

    assert client.timeout.connect == 0.5
    assert client.timeout.read == 1.5
    assert client.timeout.write == 2.5
    assert client.timeout.pool == 3.5
    await client.aclose()


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://gateway/authorisations")
    return httpx.HTTPStatusError(
        f"{code}", request=request, response=httpx.Response(code, request=request)
    )


@pytest.mark.parametrize(
    ("error", "retryable", "why"),
    [
        (
            httpx.ConnectError("refused", request=None),
            True,
            "the request provably never arrived",
        ),
        (
            httpx.ConnectTimeout("timed out", request=None),
            True,
            "likewise: no connection, so nothing was submitted",
        ),
        (
            httpx.PoolTimeout("timed out", request=None),
            True,
            "waiting for OUR OWN pool, before any socket opened: nothing submitted "
            "either, even though PoolTimeout is not a subclass of ConnectTimeout",
        ),
        (
            httpx.ReadTimeout("timed out", request=None),
            False,
            "the gateway may have taken the payment and been slow to say so",
        ),
        (
            httpx.WriteTimeout("timed out", request=None),
            False,
            "partly or wholly on the wire; as unknowable as ReadTimeout",
        ),
        (_status_error(429), True, "rejected at the edge, never delivered"),
        (_status_error(503), True, "the gateway did not process it"),
        (
            _status_error(502),
            False,
            "delivered: the gateway forwarded it and got a bad response back",
        ),
        (
            _status_error(504),
            False,
            "delivered, no timely answer — the same ambiguity as ReadTimeout",
        ),
        (_status_error(500), False, "ambiguous: it may have processed it"),
        (_status_error(402), False, "a decline is an answer, not a failure"),
        (_status_error(400), False, "our request is wrong; repeating it will not help"),
    ],
)
def test_what_may_be_retried(error: Exception, retryable: bool, why: str) -> None:
    assert is_retryable(error) is retryable, why
