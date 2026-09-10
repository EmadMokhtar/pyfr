"""The caching decorator.

Every test here answers one question: does the service still behave
correctly when Redis does not? The cache is an optimisation, and an
optimisation that can change an answer or take the service down is a bug
regardless of how much faster it is.
"""

from __future__ import annotations

from decimal import Decimal
from typing import cast
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from reference_service.infrastructure.cache.order_repository import (
    CACHE_KEY_PREFIX,
    CachedOrderRepository,
)
from reference_service.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from tests.fakes import FakeRedis

pytestmark = pytest.mark.asyncio

TTL_SECONDS = 300


def build_order(internal_note: str | None = None) -> Order:
    line = OrderLine(
        sku="SKU-1",
        quantity=2,
        unit_price=Money(amount=Decimal("10.50"), currency="EUR"),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=(line,),
        total=Money(amount=Decimal("21.00"), currency="EUR"),
        internal_note=internal_note,
    )


def build_repository() -> tuple[
    CachedOrderRepository, InMemoryOrderRepository, FakeRedis
]:
    inner = InMemoryOrderRepository()
    client = FakeRedis()
    # FakeRedis satisfies the three methods CachedOrderRepository actually
    # calls, but it is not a subclass of redis.asyncio.Redis, which is a
    # concrete class rather than a Protocol. The cast is for mypy only —
    # nothing here changes at runtime; Python never looks at the annotation.
    repository = CachedOrderRepository(inner, cast(Redis, client), TTL_SECONDS)
    return repository, inner, client


async def test_a_miss_falls_through_and_populates_the_cache() -> None:
    cached, inner, client = build_repository()
    order = build_order()
    await inner.save(order)

    assert await cached.get(order.id) == order

    assert f"{CACHE_KEY_PREFIX}{order.id}" in client.store
    assert client.last_ttl_seconds == TTL_SECONDS


async def test_a_hit_does_not_reach_the_wrapped_repository() -> None:
    """The assertion that proves the cache is doing anything at all: the
    inner repository is emptied, so a value can only come from Redis."""
    cached, inner, _client = build_repository()
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)

    inner.clear()

    assert await cached.get(order.id) == order


async def test_a_cached_order_round_trips_exactly_including_decimals() -> None:
    """Decimal is the field most likely to survive a round trip while
    quietly changing: JSON has no decimal type, so a serialiser that used a
    float would return 21.000000000000004 and the total_must_match_lines
    validator would reject it — or, worse, would not."""
    cached, inner, _client = build_repository()
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)
    inner.clear()

    from_cache = await cached.get(order.id)

    assert from_cache is not None
    assert from_cache.total.amount == Decimal("21.00")
    assert from_cache.lines[0].unit_price.amount == Decimal("10.50")
    assert from_cache == order


async def test_an_unknown_order_is_not_cached_as_absent() -> None:
    """Negative caching is deliberately not done — see the module comment in
    order_repository.py. This asserts the decision, so removing it is a
    visible choice rather than a silent drift."""
    cached, _inner, client = build_repository()
    missing = OrderId(uuid4())

    assert await cached.get(missing) is None
    assert client.store == {}


async def test_save_writes_through_and_invalidates() -> None:
    cached, inner, client = build_repository()
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)
    assert client.store != {}

    await cached.save(order)

    assert client.store == {}
    assert await inner.get(order.id) == order


async def test_a_redis_outage_on_read_still_returns_the_right_answer() -> None:
    """Fail-open, the single most important property here."""
    cached, inner, client = build_repository()
    order = build_order()
    await inner.save(order)
    client.fail_with = ConnectionError("redis is down")

    assert await cached.get(order.id) == order


async def test_a_redis_outage_on_invalidate_does_not_fail_the_save() -> None:
    """save() never calls client.set — only client.delete, via
    _invalidate. This exercises that failure, not a write one."""
    cached, inner, client = build_repository()
    order = build_order()
    client.fail_with = ConnectionError("redis is down")

    await cached.save(order)

    assert await inner.get(order.id) == order


async def test_a_corrupt_cached_payload_is_treated_as_a_miss() -> None:
    """The deliberate contrast with the database adapter, which raises
    CorruptPersistedDataError for the same situation. There, the bad data is
    the only copy. Here the real one is one call away, so the right response
    is to ignore the cache rather than fail the request."""
    cached, inner, client = build_repository()
    order = build_order()
    await inner.save(order)
    client.store[f"{CACHE_KEY_PREFIX}{order.id}"] = b"{not valid json"

    assert await cached.get(order.id) == order


async def test_a_payload_that_parses_but_violates_a_domain_rule_is_a_miss() -> None:
    """Harder than malformed JSON: this is well-formed JSON that the Order
    model refuses, which is what a cache entry written before a model change
    looks like."""
    cached, inner, client = build_repository()
    order = build_order()
    await inner.save(order)
    # A total that disagrees with the lines — total_must_match_lines rejects it.
    client.store[f"{CACHE_KEY_PREFIX}{order.id}"] = (
        order.model_copy(
            update={"total": Money(amount=Decimal("1.00"), currency="EUR")}
        )
        .model_dump_json()
        .encode()
    )

    assert await cached.get(order.id) == order


async def test_the_wrapped_repository_is_never_bypassed_on_save() -> None:
    """A save that reached Redis but not PostgreSQL would lose the order."""
    cached, inner, client = build_repository()
    order = build_order()

    await cached.save(order)

    assert await inner.get(order.id) == order
    assert "set" not in client.calls
