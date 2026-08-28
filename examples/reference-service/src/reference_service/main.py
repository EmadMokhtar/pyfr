"""Application factory and life cycle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from reference_service import __version__
from reference_service.api import health
from reference_service.api.errors import register_error_handlers
from reference_service.api.middleware import (
    AccessLogMiddleware,
    CorrelationIdMiddleware,
)
from reference_service.api.v1.router import router as v1_router
from reference_service.container import build_container, close_container
from reference_service.observability.logging import configure_logging
from reference_service.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else load_settings()

    configure_logging(
        environment=resolved.environment,
        level=resolved.log.level,
        levels=resolved.log.levels,
        service_name=resolved.service_name,
        service_version=__version__,
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build_container(resolved)
        app.state.container = container
        container.started = True
        try:
            yield
        finally:
            # Runs on SIGTERM, after in-flight requests finish. uvicorn's
            # --timeout-graceful-shutdown bounds how long that may take.
            container.started = False
            await close_container(container)

    app = FastAPI(
        title=resolved.service_name,
        version=__version__,
        lifespan=lifespan,
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1_router, prefix="/api/v1")
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    return app
