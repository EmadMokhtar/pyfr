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

import httpx
import structlog
{%- if cookiecutter.cache == "redis" %}
from redis.asyncio import Redis
{%- endif %}
{%- if cookiecutter.database == "postgres" %}
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine
{%- endif %}

from {{ cookiecutter.package_name }}.domain.payments import PaymentGateway
from {{ cookiecutter.package_name }}.domain.receipts import ReceiptStore
from {{ cookiecutter.package_name }}.domain.repositories import OrderRepository
{%- if cookiecutter.cache == "redis" %}
from {{ cookiecutter.package_name }}.infrastructure.cache.client import build_redis_client
from {{ cookiecutter.package_name }}.infrastructure.cache.order_repository import (
    CachedOrderRepository,
)
{%- endif %}
{%- if cookiecutter.database == "postgres" %}
from {{ cookiecutter.package_name }}.infrastructure.db.engine import (
    build_engine,
    build_sessionmaker,
)
from {{ cookiecutter.package_name }}.infrastructure.db.order_repository import (
    PostgresOrderRepository,
)
{%- endif %}
from {{ cookiecutter.package_name }}.infrastructure.http.breaker import CircuitBreaker
from {{ cookiecutter.package_name }}.infrastructure.http.client import build_http_client
from {{ cookiecutter.package_name }}.infrastructure.http.payment_gateway import (
    HttpPaymentGateway,
)
from {{ cookiecutter.package_name }}.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from {{ cookiecutter.package_name }}.infrastructure.memory.payment_gateway import (
    InMemoryPaymentGateway,
)
from {{ cookiecutter.package_name }}.infrastructure.memory.receipt_store import (
    InMemoryReceiptStore,
)
{%- if cookiecutter.object_storage == "s3" %}
from {{ cookiecutter.package_name }}.infrastructure.storage.client import (
    build_client_config,
    build_s3_session,
)
from {{ cookiecutter.package_name }}.infrastructure.storage.receipt_store import (
    S3ReceiptStore,
)
{%- endif %}
from {{ cookiecutter.package_name }}.settings import Settings

ReadinessCheck = Callable[[], Awaitable[None]]

READINESS_TIMEOUT_SECONDS = 2.0

_logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class ReadinessReport:
    """What /readyz learned, split by whether it is allowed to matter.

    `gating` decides the HTTP status. `informational` is reported and
    decides nothing — see register_informational for why the split exists.
    """

    gating: dict[str, str]
    informational: dict[str, str]

    @property
    def healthy(self) -> bool:
        return all(result == "ok" for result in self.gating.values())


class ReadinessRegistry:
    """Dependencies register themselves here; /readyz runs them all.

    Lives beside the container rather than in the api layer so the import
    chain stays acyclic: api.health -> api.deps -> container.

    Two tiers, and which one a dependency belongs in is a judgement about
    BLAST RADIUS, not about importance:

      gating        — losing it means this instance cannot do useful work.
                      A failure returns 503 and the orchestrator stops
                      sending traffic here. The database is the only one.
      informational — losing it degrades the service without breaking it.
                      Reported so an operator can see it, and never allowed
                      to affect the status code.

    The cache is informational because it fails open: when Redis is gone,
    PostgreSQL answers and every response is still correct. Gating on it
    would be actively harmful, because Redis is SHARED — every pod would
    fail the check in the same second and the whole service would leave
    the load balancer over a degradation it was built to survive.

    Object storage is informational for a different reason with the same
    answer: losing it breaks one endpoint, so taking 100% of traffic off
    the pod to protect that slice costs far more than it saves.

    This is the same reasoning build_container already records for not
    registering the payment provider at all. The difference is that these
    two are REPORTED, which spec 12.1 asks for and which costs nothing.
    """

    def __init__(self) -> None:
        self._gating: dict[str, ReadinessCheck] = {}
        self._informational: dict[str, ReadinessCheck] = {}

    def register(self, name: str, check: ReadinessCheck) -> None:
        """Register a check that MAY return 503. See the class docstring."""
        self._gating[name] = check

    def register_informational(self, name: str, check: ReadinessCheck) -> None:
        """Register a check that is reported and never returns 503."""
        self._informational[name] = check

    async def run(
        self,
        timeout: float = READINESS_TIMEOUT_SECONDS,  # noqa: ASYNC109 - see docstring
    ) -> ReadinessReport:
        """Run every check in BOTH tiers concurrently, each bounded by `timeout`.

        Concurrency is the point, and it spans the tiers rather than
        running one after the other. Run sequentially, the endpoint's worst
        case would be N x timeout — which an orchestrator's own probe
        timeout kills long before it arrives, marking the pod unready for
        entirely the wrong reason. One gather over both tiers keeps the
        worst case at one timeout no matter how many dependencies register
        in either.

        ASYNC109 is suppressed deliberately: the rule prefers callers to own
        deadlines, but this registry owns the readiness policy, and its
        callers are HTTP handlers with no better deadline to offer.
        """

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
                # exception message from a database driver, a Redis client or
                # an S3 client routinely carries hostnames, connection
                # strings, or credentials. The response gets only the bounded
                # exception type name; the full exception — with its message
                # and traceback — goes to the log instead, where an operator
                # can still see it.
                _logger.exception("readiness_check.failed", check=name)
                return name, f"error: {type(exc).__name__}"
            return name, "ok"

        gating_names = list(self._gating)
        results = await asyncio.gather(
            *(run_one(name, check) for name, check in self._gating.items()),
            *(run_one(name, check) for name, check in self._informational.items()),
        )
        # gather preserves argument order, so the first len(gating_names)
        # results are the gating ones. Splitting by position rather than
        # re-looking-up the name keeps this correct even if a name were ever
        # registered in both tiers.
        boundary = len(gating_names)
        return ReadinessReport(
            gating=dict(results[:boundary]),
            informational=dict(results[boundary:]),
        )


