"""Health endpoints.

Three endpoints, three different questions:

  /healthz   liveness  — is this process alive? It must NEVER check a
                         dependency. If it did, a brief database problem
                         would make the orchestrator restart every pod at
                         once, turning a small outage into a large one.
  /readyz    readiness — can this instance serve traffic right now? This is
                         where dependencies are checked, with short timeouts.
  /startupz  startup   — has startup finished? Covers slow first starts.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel

from reference_service import __version__
from reference_service.api.deps import ContainerDep


class LivenessResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    checks: dict[str, str]


router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Liveness takes no dependency, by design. See the module docstring."""
    return LivenessResponse(status="ok", version=__version__)


@router.get("/readyz", response_model=ReadinessResponse)
async def readiness(container: ContainerDep, response: Response) -> ReadinessResponse:
    checks = await container.readiness.run()
    healthy = all(result == "ok" for result in checks.values())
    if not healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(status="ok" if healthy else "unavailable", checks=checks)


@router.get("/startupz", response_model=LivenessResponse)
async def startup(container: ContainerDep, response: Response) -> LivenessResponse:
    if not container.started:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return LivenessResponse(
        status="ok" if container.started else "starting", version=__version__
    )
