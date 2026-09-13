"""The caching decorator against a real Redis.

What the unit tests cannot cover: that redis-py, the real serialisation and
a real TTL agree with each other. FakeRedis stores whatever bytes it is
given and hands them back; a real server has an encoding, an expiry clock
and a maximum value size.

This module carries its own `pytestmark` with `loop_scope="session"`, per
the rule in this directory's conftest.py: a module using a session-scoped
async fixture without it crashes with `RuntimeError: Event loop is closed`
on the second test that opens a connection.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from {{ cookiecutter.package_name }}.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from {{ cookiecutter.package_name }}.infrastructure.cache.client import build_redis_client
from {{ cookiecutter.package_name }}.infrastructure.cache.order_repository import (
    CACHE_KEY_PREFIX,
    CachedOrderRepository,
)
from {{ cookiecutter.package_name }}.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from {{ cookiecutter.package_name }}.settings import CacheSettings

pytestmark = pytest.mark.asyncio(loop_scope="session")


def build_order() -> Order:
    line = OrderLine(
        sku="SKU-1",
        quantity=3,
        unit_price=Money(amount=Decimal("19.99"), currency="GBP"),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=(line,),
        total=Money(amount=Decimal("59.97"), currency="GBP"),
        internal_note="never leaves the service",
    )


async def test_an_order_round_trips_through_a_real_redis(
    redis_client: Redis,
) -> None:
    inner = InMemoryOrderRepository()
    cached = CachedOrderRepository(inner, redis_client, ttl_seconds=300)
    order = build_order()
    await inner.save(order)

    await cached.get(order.id)
    inner.clear()
    from_cache = await cached.get(order.id)

    assert from_cache == order
    # The value most likely to survive a round trip while quietly changing.
    assert from_cache is not None
    assert from_cache.total.amount == Decimal("59.97")


async def test_the_ttl_is_actually_applied_on_the_server(
    redis_client: Redis,
) -> None:
    """FakeRedis records the TTL argument. Only a real server can say the
    key genuinely expires — a `set` whose expiry argument was passed in the
    wrong unit would pass the unit test and leak entries here."""
    inner = InMemoryOrderRepository()
    cached = CachedOrderRepository(inner, redis_client, ttl_seconds=300)
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)

    remaining = await redis_client.ttl(f"{CACHE_KEY_PREFIX}{order.id}")

    # Seconds, not milliseconds: a value near 300 proves the unit is right.
    assert 290 < remaining <= 300


async def test_a_one_second_ttl_expires_and_the_read_falls_through(
    redis_client: Redis,
) -> None:
    inner = InMemoryOrderRepository()
    cached = CachedOrderRepository(inner, redis_client, ttl_seconds=1)
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)

    await asyncio.sleep(1.5)

    assert await redis_client.get(f"{CACHE_KEY_PREFIX}{order.id}") is None
    # Still correct after expiry — it falls through to the repository.
    assert await cached.get(order.id) == order


async def test_save_removes_the_key_from_a_real_server(
    redis_client: Redis,
) -> None:
    inner = InMemoryOrderRepository()
    cached = CachedOrderRepository(inner, redis_client, ttl_seconds=300)
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)
    assert await redis_client.exists(f"{CACHE_KEY_PREFIX}{order.id}") == 1

    await cached.save(order)

    assert await redis_client.exists(f"{CACHE_KEY_PREFIX}{order.id}") == 0


async def test_an_unreachable_redis_fails_open_against_a_real_client(
    cache_settings: CacheSettings,
) -> None:
    """The fail-open path with a REAL client and a genuinely dead address.

    FakeRedis raises an exception we chose. This raises whatever redis-py
    actually raises when nothing is listening — the case that matters, and
    the one a hand-picked exception type can quietly fail to cover.
    Port 1 is reserved and never has a listener.

    `cache_settings` is not dead code even though the body never reads it:
    requesting the fixture is what forces the session-scoped Redis
    container to start, keeping this module consistent with the others in
    this directory that need it running even when this specific test talks
    to a different, deliberately unreachable address instead.
    """
    dead = CacheSettings(dsn="redis://127.0.0.1:1/0")  # type: ignore[arg-type]
    client = build_redis_client(dead)
    try:
        inner = InMemoryOrderRepository()
        cached = CachedOrderRepository(inner, client, ttl_seconds=300)
        order = build_order()
        await inner.save(order)

        assert await cached.get(order.id) == order
        await cached.save(order)
    finally:
        await client.aclose()