@dataclass
class Container:
    settings: Settings
    orders: OrderRepository
    payments: PaymentGateway
{%- if cookiecutter.database == "postgres" %}
    # None when no database is configured. Held only so close_container can
    # dispose the pool at shutdown; nothing else reaches for it.
    engine: AsyncEngine | None = None
{%- endif %}
    # None when no payment provider is configured (the in-memory gateway's
    # case). Held for the same reason `engine` is: only close_container
    # reaches for it, to close the pooled connections at shutdown.
    http_client: httpx.AsyncClient | None = None
{%- if cookiecutter.cache == "redis" %}
    # None when no cache is configured. Held only so close_container can
    # release the pool at shutdown; nothing else reaches for it.
    redis: Redis | None = None
{%- endif %}
    # Always present, never None — unlike engine and http_client, there is
    # always SOME store, because the in-memory one needs no configuration.
    # Defaults to it here; build_container below swaps in the S3 adapter
    # when settings.storage is configured.
    receipts: ReceiptStore = field(default_factory=InMemoryReceiptStore)
    readiness: ReadinessRegistry = field(default_factory=ReadinessRegistry)
    started: bool = False


def build_container(settings: Settings) -> Container:
    if settings.payment is None:
        # No payment provider configured: the in-memory gateway, which
        # authorises everything — the same arrangement `database` below has
        # with the in-memory order repository.
        payments: PaymentGateway = InMemoryPaymentGateway()
        http_client = None
    else:
        http_client = build_http_client(
            settings.payment.http,
            base_url=str(settings.payment.base_url),
            headers=(
                {
                    "Authorization": (
                        f"Bearer {settings.payment.api_key.get_secret_value()}"
                    )
                }
                if settings.payment.api_key is not None
                else None
            ),
        )
        payments = HttpPaymentGateway(
            http_client,
            breaker=CircuitBreaker(
                failure_threshold=settings.payment.breaker_failure_threshold,
                reset_after_seconds=settings.payment.breaker_reset_after_seconds,
            ),
            attempts=settings.payment.retry_attempts,
            wait_initial_seconds=settings.payment.retry_initial_wait_seconds,
            wait_max_seconds=settings.payment.retry_max_wait_seconds,
        )
{%- if cookiecutter.database == "postgres" %}

    engine: AsyncEngine | None = None
    orders: OrderRepository
    if settings.database is None:
        # No database configured: the in-memory adapter, and no readiness
        # check, because there is no dependency to report on.
        orders = InMemoryOrderRepository()
    else:
        engine = build_engine(settings.database)
        orders = PostgresOrderRepository(build_sessionmaker(engine))
{%- else %}

    orders: OrderRepository = InMemoryOrderRepository()
{%- endif %}
{%- if cookiecutter.cache == "redis" %}

    # The cache wraps whatever was selected above and satisfies the same
    # port, so this is the ONLY place in the application that knows a cache
    # exists. Removing the cache is deleting this block.
    redis: Redis | None = None
    if settings.cache is not None:
        redis = build_redis_client(settings.cache)
        orders = CachedOrderRepository(orders, redis, settings.cache.ttl_seconds)
{%- endif %}

    receipts: ReceiptStore = InMemoryReceiptStore()
{%- if cookiecutter.object_storage == "s3" %}
    s3_store: S3ReceiptStore | None = None
    if settings.storage is not None:
        storage_settings = settings.storage
        s3_store = S3ReceiptStore(
            build_s3_session(storage_settings),
            build_client_config(storage_settings),
            storage_settings,
        )
        receipts = s3_store
{%- endif %}

    container = Container(
        settings=settings,
        orders=orders,
        payments=payments,
{%- if cookiecutter.database == "postgres" %}
        engine=engine,
{%- endif %}
        http_client=http_client,
{%- if cookiecutter.cache == "redis" %}
        redis=redis,
{%- endif %}
        receipts=receipts,
    )
{%- if cookiecutter.database == "postgres" %}

    if engine is not None:

        async def database_is_reachable() -> None:
            # Deliberately trivial. /readyz answers "can this process reach
            # its dependencies", not "is the schema correct" — a readiness
            # probe that runs a real query turns a slow database into an
            # unready pod and takes the service out of rotation for a
            # problem it could have served through. ReadinessRegistry.run
            # bounds this with its own timeout and reports only the
            # exception TYPE, so a connection string in a driver's error
            # message never reaches the response body.
            async with engine.connect() as connection:
                await connection.execute(text("SELECT 1"))

        container.readiness.register("database", database_is_reachable)
{%- endif %}
{%- if cookiecutter.cache == "redis" %}

    if redis is not None:
        cache_client = redis

        async def cache_is_reachable() -> None:
            await cache_client.ping()

        # INFORMATIONAL, not gating, and the difference is deliberate.
        # Redis is shared across every pod, and this cache fails open — with
        # Redis gone, PostgreSQL answers and every response is still
        # correct. A gating check would make every pod report itself unready
        # in the same second, taking the whole service out of the load
        # balancer over a degradation it was built to survive. Reporting it
        # gives an operator the signal without the outage.
        container.readiness.register_informational("cache", cache_is_reachable)
{%- endif %}
{%- if cookiecutter.object_storage == "s3" %}

    # Both halves of the condition are checked on purpose, even though
    # `s3_store` is non-None only when `settings.storage` is. That coupling
    # is real but IMPLICIT — it lives twenty lines up, in a different
    # block — and reading `storage_settings` down here would depend on it
    # silently: correct today only because Python scopes locals to the whole
    # function, and an UnboundLocalError the moment someone moves the
    # construction above into a helper. Naming `settings.storage` again
    # makes this block self-contained, and narrows the type for mypy
    # without an assertion.
    if s3_store is not None and settings.storage is not None:
        store = s3_store
        bucket = settings.storage.bucket

        async def storage_is_reachable() -> None:
            # head_bucket, not a get or a list: it is the cheapest call that
            # proves the endpoint answers, the credentials are accepted AND
            # the bucket exists — which is the whole question. Listing keys
            # would also work and gets slower as the bucket fills.
            #
            # _client() is private, and reaching into it here is deliberate:
            # the alternative is a public ping() on the port, which would
            # put a health-check concern into the domain's ReceiptStore
            # Protocol where it does not belong. Keeping the reach-in here
            # keeps that leak inside the composition root, which already
            # knows exactly which adapter it built — `store` above is typed
            # as the concrete S3ReceiptStore, not the ReceiptStore Protocol,
            # so no suppression is needed to call it.
            client_cm = store._client()
            async with client_cm as s3:
                await s3.head_bucket(Bucket=bucket)

        container.readiness.register_informational("storage", storage_is_reachable)
{%- endif %}

    # Deliberately no readiness check registered for the payment provider.
    # /readyz removing this pod from load balancing because someone else's
    # API is slow turns their outage into ours, and the circuit breaker
    # already handles that case properly — see HttpPaymentGateway.
    return container


