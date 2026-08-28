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

from reference_service.domain.repositories import OrderRepository
from reference_service.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from reference_service.settings import Settings

ReadinessCheck = Callable[[], Awaitable[None]]

READINESS_TIMEOUT_SECONDS = 2.0


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
        timeout: float = READINESS_TIMEOUT_SECONDS,  # noqa: ASYNC109 -- public knob
    ) -> dict[str, str]:
        results: dict[str, str] = {}
        for name, check in self._checks.items():
            try:
                await asyncio.wait_for(check(), timeout=timeout)
            except TimeoutError:
                results[name] = f"error: timeout after {timeout}s"
            except Exception as exc:
                # A failing check reports; it never takes the endpoint down.
                results[name] = f"error: {exc}"
            else:
                results[name] = "ok"
        return results


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
