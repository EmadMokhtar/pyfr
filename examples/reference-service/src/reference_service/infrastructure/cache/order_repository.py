"""A caching decorator over the OrderRepository port.

This class satisfies `OrderRepository` and holds another `OrderRepository`.
Nothing above it — not GetOrder, not PlaceOrder, not the router, not the
domain — knows it exists. That is the point of the port: a cache is added
by wrapping in container.py and removed by not wrapping.

Two rules govern everything below.

FAIL OPEN. Every Redis failure is logged and swallowed, and the wrapped
repository answers. A cache exists to make reads faster; one that can make
them FAIL has made the service strictly worse than having no cache. There
is deliberately no setting that changes this.

THE DATABASE IS THE TRUTH. This class never returns something the wrapped
repository could not have returned, and never lets a write reach Redis
without reaching the repository first.
"""

from __future__ import annotations

import structlog
from pydantic import ValidationError
from redis.asyncio import Redis

from reference_service.domain.order import Order, OrderId
from reference_service.domain.repositories import OrderRepository

_logger = structlog.get_logger(__name__)

# The `v1` is a schema generation, not decoration. Cached payloads are
# serialised Order models, so a change to that model's shape makes every
# existing entry unparseable. Those entries are handled correctly anyway —
# _read treats them as misses — but bumping this prefix retires them all at
# once instead of leaving one TTL's worth of guaranteed misses being logged
# as rejected payloads. Bump it whenever Order gains, loses or renames a
# field.
CACHE_KEY_PREFIX = "order:v1:"


def _key(order_id: OrderId) -> str:
    return f"{CACHE_KEY_PREFIX}{order_id}"


class CachedOrderRepository:
    def __init__(self, inner: OrderRepository, client: Redis, ttl_seconds: int) -> None:
        self._inner = inner
        self._client = client
        self._ttl_seconds = ttl_seconds

    async def get(self, order_id: OrderId) -> Order | None:
        key = _key(order_id)
        cached = await self._read(key)
        if cached is not None:
            return cached

        order = await self._inner.get(order_id)
        if order is not None:
            await self._write(key, order)
        # A missing order is deliberately NOT cached as absent. Negative
        # caching would be safe for correctness — save() invalidates the same
        # key — but it lets anyone fill Redis with entries for identifiers
        # that do not exist simply by asking for them. The read it would save
        # is a single indexed primary-key lookup, which is not worth that.
        return order

    async def save(self, order: Order) -> None:
        # Repository FIRST, then invalidate. The other order is a real bug:
        # delete-then-save leaves a window in which a concurrent reader
        # misses the cache, reads the OLD row from the database, and writes
        # it back with a full TTL — so the stale value outlives the write
        # that was supposed to replace it. Saving first bounds the staleness
        # to the length of the write instead.
        await self._inner.save(order)
        await self._invalidate(_key(order.id))

    async def _read(self, key: str) -> Order | None:
        try:
            raw = await self._client.get(key)
        except Exception:
            # Fail open. Includes redis.RedisError and the TimeoutError that
            # socket_timeout raises; caught broadly on purpose, because the
            # correct response to ANY failure of an optional dependency is
            # the same one, and a narrow list would turn an unanticipated
            # client error into a 500 for a request the database can serve.
            _logger.warning("cache.read_failed", key=key, exc_info=True)
            return None

        if raw is None:
            return None

        try:
            return Order.model_validate_json(raw)
        except ValidationError:
            # Not CorruptPersistedDataError, which is what db/mappers.py
            # raises for the same shape of problem. There, the unreadable row
            # is the only copy and hiding it would serve a wrong answer. Here
            # the real order is one call through to the repository away, so
            # the right move is to ignore the entry and carry on. Logged at
            # warning rather than swallowed silently: a steady stream of
            # these means the prefix above needs bumping.
            _logger.warning("cache.payload_rejected", key=key)
            return None

    async def _write(self, key: str, order: Order) -> None:
        try:
            await self._client.set(
                key, order.model_dump_json().encode(), ex=self._ttl_seconds
            )
        except Exception:
            _logger.warning("cache.write_failed", key=key, exc_info=True)

    async def _invalidate(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except Exception:
            # The one failure with a lasting consequence: the stale entry
            # stays until its TTL expires. That bound is exactly why
            # CacheSettings.ttl_seconds exists and is measured in minutes
            # rather than hours — the TTL is the backstop for this branch.
            _logger.warning("cache.invalidate_failed", key=key, exc_info=True)
