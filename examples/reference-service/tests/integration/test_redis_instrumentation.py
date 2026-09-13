"""A Redis command must appear as a span carrying the statement.

Same reasoning as test_db_instrumentation.py's module docstring: without
this, a slow endpoint tells you only that it was slow. With it, the trace
shows whether the time went to Redis and to which command — the signal
that a fail-open cache read costing 40ms would otherwise hide from every
other metric, because the request still succeeds.
"""

from __future__ import annotations

import pytest
from opentelemetry.instrumentation.redis import RedisInstrumentor
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from reference_service.infrastructure.cache.client import build_redis_client
from reference_service.observability.otel import (
    build_providers,
    instrument_redis,
)
from reference_service.settings import CacheSettings, OtelSettings, Settings

pytestmark = [pytest.mark.integration, pytest.mark.asyncio(loop_scope="session")]


async def test_a_command_produces_a_redis_span(
    cache_settings: CacheSettings,
) -> None:
    """Builds its OWN client rather than borrowing the `redis_client` fixture.

    RedisInstrumentor attaches to the redis-py library itself and is a
    process-wide singleton, same as SQLAlchemyInstrumentor in
    test_db_instrumentation.py. Instrumenting inside this test and
    uninstrumenting in `finally` keeps the blast radius inside this test
    rather than leaking spans into whichever integration test happens to
    touch Redis next.
    """
    span_exporter = InMemorySpanExporter()
    settings = Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="production",
        otel=OtelSettings(enabled=True, endpoint="http://localhost:4317"),
    )
    runtime = build_providers(settings, "1.2.3", span_exporter=span_exporter)
    client = build_redis_client(cache_settings)
    instrument_redis(runtime)

    try:
        await client.set("otel-probe", "1")
        await client.get("otel-probe")

        systems = {
            span.attributes.get("db.system")
            for span in span_exporter.get_finished_spans()
            if span.attributes
        }
        assert "redis" in systems
    finally:
        # Order matters: uninstrument before closing the client, same as
        # test_db_instrumentation.py's engine.dispose() ordering.
        RedisInstrumentor().uninstrument()
        runtime.shutdown()
        await client.aclose()
