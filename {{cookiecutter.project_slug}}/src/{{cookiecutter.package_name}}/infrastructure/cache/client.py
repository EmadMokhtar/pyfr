"""The Redis connection pool.

One module whose only job is construction, mirroring
infrastructure/db/engine.py and infrastructure/http/client.py: the policy
decisions about timeouts and pool size live here, and the adapter beside it
holds only caching behaviour.
"""

from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis

from {{ cookiecutter.package_name }}.settings import CacheSettings


def build_redis_client(settings: CacheSettings) -> Redis:
    """Build the client. Never raises for an unreachable server.

    redis-py connects lazily, so nothing here touches the network — an
    unreachable Redis surfaces as a failed command, which
    CachedOrderRepository swallows, rather than as a crash at startup. That
    is the correct shape for a fail-open dependency: a cache that is down
    must not stop the process from starting.

    `decode_responses=False` is load-bearing. The values stored are
    `Order.model_dump_json()` bytes, and decoding them to `str` first would
    make every read allocate a string only for Pydantic to encode it back to
    bytes to parse it.
    """
    return Redis.from_pool(
        ConnectionPool.from_url(
            str(settings.dsn),
            max_connections=settings.pool_size,
            # Both deadlines, both required — see CacheSettings for why an
            # unbounded cache call is worse than no cache. socket_timeout
            # covers a command that has been sent and is awaiting a reply;
            # socket_connect_timeout covers establishing the connection.
            # Setting only one leaves the other unbounded.
            socket_connect_timeout=settings.connect_timeout_seconds,
            socket_timeout=settings.operation_timeout_seconds,
            decode_responses=False,
        )
    )
