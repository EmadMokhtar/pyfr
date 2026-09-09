"""The shared outbound HTTP client and its retry policy.

One client per process, built in the composition root and closed at
shutdown. Not one per request: a fresh client per call throws away the
connection pool, so every outbound request pays a new TCP and TLS
handshake, and nothing bounds how many sockets the service opens.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from reference_service.settings import HttpClientSettings

# Statuses where retrying is safe AND might help.
#
# 429 is the gateway asking us to come back. 502, 503 and 504 all say the
# request was not processed by the thing behind the gateway. 500 is
# deliberately ABSENT: it is ambiguous — the gateway may have taken the
# payment and then failed while telling us — and retrying an ambiguous
# failure on a non-idempotent POST is how a customer gets charged twice.
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


def is_retryable(exc: Exception) -> bool:
    """What may be retried, and — more to the point — what may not.

    The rule is "can this have been delivered?", not "did this fail?".

    A ConnectError or ConnectTimeout proves the request never reached the
    gateway, so a second attempt cannot authorise twice. A ReadTimeout
    proves nothing of the sort: the gateway may have taken the payment and
    simply been slow to say so, and retrying that is a double charge.
    Making read timeouts safe needs an idempotency key the gateway
    honours, which is M9 — until then this stays narrow on purpose.
    """
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return False


def build_http_client(
    settings: HttpClientSettings,
    *,
    base_url: str,
    headers: Mapping[str, str] | None = None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        headers=dict(headers or {}),
        # Every phase named explicitly. `httpx.Timeout(5.0)` would set all
        # four, but writing them out is what makes a reviewer notice if
        # one is ever dropped.
        timeout=httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.read_timeout_seconds,
            write=settings.write_timeout_seconds,
            pool=settings.pool_timeout_seconds,
        ),
        limits=httpx.Limits(
            max_connections=settings.max_connections,
            max_keepalive_connections=settings.max_keepalive_connections,
        ),
    )
