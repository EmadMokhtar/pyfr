"""Application factory and life cycle."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from {{ cookiecutter.package_name }} import __version__
from {{ cookiecutter.package_name }}.api import health
from {{ cookiecutter.package_name }}.api.errors import (
    DEFAULT_PROBLEM_RESPONSES,
    register_error_handlers,
)
from {{ cookiecutter.package_name }}.api.middleware import (
    AccessLogMiddleware,
    CorrelationIdMiddleware,
)
from {{ cookiecutter.package_name }}.api.v1.router import router as v1_router
from {{ cookiecutter.package_name }}.container import build_container, close_container
from {{ cookiecutter.package_name }}.observability.logging import configure_logging
from {{ cookiecutter.package_name }}.observability.metrics import (
    RuntimeMetrics,
    register_runtime_metrics,
)
from {{ cookiecutter.package_name }}.observability.otel import (
    OtelRuntime,
    configure_otel,
    instrument_database,
    instrument_fastapi,
    instrument_http_client,
    instrument_redis,
)
from {{ cookiecutter.package_name }}.settings import Settings, load_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    resolved = settings if settings is not None else load_settings()

    # Before configure_logging, not after. configure_logging takes an
    # optional logger_provider for OTLP log export, and that provider is
    # built here — so this has to run first or logging would have to be
    # configured twice. Nothing in configure_otel logs anything, so nothing
    # is lost by the ordering: it is pure construction, and a failure
    # inside it surfaces as a traceback on stderr exactly as a settings
    # failure already does.
    #
    # Returns None when APP_OTEL__ENABLED is false, which is the default
    # and the entire M0/M1 path.
    otel_runtime: OtelRuntime | None = configure_otel(resolved, __version__)

    configure_logging(
        environment=resolved.environment,
        level=resolved.log.level,
        levels=resolved.log.levels,
        redact_fields=resolved.log.redact_fields,
        service_name=resolved.service_name,
        service_version=__version__,
        logger_provider=(
            otel_runtime.logger_provider if otel_runtime is not None else None
        ),
    )

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        container = build_container(resolved)
        app.state.container = container
        # Bound before the try below, because the finally block reads it:
        # assigned inside the try, an exception raised earlier would make
        # the finally hit an unbound name and mask the real startup error.
        runtime_metrics: RuntimeMetrics | None = None
        # Everything from here down is inside the try, including the
        # instrumentation block below and `container.started = True` —
        # not only the `yield`. `build_container` above has, by this
        # point, already opened `container.engine` and/or
        # `container.http_client` when either is configured, so if
        # `instrument_database`, `instrument_http_client`, `instrument_redis`
        # or `register_runtime_metrics` raises, those resources are already
        # open and need the same `close_container` cleanup a normal
        # shutdown gets. Before this comment, the block below sat OUTSIDE
        # this try, so a failure inside it skipped `close_container`
        # entirely and leaked whichever of the two was already open —
        # `try`/`finally` runs its `finally` on an exception raised
        # anywhere in the `try`, including before the first `yield`, so
        # moving the block in is sufficient; nothing else has to change.
        try:
            if otel_runtime is not None:
                if container.engine is not None:
                    # Here rather than in create_app because the engine does
                    # not exist until the container is built, and here rather
                    # than in container.py because the composition root has no
                    # business importing an SDK.
                    instrument_database(container.engine, otel_runtime)
                if container.http_client is not None:
                    # Only when a real payment provider is configured. The
                    # in-memory gateway makes no HTTP request, so there is no
                    # client and nothing to instrument.
                    instrument_http_client(container.http_client, otel_runtime)
                # Unconditional, unlike the two calls above: RedisInstrumentor
                # is a GLOBAL instrumentor (see its docstring), so it takes
                # only the runtime and not a specific client. Instrumenting a
                # library nothing uses costs nothing; gating this on
                # `container.redis is not None` would buy nothing either, so
                # the condition would only be one more place to forget.
                instrument_redis(otel_runtime)
                # Here, not in create_app: the probe task needs a running
                # event loop, and create_app runs before there is one.
                runtime_metrics = register_runtime_metrics(
                    otel_runtime,
                    service_version=__version__,
                    engine=container.engine,
                )
            container.started = True
            yield
        finally:
            # Runs on SIGTERM, after in-flight requests finish, AND on a
            # startup failure raised anywhere above — see the comment at
            # the top of this try for why the latter case matters.
            # uvicorn's --timeout-graceful-shutdown bounds how long a
            # normal shutdown may take.
            container.started = False
            await close_container(container)
            if runtime_metrics is not None:
                # Before the providers shut down, so the final collection
                # still has instruments to read.
                await runtime_metrics.stop()
            if otel_runtime is not None:
                # Last, and after close_container: shutting the providers
                # down flushes whatever is still batched, and the lines and
                # spans produced BY closing the database pool are exactly
                # the ones you want when a shutdown goes wrong.
                otel_runtime.shutdown()

    app = FastAPI(
        title=resolved.service_name,
        version=__version__,
        lifespan=lifespan,
        # Every route can hit request validation (422) or an unexpected
        # failure (500); see api/errors.py's DEFAULT_PROBLEM_RESPONSES for
        # why this, and not the model=/handler registration below, is what
        # makes the OpenAPI document describe those responses correctly.
        responses=DEFAULT_PROBLEM_RESPONSES,
    )
    register_error_handlers(app)
    app.include_router(health.router)
    app.include_router(v1_router, prefix="/api/v1")
    app.add_middleware(AccessLogMiddleware)
    app.add_middleware(CorrelationIdMiddleware)
    app.state.otel = otel_runtime
    if otel_runtime is not None:
        # Last, so the OpenTelemetry middleware ends up outermost — see
        # instrument_fastapi's docstring for why the ordering is
        # load-bearing rather than incidental.
        instrument_fastapi(app, otel_runtime)
    return app
