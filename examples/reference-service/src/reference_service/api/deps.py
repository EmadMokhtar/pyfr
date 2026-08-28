"""FastAPI dependencies.

These read from `app.state`, which the lifespan populated. Tests replace them
with `app.dependency_overrides`.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request

from reference_service.container import Container


def get_container(request: Request) -> Container:
    container: Container = request.app.state.container
    return container


ContainerDep = Annotated[Container, Depends(get_container)]
