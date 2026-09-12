"""A repository call must appear as a span carrying the statement.

Without this, a slow endpoint tells you only that it was slow. With it,
the trace shows whether the time went to the database and to which
statement.
"""

from __future__ import annotations

import pytest
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from sqlalchemy import text

from {{ cookiecutter.package_name }}.infrastructure.db.engine import build_engine
from {{ cookiecutter.package_name }}.observability.otel import (
    build_providers,
    instrument_database,
)
from {{ cookiecutter.package_name }}.settings import DatabaseSettings, OtelSettings, Settings

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def test_a_query_produces_a_database_span(database_url: str) -> None:
    """Builds its OWN engine rather than borrowing the session fixture's.

    SQLAlchemyInstrumentor attaches event listeners to the engine it is
    given and is a process-wide singleton. Instrumenting the shared
    session-scoped engine would leak spans into every other integration
    test that happens to run afterwards. A dedicated engine, disposed
    here, keeps the blast radius inside this test.
    """
    span_exporter = InMemorySpanExporter()
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="production",
        otel=OtelSettings(enabled=True, endpoint="http://localhost:4317"),
    )
    runtime = build_providers(settings, "1.2.3", span_exporter=span_exporter)
    engine = build_engine(DatabaseSettings(dsn=database_url))  # type: ignore[arg-type]
    instrument_database(engine, runtime)

    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        systems = {
            span.attributes.get("db.system")
            for span in span_exporter.get_finished_spans()
            if span.attributes
        }
        assert "postgresql" in systems
    finally:
        # Order matters: uninstrument before disposing, so the listeners are
        # detached from an engine that still exists.
        SQLAlchemyInstrumentor().uninstrument()
        runtime.shutdown()
        await engine.dispose()
