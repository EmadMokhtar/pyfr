"""The composition root.

One plain module that builds the adapters. FastAPI's `lifespan` constructs it
at startup and closes it at shutdown. There is deliberately no
dependency-injection library: FastAPI's own `Depends` plus this module does
the job, and a DI container is a large concept for every new team member to
learn for no gain at this size.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import structlog

from reference_service.domain.repositories import OrderRepository
from reference_service.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from reference_service.settings import Settings

ReadinessCheck = Callable[[], Awaitable[None]]

READINESS_TIMEOUT_SECONDS = 2.0

_logger = structlog.get_logger(__name__)


class ReadinessRegistry:
    """Dependencies register themselves here; /readyz runs them all.

    Lives beside the container rather than in the api layer so the import
    chain stays acyclic: api.health -> api.deps -> container.
    """

    def __init__(self) -> None:
        self._checks: dict[str, ReadinessCheck] = {}

    def register(self, name: str, check: ReadinessCheck) -> None:
        self._checks[name] = check

    async def run(
        self,
        timeout: float = READINESS_TIMEOUT_SECONDS,  # noqa: ASYNC109 - see docstring
    ) -> dict[str, str]:
        """Run every check CONCURRENTLY, each bounded by `timeout`.

        Concurrency is the point. Run sequentially, the endpoint's worst
        case would be N x timeout — three dependency checks at two seconds
        each is a six-second readiness response, which an orchestrator's own
        probe timeout kills long before it arrives, marking the pod unready
        for entirely the wrong reason. Concurrent, the worst case is one
        timeout no matter how many dependencies register.

        ASYNC109 is suppressed deliberately: the rule prefers callers to own
        deadlines, but this registry owns the readiness policy, and its
        callers are HTTP handlers with no better deadline to offer.
        """
        if not self._checks:
            return {}

        async def run_one(name: str, check: ReadinessCheck) -> tuple[str, str]:
            try:
                await asyncio.wait_for(check(), timeout=timeout)
            except TimeoutError:
                # No untrusted content in this branch's message: keep it as is.
                return name, f"error: timeout after {timeout}s"
            except Exception as exc:
                # A failing check reports; it never takes the endpoint down.
                #
                # The exception's own message is deliberately NOT put into the
                # response: /readyz is reachable inside a cluster, and an
                # exception message from a database driver or an HTTP client
                # routinely carries hostnames, connection strings, or
                # credentials. The response gets only the bounded exception
                # type name; the full exception — with its message and
                # traceback — goes to the log instead, where an operator can
                # still see it.
                _logger.exception("readiness_check.failed", check=name)
                return name, f"error: {type(exc).__name__}"
            return name, "ok"

        results = await asyncio.gather(
            *(run_one(name, check) for name, check in self._checks.items())
        )
        return dict(results)


@dataclass
class Container:
    settings: Settings
    orders: OrderRepository
    readiness: ReadinessRegistry = field(default_factory=ReadinessRegistry)
    started: bool = False


def build_container(settings: Settings) -> Container:
    return Container(settings=settings, orders=InMemoryOrderRepository())


async def close_container(container: Container) -> None:
    """Release resources. Nothing to close in M0; M1 closes the database pool."""
    return None