async def close_container(container: Container) -> None:
    """Release resources. Runs after in-flight requests finish.

    Nested `try`/`finally` rather than sequential `if`s: without it, an
    exception from one close would skip every close after it, leaking
    pooled connections on exactly the shutdown that also had trouble —
    the moment a leak is least affordable. Each resource's cleanup is
    independent of the others' success.
    """
{%- if cookiecutter.database == "postgres" and cookiecutter.cache == "redis" %}
    try:
        if container.engine is not None:
            # Closes every pooled connection. Without this, shutdown leaves
            # connections open until the server times them out, and a rolling
            # deployment can exhaust the database's connection limit with the
            # sockets of pods that have already stopped serving.
            await container.engine.dispose()
    finally:
        try:
            if container.http_client is not None:
                await container.http_client.aclose()
        finally:
            if container.redis is not None:
                # aclose(), not close(): the sync name is deprecated in
                # redis-py 5+ and warns, which filterwarnings=["error"]
                # turns into a failure in any test that shuts a container
                # down. Redis.from_pool means this owns the pool and
                # disconnects it.
                await container.redis.aclose()
{%- elif cookiecutter.database == "postgres" %}
    try:
        if container.engine is not None:
            # Closes every pooled connection. Without this, shutdown leaves
            # connections open until the server times them out, and a rolling
            # deployment can exhaust the database's connection limit with the
            # sockets of pods that have already stopped serving.
            await container.engine.dispose()
    finally:
        if container.http_client is not None:
            await container.http_client.aclose()
{%- elif cookiecutter.cache == "redis" %}
    try:
        if container.http_client is not None:
            await container.http_client.aclose()
    finally:
        if container.redis is not None:
            # aclose(), not close(): the sync name is deprecated in
            # redis-py 5+ and warns, which filterwarnings=["error"]
            # turns into a failure in any test that shuts a container
            # down. Redis.from_pool means this owns the pool and
            # disconnects it.
            await container.redis.aclose()
{%- else %}
    if container.http_client is not None:
        await container.http_client.aclose()
{%- endif %}
