"""A circuit breaker for one outbound dependency.

Written rather than depended on. The two asyncio implementations on PyPI
were last released in 2021 and 2022; the one maintained package,
pybreaker, offers Tornado coroutines rather than `await`. Eighty lines
that this service's own tests cover is the smaller long-term cost.

What it is: after N consecutive failures the breaker OPENS and refuses
calls outright for a cool-down window, instead of letting every request
queue behind a dependency that is already down. Once the window passes it
goes HALF-OPEN and admits a single probe: if that succeeds the breaker
closes, if it fails the window starts again. Without it, one slow
dependency consumes every connection and worker this service has, and a
partial outage becomes a total one.

Deliberately not thread-safe, and it does not need to be: this service
runs one event loop per process, and every mutation below happens between
`await` points, so no other coroutine can observe a half-updated state.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

T = TypeVar("T")


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """The breaker refused the call without attempting it.

    Distinct from any error the dependency itself raises, because it means
    something different to the caller: the dependency was not asked. The
    adapter maps it onto the same "unavailable" outcome as a timeout,
    which is honest — from the caller's side both mean "no answer" — but
    keeping the type separate is what lets a log line say which happened.
    """


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        reset_after_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError(f"failure_threshold must be >= 1, got {failure_threshold}")
        if reset_after_seconds <= 0:
            raise ValueError(
                f"reset_after_seconds must be > 0, got {reset_after_seconds}"
            )
        self._failure_threshold = failure_threshold
        self._reset_after_seconds = reset_after_seconds
        # `time.monotonic` by default, never `time.time`: a wall clock can
        # step backwards when the host syncs, which would leave an open
        # breaker refusing calls until the clock caught up again.
        self._clock = clock
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False

    @property
    def state(self) -> BreakerState:
        """Derived, never stored.

        Storing HALF_OPEN would mean something has to notice the window
        expiring and write it — a timer, or a check on every call. Deriving
        it from the clock means the transition simply happens.
        """
        if self._opened_at is None:
            return BreakerState.CLOSED
        if self._clock() - self._opened_at >= self._reset_after_seconds:
            return BreakerState.HALF_OPEN
        return BreakerState.OPEN

    async def call(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Run `operation`, or refuse it if the circuit is open.

        Every exception counts as a failure, so the CALLER decides what
        counts as one by choosing what to raise. This matters for
        payments: a declined card is a successful call with a negative
        answer, and the adapter therefore returns the response from here
        and interprets it outside — a decline must never trip the breaker.
        """
        state = self.state
        if state is BreakerState.OPEN:
            opened_at = self._opened_at or 0.0
            remaining = self._reset_after_seconds - (self._clock() - opened_at)
            raise CircuitOpenError(f"circuit open; retrying in {remaining:.1f}s")

        is_probe = state is BreakerState.HALF_OPEN
        if is_probe:
            if self._probe_in_flight:
                # One probe at a time. Without this, every request that
                # arrives during the half-open moment is sent at a
                # dependency that has not yet proved it recovered — the
                # thundering herd the breaker exists to prevent, delivered
                # precisely when the dependency is most fragile.
                raise CircuitOpenError("circuit half-open; a probe is already running")
            self._probe_in_flight = True

        try:
            result = await operation()
        except Exception:
            self._record_failure(is_probe=is_probe)
            raise
        else:
            self._record_success()
            return result
        finally:
            if is_probe:
                self._probe_in_flight = False

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def _record_failure(self, *, is_probe: bool) -> None:
        self._consecutive_failures += 1
        # A failed probe reopens on its own: the dependency has already
        # shown it is unwell, and making it fail another full threshold to
        # say so again just sends more doomed requests into it.
        if is_probe or self._consecutive_failures >= self._failure_threshold:
            self._opened_at = self._clock()
