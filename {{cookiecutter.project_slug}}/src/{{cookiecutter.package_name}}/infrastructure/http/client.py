"""The shared outbound HTTP client and its retry policy.

One client per process, built in the composition root and closed at
shutdown. Not one per request: a fresh client per call throws away the
connection pool, so every outbound request pays a new TCP and TLS
handshake, and nothing bounds how many sockets the service opens.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from {{ cookiecutter.package_name }}.settings import HttpClientSettings

# Statuses where retrying is safe AND might help.
#
# The rule is "was this request delivered to whatever sits behind the
# gateway?", not "did this response look bad?". Applied status by status:
#
#   429 Too Many Requests — rejected at the edge, before the gateway even
#       looked at what was behind it. Never delivered. Retry.
#   503 Service Unavailable — the gateway is declaring itself unable to
#       handle requests at all. Never delivered. Retry.
#   502 Bad Gateway — the gateway DID forward the request and got back a
#       response it could not make sense of. Delivered; upstream may well
#       have processed it before answering strangely. Do not retry.
#   504 Gateway Timeout — the gateway forwarded the request and got no
#       timely answer. Delivered; this is the exact same ambiguity that
#       disqualifies ReadTimeout below, wearing a status code instead of
#       an exception. Do not retry.
#   500 — ambiguous for the same reason as 502/504; already excluded.
#
# So only 429 and 503 belong here. It is tempting to lump 502 and 504 in
# with them because all four "smell like" transient gateway trouble — but
# 502 and 504 both mean the request got there, and retrying a
# non-idempotent POST that got there risks the double charge this module
# exists to prevent. If you are about to add 502 or 504 back because
# leaving them out looks like an oversight: it is not, see above.
RETRYABLE_STATUS = frozenset({429, 503})


def is_retryable(exc: Exception) -> bool:
    """What may be retried, and — more to the point — what may not.

    The rule is "can this have been delivered?", not "did this fail?".

    A ConnectError or ConnectTimeout proves the request never reached the
    gateway, so a second attempt cannot authorise twice. PoolTimeout is
    not a subclass of either (verified: it is a sibling of ConnectTimeout
    directly under httpx.TimeoutException) but belongs in the same bucket
    for the same reason — it fires while waiting for a free connection
    from OUR OWN pool, before any socket to the gateway is even opened, so
    nothing was submitted either.

    A ReadTimeout proves nothing of the sort: the gateway may have taken
    the payment and simply been slow to say so, and retrying that is a
    double charge. WriteTimeout is refused for the same reason and is
    deliberately NOT special-cased below — it means the request was
    partially or wholly on the wire when the deadline hit, so whether the
    gateway received all of it is exactly as unknowable as whether a slow
    responder already processed it. It falls through to the final
    `return False` along with ReadTimeout.

    Making read/write timeouts safe needs an idempotency key the gateway
    honours, which is M9 — until then this stays narrow on purpose.
    """
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout | httpx.PoolTimeout):
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
