"""Health endpoints.

Three endpoints, three different questions:

  /healthz   liveness  — is this process alive? It must NEVER check a
                         dependency. If it did, a brief database problem
                         would make the orchestrator restart every pod at
                         once, turning a small outage into a large one.
  /readyz    readiness — can this instance serve traffic right now? Gating
                         dependencies are checked with short timeouts and a
                         failure returns 503. Informational ones are
                         reported under `dependencies` and never change the
                         status code — see ReadinessRegistry.
  /startupz  startup   — has startup finished? Covers slow first starts.
"""

from __future__ import annotations

from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from reference_service import __version__
from reference_service.api.deps import ContainerDep


class LivenessResponse(BaseModel):
    status: str
    version: str


class ReadinessResponse(BaseModel):
    status: str
    # Only these decide the status code.
    checks: dict[str, str]
    # Reported, never decisive. Empty when nothing informational is
    # registered, which is the case for a service with no cache and no
    # object store configured.
    dependencies: dict[str, str] = Field(default_factory=dict)


router = APIRouter(tags=["health"])


@router.get("/healthz", response_model=LivenessResponse)
async def liveness() -> LivenessResponse:
    """Liveness takes no dependency, by design. See the module docstring."""
    return LivenessResponse(status="ok", version=__version__)


@router.get("/readyz", response_model=ReadinessResponse)
async def readiness(container: ContainerDep, response: Response) -> ReadinessResponse:
    report = await container.readiness.run()
    if not report.healthy:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return ReadinessResponse(
        status="ok" if report.healthy else "unavailable",
        checks=report.gating,
        dependencies=report.informational,
    )


@router.get("/startupz", response_model=LivenessResponse)
async def startup(container: ContainerDep, response: Response) -> LivenessResponse:
    if not container.started:
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
    return LivenessResponse(
        status="ok" if container.started else "starting", version=__version__
    )
