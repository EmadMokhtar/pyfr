"""The breaker's state machine, against a clock we control.

Every test here would otherwise need to sleep through the reset window,
which is the reason breaker tests are usually slow and flaky. The clock is
a constructor argument precisely so they are neither.
"""

from __future__ import annotations

import asyncio

import pytest

from reference_service.infrastructure.http.breaker import (
    BreakerState,
    CircuitBreaker,
    CircuitOpenError,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Boom(Exception):
    pass


def make_breaker(clock: FakeClock) -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=3, reset_after_seconds=30.0, clock=clock)


async def succeed() -> str:
    return "ok"


async def fail() -> str:
    raise Boom


async def test_a_new_breaker_is_closed_and_passes_calls_through() -> None:
    breaker = make_breaker(FakeClock())

    assert breaker.state is BreakerState.CLOSED
    assert await breaker.call(succeed) == "ok"


async def test_it_opens_only_after_the_threshold_is_reached() -> None:
    breaker = make_breaker(FakeClock())

    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail)
    assert breaker.state is BreakerState.CLOSED, "two failures is not three"

    with pytest.raises(Boom):
        await breaker.call(fail)
    assert breaker.state is BreakerState.OPEN


async def test_the_failure_count_is_consecutive_not_cumulative() -> None:
    """A success resets the count. Otherwise a service failing 1% of the
    time trips the breaker after a few hundred healthy requests."""
    breaker = make_breaker(FakeClock())

    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail)
    await breaker.call(succeed)
    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail)

    assert breaker.state is BreakerState.CLOSED


async def test_an_open_breaker_refuses_without_calling() -> None:
    clock = FakeClock()
    breaker = make_breaker(clock)
    calls = 0

    async def count() -> str:
        nonlocal calls
        calls += 1
        raise Boom

    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(count)
    assert calls == 3

    with pytest.raises(CircuitOpenError):
        await breaker.call(count)
    assert calls == 3, "an open breaker must not reach the dependency at all"


async def test_it_half_opens_once_the_reset_window_has_passed() -> None:
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail)

    clock.advance(29.9)
    assert breaker.state is BreakerState.OPEN

    clock.advance(0.1)
    assert breaker.state is BreakerState.HALF_OPEN


async def test_a_successful_probe_closes_the_breaker() -> None:
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail)
    clock.advance(30.0)

    assert await breaker.call(succeed) == "ok"
    assert breaker.state is BreakerState.CLOSED


async def test_a_failed_probe_reopens_immediately() -> None:
    """One failure, not another full threshold. The dependency has already
    proved it is unwell; making it fail three more times to say so again
    just sends three more doomed requests into it."""
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail)
    clock.advance(30.0)

    with pytest.raises(Boom):
        await breaker.call(fail)

    assert breaker.state is BreakerState.OPEN
    clock.advance(29.9)
    assert breaker.state is BreakerState.OPEN, "the window restarts from the probe"


async def test_a_half_open_breaker_admits_only_one_concurrent_probe() -> None:
    """The trickiest branch in the state machine: two coroutines call()
    while the breaker is HALF_OPEN. Without the `_probe_in_flight` guard,
    both would reach the dependency at once — the thundering herd the
    breaker exists to prevent, delivered exactly when the dependency is
    most fragile.

    An `asyncio.Event` proves the two calls are genuinely in flight
    together: the second `call()` is only attempted once the first has
    provably entered its operation, rather than hoping the scheduler
    interleaves them the right way by chance.
    """
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail)
    clock.advance(30.0)
    assert breaker.state is BreakerState.HALF_OPEN

    probe_entered = asyncio.Event()
    release_probe = asyncio.Event()
    entered_count = 0

    async def blocking_probe() -> str:
        nonlocal entered_count
        entered_count += 1
        probe_entered.set()
        await release_probe.wait()
        return "ok"

    async def unreachable() -> str:
        raise AssertionError("a second probe must never reach the operation")

    async def second_call_while_probe_is_in_flight() -> None:
        await probe_entered.wait()
        with pytest.raises(CircuitOpenError):
            await breaker.call(unreachable)
        release_probe.set()

    first_result, _ = await asyncio.gather(
        breaker.call(blocking_probe), second_call_while_probe_is_in_flight()
    )

    assert first_result == "ok"
    assert entered_count == 1, "only the first caller may reach the dependency"
    assert breaker.state is BreakerState.CLOSED


async def test_a_threshold_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreaker(failure_threshold=0, reset_after_seconds=1.0)


async def test_a_non_positive_reset_window_is_refused() -> None:
    """Mirrors the threshold-validation test above. A regression that
    weakened `<= 0` to `< 0` would let `reset_after_seconds=0` through,
    which flips the breaker to HALF_OPEN on the very next call."""
    with pytest.raises(ValueError, match="reset_after_seconds"):
        CircuitBreaker(failure_threshold=1, reset_after_seconds=0.0)
