# PyFr M4 — Cache and Object Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Redis cache and an S3-compatible object store to the reference service, each behind a port with a real caller, each optional, and each proven by integration tests against a real container.

**Architecture:** The cache is a *decorator* over the existing `OrderRepository` port, not a new port — `CachedOrderRepository` wraps another repository and satisfies the same Protocol, so no service, router or domain module changes. Object storage gets one new domain port, `ReceiptStore`, served by an `aioboto3` adapter and consumed by a new `GetReceipt` service behind `GET /api/v1/orders/{order_id}/receipt`. Both dependencies are optional in exactly the way `database` and `payment` already are: absent settings select an in-memory adapter and the service still runs.

**Tech Stack:** `redis` (asyncio client), `aioboto3`, `opentelemetry-instrumentation-redis`, `opentelemetry-instrumentation-botocore`, `testcontainers[redis,minio]`, MinIO and Redis in compose.

**Spec:** [`docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md`](../specs/2026-08-28-pyfr-cookiecutter-template-design.md) — sections 7.2 (instrumentation), 7.4 (dashboards), 8.1 (testing tiers), 9.1 (the `cache` and `object_storage` prompts), 12.1 item 1 (health endpoints), and the M4 row of section 13.

---

## Global Constraints

Every task's requirements implicitly include these. The first twenty-four are inherited from M0, M1, M2 and M3 unchanged; the rest are new in M4.

- **Python `>=3.13`.** `.python-version` contains `3.13`.
- **uv for everything Python.** `uv sync`, `uv run`, `uv lock`. No `pip`, no `requirements.txt`, no `pipx`, no manually activated virtual environment.
- **Plain Python only.** M4 is still Phase A. No Jinja, no cookiecutter variables, no `{{ }}` templating in any Python, YAML or compose file. Templatisation is M7.
- **Package name is `reference_service`;** distribution name is `reference-service`. All work happens under `examples/reference-service/`.
- **The domain layer imports nothing but `pydantic`.** Not FastAPI, not the service layer, not infrastructure, not SQLAlchemy, not asyncpg, not `opentelemetry`, not `httpx`, not `stamina` — and, new in M4, not `redis` and not `aioboto3`.
- **The domain layer never knows an HTTP status code exists.**
- **mypy is strict on `domain/` and `services/`,** lenient elsewhere.
- **All logging goes through structlog.**
- **`/healthz` never checks a dependency.** Only `/readyz` does.
- **Line length 88.**
- **Conventional Commits** for every commit: `<type>[scope]: <description>`, imperative, lowercase, no trailing period.
- **Unit tests never need Docker.** `just test` runs `tests/unit` and `tests/api` only. Anything requiring a container lives in `tests/integration` and runs under `just test-integration`.
- **`filterwarnings = ["error"]` stays.** This bites in M4 — see Verified Fact 1.
- **Pinned images.** Every image is written in exactly one place and referenced from there. New in M4: `redis:8-alpine`, `minio/minio:RELEASE.2025-09-07T16-13-09Z`, `minio/mc:RELEASE.2025-08-13T08-35-41Z`.
- **Telemetry is off by default.** `APP_OTEL__ENABLED=false` is the default. With it false the process must import no exporter, open no socket, and start no background task. This extends to the two new instrumentations.
- **Standard output stays the source of truth for logs (D15).**
- **The stable HTTP semantic conventions, not the legacy ones.**
- **One source of truth for the SLO numbers.**
- **The committed contract is generated, never hand-edited.** `openapi.json` is an artifact of the code. The only way to change it is to change a route or a schema and run `just openapi`. A task that edits it by hand has done something wrong.
- **Every gate runs from `just`.** No `.github/workflows/` file is added in M4; M5 wires the same recipes into CI.
- **The contract tier never runs in the default selection.** `tests/contract/` is marked and deselected exactly as `tests/integration/` is.
- **No outbound request in a test ever reaches the network.** `record_mode=none` stays.
- **The breaker wraps the retry, not the reverse.**
- **Never retry a decline.**
- **A secret never reaches a log line, a traceback, or an HTTP response body.** `SecretStr` for every credential; `load_settings` elides input values.
- **The cache is fail-open, always.** Every Redis failure — connection, timeout, malformed payload — is logged and swallowed, and the wrapped repository answers. There is no configuration flag that makes a cache miss fatal. A cache that can take the service down is worse than no cache.
- **Object storage is never in the order-placing write path.** `PlaceOrder` does not touch `ReceiptStore`. Receipts are rendered on demand. An object-store outage must not be able to fail a payment.
- **`internal_note` never leaves the service.** It is excluded from the receipt document explicitly, not by accident of field ordering — see Verified Fact 7.
- **One adapter for every S3-compatible provider.** MinIO locally, Amazon S3 in production, distinguished only by `endpoint_url`. No provider-specific branching anywhere in the adapter.
- **Readiness reports the cache and the store; only the database gates.** See Task 2 and Verified Fact 8.

---

## What M4 deliberately does not include

| Left out | Owner |
|---|---|
| Presigned URLs for receipt download | Deliberately never, at least while compose is the local story — a presigned URL is signed for the `minio:9000` hostname that only resolves inside the compose network, so it is unusable from a browser on the host. Streaming through the app works identically in every environment |
| Idempotency keys backed by Redis | M9. The roadmap places them there, and pulling them forward would put the cache in the order write path, which Global Constraints forbids |
| Log redaction of storage credentials and payment payloads | M6, with the rest of the hardening work |
| `.github/workflows/*` — every gate runs from `just` | M5 (release), M7 (template CI) |
| Making `cache` and `object_storage` cookiecutter prompts | M7. In M4 they are two adapters behind two ports, which is exactly what M7 will make optional |
| A second cached aggregate, or a generic cache-aside helper | YAGNI. One cached repository demonstrates the pattern; a framework for caching things we do not cache is scaffolding |
| Cache stampede protection (single-flight / request coalescing) | Not in the roadmap's M4 row. The `GetOrder` read is a single indexed primary-key lookup, so a stampede costs one cheap query per concurrent reader, not an outage. Revisit if a genuinely expensive read is ever cached |
| Object versioning, lifecycle rules, or server-side encryption configuration | M6 at the earliest, and arguably never — these are bucket-provisioning concerns owned by whoever runs the bucket, not by application code |
| A `DELETE` route for a receipt | No caller wants one. Receipts are derived data: the source of truth is the order, and the object is a cache with a bucket in front of it |
| Multipart upload, or any client-supplied object | Nothing in the domain accepts uploads. Adding an upload path would mean content-type sniffing, size limits and virus scanning — its own design round |

---

## Verified Facts

Each of these was established by reading or running the installed code, not assumed. They exist so the implementer does not rediscover them.

**1. `testcontainers.minio` and `testcontainers.redis` are deprecated shims that warn on import, and this project turns warnings into errors.**

The installed `testcontainers/minio.py` is six lines: it re-exports from `testcontainers.community.minio` and then calls `warnings.warn(..., DeprecationWarning)`. `pyproject.toml` sets `filterwarnings = ["error"]`, so importing the short path raises rather than warns. Use `testcontainers.community.minio` and `testcontainers.community.redis`, which is the same path M1 already uses for `testcontainers.community.postgres`.

**2. `MinioContainer`'s default image is nearly four years old.**

`MinioContainer.__init__` defaults to `image="minio/minio:RELEASE.2022-12-02T19-19-22Z"`. Never accept the default. Pass the pinned tag explicitly, and pin it to the same tag `compose.yaml` uses — a gate that runs against a different MinIO than the local stack is not a gate.

**3. `MinioContainer` sets the *legacy* credential environment variables.**

Its constructor calls `with_env("MINIO_ACCESS_KEY", ...)` and `with_env("MINIO_SECRET_KEY", ...)`. Modern MinIO releases read `MINIO_ROOT_USER` and `MINIO_ROOT_PASSWORD`. With a modern pinned image the legacy names may be ignored, in which case the server comes up with the built-in `minioadmin`/`minioadmin` credentials and any test using the requested ones fails to authenticate. Task 11 sets both pairs with `.with_env()` so the container works whichever the pinned release honours.

**4. `AsyncRedisContainer.get_async_client()` is broken as shipped.**

Its body is `return await asyncRedis(host=..., port=..., password=...)`. `redis.asyncio.Redis(...)` is an ordinary constructor returning a client instance, not a coroutine, so awaiting it raises `TypeError: object Redis can't be used in 'await' expression`. Do not use `AsyncRedisContainer`. Use `RedisContainer` for lifecycle only, read `get_container_host_ip()` and `get_exposed_port(6379)` from it, and construct `redis.asyncio.Redis` directly.

**5. `MinioContainer.get_config()["endpoint"]` carries no URL scheme.**

It returns `f"{host_ip}:{exposed_port}"` — for example `localhost:32773`. `aioboto3`'s `endpoint_url` requires a scheme. Prefix it with `http://` when building `StorageSettings` in the integration fixture, or every call fails with an unhelpful `InvalidURL`.

**6. `testcontainers.community.minio` imports the `minio` Python SDK at module import time.**

Its first line is `from minio import Minio`. So `minio` is a test dependency even though the production adapter uses `aioboto3` and never imports it. Add it to the dev group with a comment saying why, or the import fails at collection.

**7. `Order.internal_note` exists and must not appear in a receipt.**

`domain/order.py` carries `internal_note: str | None = None`, documented as "Deliberately never exposed over HTTP", and M0's Task 12 asserts the API response omits it. A receipt rendered with `order.model_dump_json()` would include it and publish it. `render_receipt` must build its dictionary field by field, and Task 6 includes a test that fails if `internal_note` ever appears in the rendered bytes.

**8. Registering a readiness check today both reports *and* gates, inseparably.**

`api/health.py`'s readiness handler computes `healthy = all(result == "ok" for result in checks.values())` over every registered check and returns 503 if any failed. So there is currently no way to surface a dependency's status without also letting it remove the pod from load balancing. Spec 12.1 asks `/readyz` to check "database, cache and storage"; gating on a *shared* Redis would make every pod go unready simultaneously, converting a latency degradation the service is explicitly built to survive into a total outage. Task 2 adds a second, informational tier so `/readyz` reports all three and only the database gates. This is the same reasoning `container.py` already records for not registering the payment provider.

**9. The cache stores `internal_note`, and that is correct.**

`CachedOrderRepository` serialises the whole `Order`, `internal_note` included, because it must return exactly what the database would have returned. Redis here is internal infrastructure holding the same data PostgreSQL already holds — not an exposure. This is the opposite decision from Fact 7, and the difference is the audience: a receipt is served to a client, a cache entry is not.

**10. Version floors, resolved against the index on 2026-09-10.**

`redis` 8.1.0, `aioboto3` 15.5.0, `minio` 7.2.20, `opentelemetry-instrumentation-redis` 0.65b0, `opentelemetry-instrumentation-botocore` 0.65b0. The two instrumentation packages sit on the same `0.65b0` line as every other `opentelemetry-instrumentation-*` dependency already in `pyproject.toml`, so they need no separate version policy. The `b` is upstream's, not a typo.

**11. Whether `opentelemetry-instrumentation-botocore` produces spans for `aioboto3` is NOT established.**

That package patches `botocore`'s client machinery. `aioboto3` runs on `aiobotocore`, which replaces parts of that machinery with async equivalents. The instrumentation may therefore produce spans, produce none, or produce them without the async context. Task 12 begins by measuring this and branches on the result rather than assuming it works. Do not let this block the adapter: storage works with or without spans.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `src/reference_service/domain/receipts.py` | The `ReceiptStore` port and the `Receipt` value object. Imports Pydantic and the standard library only |
| `src/reference_service/domain/receipt_render.py` | `render_receipt(order) -> bytes` — a pure, deterministic function. No I/O |
| `src/reference_service/services/receipt.py` | `GetReceipt` — the render-on-miss use case |
| `src/reference_service/infrastructure/cache/__init__.py` | Package marker |
| `src/reference_service/infrastructure/cache/client.py` | `build_redis_client(settings)` — pool construction, nothing else |
| `src/reference_service/infrastructure/cache/order_repository.py` | `CachedOrderRepository` — the fail-open decorator |
| `src/reference_service/infrastructure/storage/__init__.py` | Package marker |
| `src/reference_service/infrastructure/storage/client.py` | `build_s3_session(settings)` and the shared client-config policy |
| `src/reference_service/infrastructure/storage/receipt_store.py` | `S3ReceiptStore` — the `aioboto3` adapter |
| `src/reference_service/infrastructure/memory/receipt_store.py` | `InMemoryReceiptStore` — the fallback when storage is unconfigured |
| `tests/unit/test_cached_order_repository.py` | Fail-open, invalidation, corrupt-payload-as-miss |
| `tests/unit/test_receipt_render.py` | Determinism, and the `internal_note` exclusion |
| `tests/unit/test_get_receipt.py` | Render-on-miss, serve-on-hit |
| `tests/unit/test_readiness_tiers.py` | Informational checks report but never gate |
| `tests/api/test_receipts.py` | The endpoint, against in-memory adapters |
| `tests/integration/test_cached_order_repository.py` | Real Redis: round trip, TTL, invalidation |
| `tests/integration/test_receipt_store.py` | Real MinIO: put/get, missing key, bucket handling |

**Modified:**

| Path | Change |
|---|---|
| `pyproject.toml` | Four runtime dependencies, two dev dependencies, two testcontainers extras |
| `src/reference_service/settings.py` | `CacheSettings`, `StorageSettings`, and two optional fields on `Settings` |
| `src/reference_service/container.py` | Build and wire both adapters; register two informational readiness checks; close both at shutdown |
| `src/reference_service/api/health.py` | Report informational checks without gating on them |
| `src/reference_service/api/deps.py` | `ReceiptStoreDep` and `GetReceiptDep` |
| `src/reference_service/api/v1/router.py` | The receipt route |
| `src/reference_service/api/errors.py` | A handler mapping `StorageUnavailableError` to 503 |
| `src/reference_service/infrastructure/errors.py` | `StorageUnavailableError` |
| `src/reference_service/observability/otel.py` | Redis and botocore instrumentation |
| `.importlinter` | `redis` and `aioboto3` added to both forbidden lists |
| `compose.yaml` | `redis`, `minio`, `minio-bootstrap`; new `app` environment |
| `justfile` | `redis-cli` and `minio-console` conveniences |
| `.env.example` | The new settings, commented |
| `openapi.json` | Regenerated — never hand-edited |
| `ops/grafana/dashboards/*.json` | The Redis saturation panel spec 7.4 names |
| `docs/roadmap.md`, `docs/reference/configuration.md`, `docs/explanation/architecture.md` | M4 marked done; the new settings and the two new adapters described |

---

## Task 1: Dependencies and settings

**Files:**
- Modify: `examples/reference-service/pyproject.toml`
- Modify: `examples/reference-service/src/reference_service/settings.py`
- Modify: `examples/reference-service/.importlinter`
- Modify: `examples/reference-service/.env.example`
- Test: `examples/reference-service/tests/unit/test_settings.py`

**Interfaces:**
- Consumes: nothing — this is the first task.
- Produces: `CacheSettings` (fields `dsn: RedisDsn`, `ttl_seconds: int`, `pool_size: int`, `connect_timeout_seconds: float`, `operation_timeout_seconds: float`), `StorageSettings` (fields `bucket: str`, `endpoint_url: HttpUrl | None`, `region: str`, `access_key_id: SecretStr`, `secret_access_key: SecretStr`, `connect_timeout_seconds: float`, `read_timeout_seconds: float`), and two new optional fields on `Settings`: `cache: CacheSettings | None` and `storage: StorageSettings | None`.

- [ ] **Step 1: Write the failing settings tests**

Add to `tests/unit/test_settings.py`:

```python
def test_cache_and_storage_are_absent_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """Both dependencies are optional, exactly as database and payment are."""
    settings = Settings(_env_file=None)
    assert settings.cache is None
    assert settings.storage is None


def test_cache_settings_are_read_from_the_environment(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_CACHE__DSN", "redis://localhost:6379/0")
    monkeypatch.setenv("APP_CACHE__TTL_SECONDS", "60")
    settings = Settings(_env_file=None)
    assert settings.cache is not None
    assert settings.cache.ttl_seconds == 60
    # Defaulted, not required: a cache that needs five variables set before it
    # works is a cache nobody turns on.
    assert settings.cache.pool_size == 10


def test_a_cache_timeout_must_be_positive(monkeypatch: pytest.MonkeyPatch) -> None:
    """Zero would mean 'no deadline' to redis-py, which is the one thing a
    fail-open cache must never do: it would hang the request it was added
    to speed up."""
    monkeypatch.setenv("APP_CACHE__DSN", "redis://localhost:6379/0")
    monkeypatch.setenv("APP_CACHE__OPERATION_TIMEOUT_SECONDS", "0")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_storage_settings_require_a_bucket(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_STORAGE__ACCESS_KEY_ID", "key")
    monkeypatch.setenv("APP_STORAGE__SECRET_ACCESS_KEY", "secret")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_a_bucket_name_that_s3_would_reject_is_refused_at_startup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Uppercase is invalid in an S3 bucket name. Catching it here turns a
    confusing runtime 400 from the provider into an exit-78 message naming
    the setting."""
    monkeypatch.setenv("APP_STORAGE__BUCKET", "Receipts")
    monkeypatch.setenv("APP_STORAGE__ACCESS_KEY_ID", "key")
    monkeypatch.setenv("APP_STORAGE__SECRET_ACCESS_KEY", "secret")
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_storage_credentials_are_secrets(monkeypatch: pytest.MonkeyPatch) -> None:
    """repr must not leak them. load_settings already elides input values on a
    validation error; this covers every OTHER path a settings object takes,
    including a traceback frame that happens to render it."""
    monkeypatch.setenv("APP_STORAGE__BUCKET", "receipts")
    monkeypatch.setenv("APP_STORAGE__ACCESS_KEY_ID", "key")
    monkeypatch.setenv("APP_STORAGE__SECRET_ACCESS_KEY", "sup3rs3cr3t")
    settings = Settings(_env_file=None)
    assert settings.storage is not None
    assert "sup3rs3cr3t" not in repr(settings.storage)
    assert settings.storage.secret_access_key.get_secret_value() == "sup3rs3cr3t"
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_settings.py -v -k "cache or storage or bucket"
```

Expected: FAIL. `AttributeError: 'Settings' object has no attribute 'cache'`.

- [ ] **Step 3: Add the dependencies**

In `pyproject.toml`, add to `[project].dependencies`:

```toml
    # The cache client. redis-py's own asyncio interface (redis.asyncio) —
    # aioredis was merged into it years ago and is archived, so there is no
    # separate async package to choose. Used ONLY by
    # infrastructure/cache/, which is the one place allowed to import it.
    "redis>=8.1",
    # The S3-compatible object store client. aioboto3 wraps aiobotocore,
    # which wraps botocore: one adapter serves MinIO, Amazon S3, Cloudflare
    # R2, Ceph and Backblaze B2, distinguished only by endpoint_url (spec
    # 9.1). boto3 itself is synchronous and would block the event loop on
    # every call.
    "aioboto3>=15.5",
    # Spans for Redis commands and for S3 calls. Same 0.65b0 line as every
    # other opentelemetry-instrumentation-* dependency above; the `b` is
    # upstream's permanent beta versioning, not a typo. Whether the
    # botocore instrumentation actually sees aioboto3's async calls is
    # measured in Task 12 rather than assumed.
    "opentelemetry-instrumentation-redis>=0.65b0",
    "opentelemetry-instrumentation-botocore>=0.65b0",
```

And in `[dependency-groups].dev`, replace the `testcontainers` line and add `minio`:

```toml
    "testcontainers[postgres,redis,minio]>=4.15",
    # Imported at module scope by testcontainers.community.minio (its first
    # line is `from minio import Minio`), so collection fails without it.
    # The production adapter uses aioboto3 and never imports this — it is
    # purely a test-container dependency.
    "minio>=7.2",
```

- [ ] **Step 4: Add the settings models**

In `settings.py`, add `RedisDsn` to the `pydantic` import list, then insert these two classes after `PaymentSettings`:

```python
class CacheSettings(BaseModel):
    # See LogSettings.model_config for why each sub-model needs its own
    # frozen=True rather than inheriting Settings's.
    model_config = ConfigDict(frozen=True)

    dsn: RedisDsn
    # How long a cached order stays valid. Five minutes is short enough that
    # a cache that somehow misses an invalidation self-corrects quickly, and
    # long enough to be worth having. The TTL is a safety net, not the
    # primary invalidation mechanism — CachedOrderRepository.save() deletes
    # the key outright.
    ttl_seconds: int = Field(default=300, ge=1)
    pool_size: int = Field(default=10, ge=1)
    # Both deadlines are deliberately sub-second, and both are required.
    #
    # This is the single most important pair of numbers in the cache. The
    # cache exists to make reads faster; a slow Redis that is not bounded
    # makes every read SLOWER than having no cache at all, because each
    # request pays the full Redis stall and then still queries PostgreSQL.
    # redis-py accepts None for "wait forever" on both, and a client built
    # that way is indistinguishable from a working one until the day Redis
    # starts swapping. gt=0 because 0 means "no deadline" to redis-py, not
    # "give up immediately".
    connect_timeout_seconds: float = Field(default=0.5, gt=0)
    operation_timeout_seconds: float = Field(default=0.5, gt=0)


# Amazon's bucket naming rules, the subset that is a pure string check:
# 3-63 characters, lowercase letters, digits, hyphens and dots, starting
# and ending alphanumeric. Deliberately not the full rule set — the
# IP-address-shaped and `xn--`-prefixed exclusions need more than a regex
# and their absence costs nothing here, because the provider rejects those
# too and this check exists to catch the ORDINARY mistake (a capital
# letter, an underscore, a trailing slash) at startup rather than on the
# first request.
_BUCKET_NAME_PATTERN = r"^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$"


class StorageSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    bucket: Annotated[str, StringConstraints(pattern=_BUCKET_NAME_PATTERN)]
    # None means real Amazon S3, where botocore derives the endpoint from
    # the region. Anything else — MinIO, Cloudflare R2, Ceph — sets it.
    # This one field is the whole of "one adapter for every S3-compatible
    # provider" (spec 9.1): there is no provider branch anywhere below it.
    endpoint_url: HttpUrl | None = None
    # Required by botocore's signing even when talking to MinIO, which does
    # not care what it is. us-east-1 is the conventional filler.
    region: str = "us-east-1"
    # SecretStr for the same reason PaymentSettings.api_key is: repr is
    # "**********", so a traceback frame or a careless f-string cannot
    # publish it.
    access_key_id: SecretStr
    secret_access_key: SecretStr
    connect_timeout_seconds: float = Field(default=2.0, gt=0)
    read_timeout_seconds: float = Field(default=5.0, gt=0)
```

Then add the two fields to `Settings`, directly after `payment`:

```python
    # Optional on purpose: None selects the plain repository with no cache
    # in front of it, exactly as `database` None selects the in-memory one.
    # A service generated with cache=none takes this path. See container.py.
    cache: CacheSettings | None = None
    # Optional on purpose: None selects InMemoryReceiptStore, so the receipt
    # endpoint works with no object store anywhere — the same arrangement
    # `payment` has with the in-memory gateway.
    storage: StorageSettings | None = None
```

`Annotated` and `StringConstraints` are already imported in this module; `RedisDsn` is the only new name.

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd examples/reference-service && uv sync && uv run pytest tests/unit/test_settings.py -v
```

Expected: PASS, all tests.

- [ ] **Step 6: Keep the domain sealed against the two new libraries**

In `.importlinter`, add `redis` and `aioboto3` to the `forbidden_modules` list of **both** the `domain-independence` and `services-independence` contracts. Without this, nothing stops a later change importing `redis` straight into a service — the contracts already name `sqlalchemy`, `httpx` and `stamina` for exactly this reason.

```bash
cd examples/reference-service && uv run lint-imports
```

Expected: all contracts pass.

- [ ] **Step 7: Document the settings**

Append to `.env.example`:

```bash
# --- Cache (optional) -------------------------------------------------
# Unset, the service runs with no cache and every read goes to PostgreSQL.
# Set, an order read is served from Redis when it is there. A Redis outage
# is never fatal: the cache fails open and PostgreSQL answers.
# APP_CACHE__DSN=redis://localhost:6379/0
# APP_CACHE__TTL_SECONDS=300

# --- Object storage (optional) ----------------------------------------
# Unset, receipts are held in memory and vanish on restart. Set, they are
# stored as objects. endpoint_url is what makes one adapter serve MinIO
# locally and Amazon S3 in production — leave it unset for real S3.
# APP_STORAGE__BUCKET=receipts
# APP_STORAGE__ENDPOINT_URL=http://localhost:9000
# APP_STORAGE__ACCESS_KEY_ID=minioadmin
# APP_STORAGE__SECRET_ACCESS_KEY=minioadmin
```

- [ ] **Step 8: Run the full fast suite and commit**

```bash
cd examples/reference-service && uv run pytest && uv run mypy && uv run ruff check . && uv run lint-imports
```

Expected: all pass.

```bash
git add examples/reference-service/pyproject.toml examples/reference-service/uv.lock \
        examples/reference-service/src/reference_service/settings.py \
        examples/reference-service/.importlinter examples/reference-service/.env.example \
        examples/reference-service/tests/unit/test_settings.py
git commit -m "feat(settings): add optional cache and object storage configuration"
```

---

## Task 2: An informational readiness tier

Spec 12.1 asks `/readyz` to check database, cache and storage. Verified Fact 8 explains why all three must not gate. This task adds the second tier, before either adapter exists, so the adapters can simply register into it.

**Files:**
- Modify: `examples/reference-service/src/reference_service/container.py`
- Modify: `examples/reference-service/src/reference_service/api/health.py`
- Test: `examples/reference-service/tests/unit/test_readiness_tiers.py` (create)
- Modify: `examples/reference-service/tests/unit/test_readiness_registry.py`
- Modify: `examples/reference-service/tests/unit/test_container.py:36,59`
- Modify: `examples/reference-service/openapi.json` (regenerated, never edited)

**Interfaces:**
- Consumes: nothing from Task 1.
- Produces: `ReadinessRegistry.register_informational(name, check)`; `ReadinessRegistry.run(timeout)` now returns `ReadinessReport` (fields `gating: dict[str, str]`, `informational: dict[str, str]`, property `healthy: bool`); `ReadinessResponse` gains a `dependencies: dict[str, str]` field.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_readiness_tiers.py`:

```python
"""The two readiness tiers.

Gating checks decide whether this instance receives traffic. Informational
checks are reported and never decide anything. The distinction exists
because a shared dependency that the service survives losing — the cache —
would otherwise take EVERY pod out of rotation at the same moment, turning
a latency degradation into a total outage.
"""

from __future__ import annotations

import pytest

from reference_service.container import ReadinessRegistry

pytestmark = pytest.mark.asyncio


async def test_an_informational_failure_does_not_make_the_report_unhealthy() -> None:
    registry = ReadinessRegistry()

    async def ok() -> None:
        return None

    async def broken() -> None:
        raise ConnectionError("redis is down")

    registry.register("database", ok)
    registry.register_informational("cache", broken)

    report = await registry.run(timeout=1.0)

    assert report.healthy is True
    assert report.gating == {"database": "ok"}
    assert report.informational == {"cache": "error: ConnectionError"}


async def test_a_gating_failure_does_make_the_report_unhealthy() -> None:
    registry = ReadinessRegistry()

    async def broken() -> None:
        raise ConnectionError("postgres is down")

    registry.register("database", broken)

    report = await registry.run(timeout=1.0)

    assert report.healthy is False
    assert report.gating == {"database": "error: ConnectionError"}


async def test_both_tiers_run_concurrently_not_one_tier_after_the_other() -> None:
    """The whole point of the concurrency in run(): worst case is ONE
    timeout, not one per tier. Two tiers run sequentially would double the
    endpoint's worst case, which is the bug this asserts against."""
    import asyncio

    registry = ReadinessRegistry()

    async def slow() -> None:
        await asyncio.sleep(10)

    registry.register("database", slow)
    registry.register_informational("cache", slow)

    started = asyncio.get_running_loop().time()
    report = await registry.run(timeout=0.2)
    elapsed = asyncio.get_running_loop().time() - started

    # Two 0.2s timeouts run concurrently finish in ~0.2s. Sequentially they
    # would take ~0.4s. Allow generous headroom for a slow machine while
    # still failing if the two tiers were awaited one after the other.
    assert elapsed < 0.35
    assert report.gating["database"].startswith("error: timeout")
    assert report.informational["cache"].startswith("error: timeout")


async def test_no_checks_at_all_is_healthy() -> None:
    report = await ReadinessRegistry().run(timeout=1.0)
    assert report.healthy is True
    assert report.gating == {}
    assert report.informational == {}
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_readiness_tiers.py -v
```

Expected: FAIL. `AttributeError: 'ReadinessRegistry' object has no attribute 'register_informational'`.

- [ ] **Step 3: Add the tier to `ReadinessRegistry`**

In `container.py`, add the report type above `ReadinessRegistry`:

```python
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
```

Then replace `ReadinessRegistry`'s body:

```python
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
        # results are the gating ones. Splitting by position rather than by
        # re-looking-up the name keeps this correct even if a name were ever
        # registered in both tiers.
        boundary = len(gating_names)
        return ReadinessReport(
            gating=dict(results[:boundary]),
            informational=dict(results[boundary:]),
        )
```

- [ ] **Step 4: Report the second tier from `/readyz`**

In `api/health.py`, add the field to the response model and use the report:

```python
class ReadinessResponse(BaseModel):
    status: str
    # Only these decide the status code.
    checks: dict[str, str]
    # Reported, never decisive. Empty when nothing informational is
    # registered, which is the case for a service with no cache and no
    # object store configured.
    dependencies: dict[str, str] = {}
```

```python
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
```

Also extend the module docstring's `/readyz` line to name the split:

```
  /readyz    readiness — can this instance serve traffic right now? Gating
                         dependencies are checked with short timeouts and a
                         failure returns 503. Informational ones are
                         reported under `dependencies` and never change the
                         status code — see ReadinessRegistry.
```

- [ ] **Step 5: Update the four existing registry tests**

`tests/unit/test_readiness_registry.py` compares `run()`'s result to a plain dict in four places. `run()` now returns `ReadinessReport`. Change each assertion to read `.gating`:

- line 30 area: `results = await registry.run(timeout=1.0)` → then assert against `results.gating`
- line 47 area: same
- line 69 area: same
- line 77: `assert await ReadinessRegistry().run(timeout=1.0) == {}` → `assert (await ReadinessRegistry().run(timeout=1.0)).gating == {}`

`tests/unit/test_container.py` reaches into the private attribute at lines 36 and 59: change `container.readiness._checks` to `container.readiness._gating` in both.

- [ ] **Step 6: Run the tests to verify they pass**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_readiness_tiers.py tests/unit/test_readiness_registry.py tests/unit/test_container.py tests/api/test_health.py -v
```

Expected: PASS, all tests.

- [ ] **Step 7: Regenerate the contract and check the gates**

`ReadinessResponse` gained a field, so the committed contract has changed.

```bash
cd examples/reference-service && just openapi && git diff --stat openapi.json
```

Expected: `openapi.json` gains a `dependencies` property on `ReadinessResponse`. Read the diff — it is your API change, in full.

```bash
cd examples/reference-service && just test && just contract-gates
```

Expected: the drift gate passes (the committed file now matches the code), and the breaking-change gate reports **no breaking changes** — an added optional response property is additive. If oasdiff reports a breaking change here, stop and read it: it means the field was added in a way that changes an existing response's required set, which is not what Step 4 wrote.

- [ ] **Step 8: Commit**

```bash
git add examples/reference-service/src/reference_service/container.py \
        examples/reference-service/src/reference_service/api/health.py \
        examples/reference-service/tests/unit/test_readiness_tiers.py \
        examples/reference-service/tests/unit/test_readiness_registry.py \
        examples/reference-service/tests/unit/test_container.py \
        examples/reference-service/openapi.json
git commit -m "feat(health): report non-gating dependencies from /readyz"
```

---

## Task 3: The cache decorator

The cache adds no port. `CachedOrderRepository` satisfies the existing `OrderRepository` Protocol, so no service, router or domain module changes — which is the whole demonstration.

**Files:**
- Create: `examples/reference-service/src/reference_service/infrastructure/cache/__init__.py`
- Create: `examples/reference-service/src/reference_service/infrastructure/cache/client.py`
- Create: `examples/reference-service/src/reference_service/infrastructure/cache/order_repository.py`
- Modify: `examples/reference-service/tests/fakes.py`
- Test: `examples/reference-service/tests/unit/test_cached_order_repository.py` (create)

**Interfaces:**
- Consumes: `CacheSettings` from Task 1.
- Produces: `build_redis_client(settings: CacheSettings) -> redis.asyncio.Redis`; `CachedOrderRepository(inner: OrderRepository, client: Redis, ttl_seconds: int)` satisfying `OrderRepository`; `CACHE_KEY_PREFIX: str`; and `FakeRedis` in `tests/fakes.py`.

- [ ] **Step 1: Write the failing tests**

First add the fake to `tests/fakes.py`. Hand-written rather than the `fakeredis` package for the reason the circuit breaker is hand-written: the surface actually used here is three commands, and a fake we control can be told to fail on demand, which is most of what these tests need.

```python
class FakeRedis:
    """The three commands CachedOrderRepository uses, plus a fault switch.

    `fail_with` makes every command raise, which is how the fail-open tests
    simulate a Redis outage without a container. `calls` records command
    names so a test can assert the cache was CONSULTED, not merely that the
    right value came back — a decorator that silently stopped calling Redis
    would still pass a value-only assertion.
    """

    def __init__(self) -> None:
        self.store: dict[str, bytes] = {}
        self.calls: list[str] = []
        self.fail_with: Exception | None = None
        self.last_ttl_seconds: int | None = None

    def _maybe_fail(self, command: str) -> None:
        self.calls.append(command)
        if self.fail_with is not None:
            raise self.fail_with

    async def get(self, key: str) -> bytes | None:
        self._maybe_fail("get")
        return self.store.get(key)

    async def set(self, key: str, value: bytes, ex: int | None = None) -> None:
        self._maybe_fail("set")
        self.store[key] = value
        self.last_ttl_seconds = ex

    async def delete(self, key: str) -> None:
        self._maybe_fail("delete")
        self.store.pop(key, None)
```

Then create `tests/unit/test_cached_order_repository.py`:

```python
"""The caching decorator.

Every test here answers one question: does the service still behave
correctly when Redis does not? The cache is an optimisation, and an
optimisation that can change an answer or take the service down is a bug
regardless of how much faster it is.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from reference_service.infrastructure.cache.order_repository import (
    CACHE_KEY_PREFIX,
    CachedOrderRepository,
)
from reference_service.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from tests.fakes import FakeRedis

pytestmark = pytest.mark.asyncio

TTL_SECONDS = 300


def build_order(internal_note: str | None = None) -> Order:
    line = OrderLine(
        sku="SKU-1",
        quantity=2,
        unit_price=Money(amount=Decimal("10.50"), currency="EUR"),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=(line,),
        total=Money(amount=Decimal("21.00"), currency="EUR"),
        internal_note=internal_note,
    )


def build_repository() -> tuple[CachedOrderRepository, InMemoryOrderRepository, FakeRedis]:
    inner = InMemoryOrderRepository()
    client = FakeRedis()
    return CachedOrderRepository(inner, client, TTL_SECONDS), inner, client


async def test_a_miss_falls_through_and_populates_the_cache() -> None:
    cached, inner, client = build_repository()
    order = build_order()
    await inner.save(order)

    assert await cached.get(order.id) == order

    assert f"{CACHE_KEY_PREFIX}{order.id}" in client.store
    assert client.last_ttl_seconds == TTL_SECONDS


async def test_a_hit_does_not_reach_the_wrapped_repository() -> None:
    """The assertion that proves the cache is doing anything at all: the
    inner repository is emptied, so a value can only come from Redis."""
    cached, inner, _client = build_repository()
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)

    inner.clear()

    assert await cached.get(order.id) == order


async def test_a_cached_order_round_trips_exactly_including_decimals() -> None:
    """Decimal is the field most likely to survive a round trip while
    quietly changing: JSON has no decimal type, so a serialiser that used a
    float would return 21.000000000000004 and the total_must_match_lines
    validator would reject it — or, worse, would not."""
    cached, inner, _client = build_repository()
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)
    inner.clear()

    from_cache = await cached.get(order.id)

    assert from_cache is not None
    assert from_cache.total.amount == Decimal("21.00")
    assert from_cache.lines[0].unit_price.amount == Decimal("10.50")
    assert from_cache == order


async def test_an_unknown_order_is_not_cached_as_absent() -> None:
    """Negative caching is deliberately not done — see the module comment in
    order_repository.py. This asserts the decision, so removing it is a
    visible choice rather than a silent drift."""
    cached, _inner, client = build_repository()
    missing = OrderId(uuid4())

    assert await cached.get(missing) is None
    assert client.store == {}


async def test_save_writes_through_and_invalidates() -> None:
    cached, inner, client = build_repository()
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)
    assert client.store != {}

    await cached.save(order)

    assert client.store == {}
    assert await inner.get(order.id) == order


async def test_a_redis_outage_on_read_still_returns_the_right_answer() -> None:
    """Fail-open, the single most important property here."""
    cached, inner, client = build_repository()
    order = build_order()
    await inner.save(order)
    client.fail_with = ConnectionError("redis is down")

    assert await cached.get(order.id) == order


async def test_a_redis_outage_on_write_does_not_fail_the_save() -> None:
    cached, inner, client = build_repository()
    order = build_order()
    client.fail_with = ConnectionError("redis is down")

    await cached.save(order)

    assert await inner.get(order.id) == order


async def test_a_corrupt_cached_payload_is_treated_as_a_miss() -> None:
    """The deliberate contrast with the database adapter, which raises
    CorruptPersistedDataError for the same situation. There, the bad data is
    the only copy. Here the real one is one call away, so the right response
    is to ignore the cache rather than fail the request."""
    cached, inner, client = build_repository()
    order = build_order()
    await inner.save(order)
    client.store[f"{CACHE_KEY_PREFIX}{order.id}"] = b"{not valid json"

    assert await cached.get(order.id) == order


async def test_a_payload_that_parses_but_violates_a_domain_rule_is_a_miss() -> None:
    """Harder than malformed JSON: this is well-formed JSON that the Order
    model refuses, which is what a cache entry written before a model change
    looks like."""
    cached, inner, client = build_repository()
    order = build_order()
    await inner.save(order)
    # A total that disagrees with the lines — total_must_match_lines rejects it.
    client.store[f"{CACHE_KEY_PREFIX}{order.id}"] = (
        order.model_copy(update={"total": Money(amount=Decimal("1.00"), currency="EUR")})
        .model_dump_json()
        .encode()
    )

    assert await cached.get(order.id) == order


async def test_the_wrapped_repository_is_never_bypassed_on_save() -> None:
    """A save that reached Redis but not PostgreSQL would lose the order."""
    cached, inner, client = build_repository()
    order = build_order()

    await cached.save(order)

    assert await inner.get(order.id) == order
    assert "set" not in client.calls
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_cached_order_repository.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'reference_service.infrastructure.cache'`.

- [ ] **Step 3: Write the client builder**

Create `src/reference_service/infrastructure/cache/__init__.py` (empty file) and `src/reference_service/infrastructure/cache/client.py`:

```python
"""The Redis connection pool.

One module whose only job is construction, mirroring
infrastructure/db/engine.py and infrastructure/http/client.py: the policy
decisions about timeouts and pool size live here, and the adapter beside it
holds only caching behaviour.
"""

from __future__ import annotations

from redis.asyncio import ConnectionPool, Redis

from reference_service.settings import CacheSettings


def build_redis_client(settings: CacheSettings) -> Redis:
    """Build the client. Never raises for an unreachable server.

    redis-py connects lazily, so nothing here touches the network — an
    unreachable Redis surfaces as a failed command, which
    CachedOrderRepository swallows, rather than as a crash at startup. That
    is the correct shape for a fail-open dependency: a cache that is down
    must not stop the process from starting.

    `decode_responses=False` is load-bearing. The values stored are
    `Order.model_dump_json()` bytes, and decoding them to `str` first would
    make every read allocate a string only for Pydantic to encode it back to
    bytes to parse it.
    """
    return Redis.from_pool(
        ConnectionPool.from_url(
            str(settings.dsn),
            max_connections=settings.pool_size,
            # Both deadlines, both required — see CacheSettings for why an
            # unbounded cache call is worse than no cache. socket_timeout
            # covers a command that has been sent and is awaiting a reply;
            # socket_connect_timeout covers establishing the connection.
            # Setting only one leaves the other unbounded.
            socket_connect_timeout=settings.connect_timeout_seconds,
            socket_timeout=settings.operation_timeout_seconds,
            decode_responses=False,
        )
    )
```

- [ ] **Step 4: Write the decorator**

Create `src/reference_service/infrastructure/cache/order_repository.py`:

```python
"""A caching decorator over the OrderRepository port.

This class satisfies `OrderRepository` and holds another `OrderRepository`.
Nothing above it — not GetOrder, not PlaceOrder, not the router, not the
domain — knows it exists. That is the point of the port: a cache is added
by wrapping in container.py and removed by not wrapping.

Two rules govern everything below.

FAIL OPEN. Every Redis failure is logged and swallowed, and the wrapped
repository answers. A cache exists to make reads faster; one that can make
them FAIL has made the service strictly worse than having no cache. There
is deliberately no setting that changes this.

THE DATABASE IS THE TRUTH. This class never returns something the wrapped
repository could not have returned, and never lets a write reach Redis
without reaching the repository first.
"""

from __future__ import annotations

import structlog
from pydantic import ValidationError
from redis.asyncio import Redis

from reference_service.domain.order import Order, OrderId
from reference_service.domain.repositories import OrderRepository

_logger = structlog.get_logger(__name__)

# The `v1` is a schema generation, not decoration. Cached payloads are
# serialised Order models, so a change to that model's shape makes every
# existing entry unparseable. Those entries are handled correctly anyway —
# _read treats them as misses — but bumping this prefix retires them all at
# once instead of leaving one TTL's worth of guaranteed misses being logged
# as rejected payloads. Bump it whenever Order gains, loses or renames a
# field.
CACHE_KEY_PREFIX = "order:v1:"


def _key(order_id: OrderId) -> str:
    return f"{CACHE_KEY_PREFIX}{order_id}"


class CachedOrderRepository:
    def __init__(
        self, inner: OrderRepository, client: Redis, ttl_seconds: int
    ) -> None:
        self._inner = inner
        self._client = client
        self._ttl_seconds = ttl_seconds

    async def get(self, order_id: OrderId) -> Order | None:
        key = _key(order_id)
        cached = await self._read(key)
        if cached is not None:
            return cached

        order = await self._inner.get(order_id)
        if order is not None:
            await self._write(key, order)
        # A missing order is deliberately NOT cached as absent. Negative
        # caching would be safe for correctness — save() invalidates the same
        # key — but it lets anyone fill Redis with entries for identifiers
        # that do not exist simply by asking for them. The read it would save
        # is a single indexed primary-key lookup, which is not worth that.
        return order

    async def save(self, order: Order) -> None:
        # Repository FIRST, then invalidate. The other order is a real bug:
        # delete-then-save leaves a window in which a concurrent reader
        # misses the cache, reads the OLD row from the database, and writes
        # it back with a full TTL — so the stale value outlives the write
        # that was supposed to replace it. Saving first bounds the staleness
        # to the length of the write instead.
        await self._inner.save(order)
        await self._invalidate(_key(order.id))

    async def _read(self, key: str) -> Order | None:
        try:
            raw = await self._client.get(key)
        except Exception:
            # Fail open. Includes redis.RedisError and the TimeoutError that
            # socket_timeout raises; caught broadly on purpose, because the
            # correct response to ANY failure of an optional dependency is
            # the same one, and a narrow list would turn an unanticipated
            # client error into a 500 for a request the database can serve.
            _logger.warning("cache.read_failed", key=key, exc_info=True)
            return None

        if raw is None:
            return None

        try:
            return Order.model_validate_json(raw)
        except ValidationError:
            # Not CorruptPersistedDataError, which is what db/mappers.py
            # raises for the same shape of problem. There, the unreadable row
            # is the only copy and hiding it would serve a wrong answer. Here
            # the real order is one call through to the repository away, so
            # the right move is to ignore the entry and carry on. Logged at
            # warning rather than swallowed silently: a steady stream of
            # these means the prefix above needs bumping.
            _logger.warning("cache.payload_rejected", key=key)
            return None

    async def _write(self, key: str, order: Order) -> None:
        try:
            await self._client.set(key, order.model_dump_json().encode(), ex=self._ttl_seconds)
        except Exception:
            _logger.warning("cache.write_failed", key=key, exc_info=True)

    async def _invalidate(self, key: str) -> None:
        try:
            await self._client.delete(key)
        except Exception:
            # The one failure with a lasting consequence: the stale entry
            # stays until its TTL expires. That bound is exactly why
            # CacheSettings.ttl_seconds exists and is measured in minutes
            # rather than hours — the TTL is the backstop for this branch.
            _logger.warning("cache.invalidate_failed", key=key, exc_info=True)
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_cached_order_repository.py -v
```

Expected: PASS, all eleven tests.

- [ ] **Step 6: Confirm the decorator really satisfies the port**

```bash
cd examples/reference-service && uv run mypy && uv run lint-imports
```

Expected: both pass. mypy is what proves `CachedOrderRepository` structurally satisfies `OrderRepository` — Task 4 assigns one to a variable of that type, and a signature mismatch fails there.

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service/src/reference_service/infrastructure/cache \
        examples/reference-service/tests/fakes.py \
        examples/reference-service/tests/unit/test_cached_order_repository.py
git commit -m "feat(cache): add a fail-open caching decorator over the order repository"
```

---

## Task 4: Wire the cache in, and add Redis to compose

**Files:**
- Modify: `examples/reference-service/src/reference_service/container.py`
- Modify: `examples/reference-service/compose.yaml`
- Modify: `examples/reference-service/justfile`
- Test: `examples/reference-service/tests/unit/test_container.py`

**Interfaces:**
- Consumes: `build_redis_client`, `CachedOrderRepository` (Task 3); `register_informational` (Task 2); `CacheSettings` (Task 1).
- Produces: `Container.redis` (`Redis | None`), and a `cache` entry under `/readyz`'s `dependencies` whenever cache settings are present.

- [ ] **Step 1: Write the failing container tests**

Add to `tests/unit/test_container.py`:

```python
def test_no_cache_settings_means_no_cache_and_no_report() -> None:
    settings = Settings(_env_file=None)
    container = build_container(settings)

    assert container.redis is None
    assert "cache" not in container.readiness._informational


def test_cache_settings_wrap_the_repository_and_register_a_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_DATABASE__DSN", "postgresql://app:secret@localhost:5432/app")
    monkeypatch.setenv("APP_CACHE__DSN", "redis://localhost:6379/0")
    container = build_container(Settings(_env_file=None))

    assert isinstance(container.orders, CachedOrderRepository)
    assert container.redis is not None
    # Reported, and NOT gating — the distinction Task 2 exists for.
    assert "cache" in container.readiness._informational
    assert "cache" not in container.readiness._gating


def test_a_cache_without_a_database_still_wraps_the_in_memory_repository(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An odd combination, but it must not crash: the decorator wraps
    whatever repository was selected, and neither one knows about the
    other."""
    monkeypatch.setenv("APP_CACHE__DSN", "redis://localhost:6379/0")
    container = build_container(Settings(_env_file=None))

    assert isinstance(container.orders, CachedOrderRepository)
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_container.py -v -k cache
```

Expected: FAIL. `AttributeError: 'Container' object has no attribute 'redis'`.

- [ ] **Step 3: Wire it into the container**

In `container.py`, add the imports, the field, a helper, and the wiring.

Field on `Container`, beside `engine` and `http_client`:

```python
    # None when no cache is configured. Held only so close_container can
    # release the pool at shutdown; nothing else reaches for it.
    redis: Redis | None = None
```

Then refactor `build_container` so the repository is chosen first and wrapped second. Replace the two `return`/construction paths with a single flow:

```python
def build_container(settings: Settings) -> Container:
    # ... the existing payment block is unchanged ...

    engine: AsyncEngine | None = None
    orders: OrderRepository
    if settings.database is None:
        # No database configured: the in-memory adapter, and no readiness
        # check, because there is no dependency to report on.
        orders = InMemoryOrderRepository()
    else:
        engine = build_engine(settings.database)
        orders = PostgresOrderRepository(build_sessionmaker(engine))

    # The cache wraps whatever was selected above and satisfies the same
    # port, so this is the ONLY place in the application that knows a cache
    # exists. Removing the cache is deleting this block.
    redis: Redis | None = None
    if settings.cache is not None:
        redis = build_redis_client(settings.cache)
        orders = CachedOrderRepository(orders, redis, settings.cache.ttl_seconds)

    container = Container(
        settings=settings,
        orders=orders,
        payments=payments,
        engine=engine,
        http_client=http_client,
        redis=redis,
    )

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

    # Deliberately no readiness check registered for the payment provider.
    # /readyz removing this pod from load balancing because someone else's
    # API is slow turns their outage into ours, and the circuit breaker
    # already handles that case properly — see HttpPaymentGateway.
    return container
```

The `cache_client = redis` rebinding is not decoration: `redis` is typed `Redis | None`, and closing over it directly would leave mypy unable to narrow the type inside the nested function.

- [ ] **Step 4: Close the pool at shutdown**

Extend `close_container`'s `try`/`finally` chain so a failure in one close cannot skip another:

```python
async def close_container(container: Container) -> None:
    """Release resources. Runs after in-flight requests finish.

    Nested `try`/`finally` rather than sequential `if`s: without it, an
    exception from one close would skip every close after it, leaking
    pooled connections on exactly the shutdown that also had trouble —
    the moment a leak is least affordable. Each resource's cleanup is
    independent of the others' success.
    """
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
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_container.py -v && uv run mypy
```

Expected: PASS, and mypy clean. mypy passing is the proof that `CachedOrderRepository` satisfies `OrderRepository` — `orders` is declared as that type and assigned both a plain and a wrapped repository.

- [ ] **Step 6: Add Redis to compose**

In `compose.yaml`, add the service:

```yaml
  # The cache. Not behind a profile: it is small, starts in under a second,
  # and `just up` should exercise the same arrangement production runs.
  # Losing it is survivable by design — see CachedOrderRepository — so
  # nothing `depends_on` it with service_healthy the way `app` does for
  # postgres.
  redis:
    image: redis:8-alpine
    ports:
      # Published so `just redis-cli` and any local tool can reach it. The
      # application inside compose does NOT use this — it connects over the
      # compose network to the host name `redis`.
      - "6379:6379"
    command:
      # An explicit bound, because the default is unbounded: a Redis with no
      # maxmemory grows until the host's OOM killer picks a process, and on
      # a developer's laptop that process is as likely to be the database as
      # this. allkeys-lru makes it a cache rather than a store — under
      # pressure it evicts the least recently used key instead of returning
      # errors on write, which is the correct behaviour for data whose
      # source of truth is PostgreSQL.
      - redis-server
      - --maxmemory
      - 256mb
      - --maxmemory-policy
      - allkeys-lru
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
```

And add to the `app` service's `environment` block:

```yaml
      # `redis` is the compose service name above. Set here rather than
      # defaulted, because `just up` should exercise the cached path — an
      # adapter that only runs in tests is an adapter nobody has really run.
      APP_CACHE__DSN: redis://redis:6379/0
```

- [ ] **Step 7: Add the convenience recipe**

In `justfile`, beside `psql`:

```just
# An interactive redis-cli session against the running compose cache.
redis-cli:
    docker compose exec redis redis-cli
```

- [ ] **Step 8: Verify the stack end to end by hand**

```bash
cd examples/reference-service && just up
```

In a second terminal:

```bash
curl -s localhost:8000/readyz | python3 -m json.tool
```

Expected: `checks` contains `database: ok`, and `dependencies` contains `cache: ok`.

Now place an order, read it twice, and confirm the second read was served from Redis:

```bash
cd examples/reference-service && ORDER=$(curl -s -X POST localhost:8000/api/v1/orders -H 'content-type: application/json' -d '{"customer_id":"11111111-1111-1111-1111-111111111111","lines":[{"sku":"SKU-1","quantity":2,"unit_amount":"10.50","currency":"EUR"}]}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])') && curl -s "localhost:8000/api/v1/orders/$ORDER" > /dev/null && docker compose exec redis redis-cli KEYS 'order:v1:*'
```

Expected: one key, `order:v1:<the order id>`.

Then prove the fail-open path is real, which is the property no unit test can fully demonstrate:

```bash
cd examples/reference-service && docker compose stop redis && curl -s -o /dev/null -w '%{http_code}\n' "localhost:8000/api/v1/orders/$ORDER" && curl -s localhost:8000/readyz | python3 -m json.tool
```

Expected: the order read returns **200** with Redis stopped, and `/readyz` returns **200** with `status: ok`, `checks.database: ok`, and `dependencies.cache` showing an error. If `/readyz` returns 503 here, the check was registered as gating and Task 2's distinction has been lost.

```bash
cd examples/reference-service && docker compose start redis && just down
```

- [ ] **Step 9: Commit**

```bash
git add examples/reference-service/src/reference_service/container.py \
        examples/reference-service/compose.yaml examples/reference-service/justfile \
        examples/reference-service/tests/unit/test_container.py
git commit -m "feat(cache): wire the redis cache into the container and compose"
```

---

## Task 5: Redis integration tests

Unit tests with `FakeRedis` prove the decorator's logic. They cannot prove that the real client, the real serialisation and a real TTL agree. That is this task.

**Files:**
- Modify: `examples/reference-service/tests/integration/conftest.py`
- Test: `examples/reference-service/tests/integration/test_cached_order_repository.py` (create)

**Interfaces:**
- Consumes: `build_redis_client`, `CachedOrderRepository`, `CACHE_KEY_PREFIX` (Task 3); `CacheSettings` (Task 1).
- Produces: session-scoped `redis_container` and function-scoped `redis_client` fixtures; `REDIS_IMAGE`.

- [ ] **Step 1: Add the container fixtures**

In `tests/integration/conftest.py`, add the import and image pin beside the existing PostgreSQL ones:

```python
from testcontainers.community.redis import RedisContainer

# Pinned, and pinned to the same tag compose uses. A gate that passes
# against a different Redis than the local stack runs is not a gate.
#
# testcontainers.redis (the short path) is a deprecated shim that calls
# warnings.warn on import, and this project runs filterwarnings=["error"],
# so importing it would fail outright. The community path above is the
# supported one and is what tests/integration already uses for PostgreSQL.
REDIS_IMAGE = "redis:8-alpine"
```

Then the fixtures:

```python
@pytest.fixture(scope="session")
def redis_container() -> Iterator[RedisContainer]:
    """One Redis for the whole session, as with PostgreSQL above.

    RedisContainer, deliberately, and NOT AsyncRedisContainer: the latter's
    get_async_client() is `return await asyncRedis(...)`, and
    redis.asyncio.Redis is an ordinary constructor returning a client rather
    than a coroutine, so awaiting it raises `TypeError: object Redis can't
    be used in 'await' expression`. This fixture uses the sync container for
    lifecycle only and builds the async client from its host and port.
    """
    with RedisContainer(image=REDIS_IMAGE) as container:
        yield container


@pytest.fixture(scope="session")
def cache_settings(redis_container: RedisContainer) -> CacheSettings:
    host = redis_container.get_container_host_ip()
    port = redis_container.get_exposed_port(6379)
    return CacheSettings(dsn=f"redis://{host}:{port}/0")  # type: ignore[arg-type]


@pytest_asyncio.fixture(loop_scope="session")
async def redis_client(cache_settings: CacheSettings) -> AsyncIterator[Redis]:
    """A client per test, flushed before each one.

    Function-scoped rather than session-scoped even though the container is
    shared: leftover keys from a previous test are exactly the kind of
    cross-test coupling that makes a cache suite pass in one order and fail
    in another. Flushing is milliseconds; a container per test is not.
    """
    client = build_redis_client(cache_settings)
    await client.flushdb()
    yield client
    await client.aclose()
```

Add `CacheSettings`, `build_redis_client` and `Redis` to the module's imports.

- [ ] **Step 2: Write the failing integration tests**

Create `tests/integration/test_cached_order_repository.py`:

```python
"""The caching decorator against a real Redis.

What the unit tests cannot cover: that redis-py, the real serialisation and
a real TTL agree with each other. FakeRedis stores whatever bytes it is
given and hands them back; a real server has an encoding, an expiry clock
and a maximum value size.

This module carries its own `pytestmark` with `loop_scope="session"`, per
the rule in this directory's conftest.py: a module using a session-scoped
async fixture without it crashes with `RuntimeError: Event loop is closed`
on the second test that opens a connection.
"""

from __future__ import annotations

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from redis.asyncio import Redis

from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from reference_service.infrastructure.cache.order_repository import (
    CACHE_KEY_PREFIX,
    CachedOrderRepository,
)
from reference_service.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)

pytestmark = pytest.mark.asyncio(loop_scope="session")


def build_order() -> Order:
    line = OrderLine(
        sku="SKU-1",
        quantity=3,
        unit_price=Money(amount=Decimal("19.99"), currency="GBP"),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=(line,),
        total=Money(amount=Decimal("59.97"), currency="GBP"),
        internal_note="never leaves the service",
    )


async def test_an_order_round_trips_through_a_real_redis(
    redis_client: Redis,
) -> None:
    inner = InMemoryOrderRepository()
    cached = CachedOrderRepository(inner, redis_client, ttl_seconds=300)
    order = build_order()
    await inner.save(order)

    await cached.get(order.id)
    inner.clear()
    from_cache = await cached.get(order.id)

    assert from_cache == order
    # The value most likely to survive a round trip while quietly changing.
    assert from_cache is not None
    assert from_cache.total.amount == Decimal("59.97")


async def test_the_ttl_is_actually_applied_on_the_server(
    redis_client: Redis,
) -> None:
    """FakeRedis records the TTL argument. Only a real server can say the
    key genuinely expires — a `set` whose expiry argument was passed in the
    wrong unit would pass the unit test and leak entries here."""
    inner = InMemoryOrderRepository()
    cached = CachedOrderRepository(inner, redis_client, ttl_seconds=300)
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)

    remaining = await redis_client.ttl(f"{CACHE_KEY_PREFIX}{order.id}")

    # Seconds, not milliseconds: a value near 300 proves the unit is right.
    assert 290 < remaining <= 300


async def test_a_one_second_ttl_expires_and_the_read_falls_through(
    redis_client: Redis,
) -> None:
    inner = InMemoryOrderRepository()
    cached = CachedOrderRepository(inner, redis_client, ttl_seconds=1)
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)

    await asyncio.sleep(1.5)

    assert await redis_client.get(f"{CACHE_KEY_PREFIX}{order.id}") is None
    # Still correct after expiry — it falls through to the repository.
    assert await cached.get(order.id) == order


async def test_save_removes_the_key_from_a_real_server(
    redis_client: Redis,
) -> None:
    inner = InMemoryOrderRepository()
    cached = CachedOrderRepository(inner, redis_client, ttl_seconds=300)
    order = build_order()
    await inner.save(order)
    await cached.get(order.id)
    assert await redis_client.exists(f"{CACHE_KEY_PREFIX}{order.id}") == 1

    await cached.save(order)

    assert await redis_client.exists(f"{CACHE_KEY_PREFIX}{order.id}") == 0


async def test_an_unreachable_redis_fails_open_against_a_real_client(
    cache_settings: CacheSettings,
) -> None:
    """The fail-open path with a REAL client and a genuinely dead address.

    FakeRedis raises an exception we chose. This raises whatever redis-py
    actually raises when nothing is listening — the case that matters, and
    the one a hand-picked exception type can quietly fail to cover.
    Port 1 is reserved and never has a listener.
    """
    from reference_service.settings import CacheSettings as _CacheSettings

    dead = _CacheSettings(dsn="redis://127.0.0.1:1/0")  # type: ignore[arg-type]
    client = build_redis_client(dead)
    try:
        inner = InMemoryOrderRepository()
        cached = CachedOrderRepository(inner, client, ttl_seconds=300)
        order = build_order()
        await inner.save(order)

        assert await cached.get(order.id) == order
        await cached.save(order)
    finally:
        await client.aclose()
```

Add `build_redis_client` and `CacheSettings` to this module's imports.

- [ ] **Step 3: Run the tests**

```bash
cd examples/reference-service && uv sync && uv run pytest -m integration -k cached_order -v
```

Expected: PASS, all five. The first run pulls `redis:8-alpine`, so allow time.

- [ ] **Step 4: Confirm the fast tier still needs no Docker**

```bash
cd examples/reference-service && uv run pytest
```

Expected: PASS, with the integration tier deselected. If this now tries to start a container, the automatic `integration` marker in `conftest.py` is not being applied to the new module.

- [ ] **Step 5: Commit**

```bash
git add examples/reference-service/tests/integration/conftest.py \
        examples/reference-service/tests/integration/test_cached_order_repository.py
git commit -m "test(cache): exercise the caching decorator against a real redis"
```

---

## Task 6: The receipt document

A pure function and a port. No I/O, no adapter yet — this task is the part of object storage that has nothing to do with storage.

**Files:**
- Create: `examples/reference-service/src/reference_service/domain/receipts.py`
- Create: `examples/reference-service/src/reference_service/domain/receipt_render.py`
- Test: `examples/reference-service/tests/unit/test_receipt_render.py` (create)

**Interfaces:**
- Consumes: `Order`, `OrderId` from `domain/order.py`.
- Produces: `ReceiptStore` Protocol (`get(order_id) -> bytes | None`, `put(order_id, content) -> None`); `render_receipt(order: Order) -> bytes`; `RECEIPT_MEDIA_TYPE = "application/json"`; `RECEIPT_SCHEMA_VERSION = 1`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_receipt_render.py`:

```python
"""Rendering a receipt.

Two properties carry this module. The document must be DETERMINISTIC, or
the store's "write once, serve the same bytes forever" behaviour is
untestable and a re-render silently produces a different object. And it
must never contain `internal_note`, which the Order aggregate documents as
never leaving the service.
"""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import UUID, uuid4

from reference_service.domain.order import (
    AuthorisationId,
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from reference_service.domain.receipt_render import (
    RECEIPT_SCHEMA_VERSION,
    render_receipt,
)


def build_order(internal_note: str | None = None) -> Order:
    lines = (
        OrderLine(
            sku="SKU-B",
            quantity=1,
            unit_price=Money(amount=Decimal("5.00"), currency="EUR"),
        ),
        OrderLine(
            sku="SKU-A",
            quantity=2,
            unit_price=Money(amount=Decimal("10.50"), currency="EUR"),
        ),
    )
    return Order(
        id=OrderId(UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")),
        customer_id=CustomerId(UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")),
        lines=lines,
        total=Money(amount=Decimal("26.00"), currency="EUR"),
        internal_note=internal_note,
        authorisation_id=AuthorisationId("auth-123"),
    )


def test_rendering_the_same_order_twice_produces_identical_bytes() -> None:
    """The property the whole store depends on. If this ever fails, a
    re-render after an eviction writes a DIFFERENT object under the same
    key, and 'the receipt' stops being one thing."""
    order = build_order()
    assert render_receipt(order) == render_receipt(order)


def test_the_internal_note_never_appears_in_a_receipt() -> None:
    """Order.internal_note is documented as never exposed over HTTP, and a
    receipt is served over HTTP. A renderer written as
    `order.model_dump_json()` would publish it, which is why the document
    below is built field by field."""
    order = build_order(internal_note="customer disputed a previous order")

    rendered = render_receipt(order)

    assert b"internal_note" not in rendered
    assert b"disputed" not in rendered


def test_the_receipt_carries_the_fields_a_customer_needs() -> None:
    document = json.loads(render_receipt(build_order()))

    assert document["order_id"] == "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
    assert document["customer_id"] == "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"
    assert document["authorisation_id"] == "auth-123"
    assert document["currency"] == "EUR"
    assert document["total"] == "26.00"
    assert len(document["lines"]) == 2


def test_money_is_rendered_as_a_string_not_a_float() -> None:
    """A receipt is a financial document. Serialising 10.50 as a JSON number
    hands the reader an IEEE 754 double and the rounding that comes with it;
    a string preserves the exact decimal the order was priced in."""
    document = json.loads(render_receipt(build_order()))

    assert document["total"] == "26.00"
    assert isinstance(document["total"], str)
    assert all(isinstance(line["unit_price"], str) for line in document["lines"])


def test_line_order_follows_the_order_not_the_alphabet() -> None:
    """Keys are sorted for determinism; the lines array must NOT be, or the
    receipt stops matching the order it describes."""
    document = json.loads(render_receipt(build_order()))

    assert [line["sku"] for line in document["lines"]] == ["SKU-B", "SKU-A"]


def test_the_document_records_its_schema_version() -> None:
    """A stored receipt outlives the code that wrote it. Without a version
    in the document, a reader years from now has to guess which shape it
    is."""
    document = json.loads(render_receipt(build_order()))

    assert document["schema_version"] == RECEIPT_SCHEMA_VERSION


def test_a_subtotal_is_computed_per_line() -> None:
    document = json.loads(render_receipt(build_order()))
    by_sku = {line["sku"]: line for line in document["lines"]}

    assert by_sku["SKU-A"]["quantity"] == 2
    assert by_sku["SKU-A"]["unit_price"] == "10.50"
    assert by_sku["SKU-A"]["subtotal"] == "21.00"
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_receipt_render.py -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'reference_service.domain.receipt_render'`.

- [ ] **Step 3: Write the port**

Create `src/reference_service/domain/receipts.py`:

```python
"""The receipt store port: what the domain needs, not how it is done.

Imports nothing but the standard library and the Order aggregate's
identifier type, exactly as the rest of this layer does. `aioboto3` lives on
the far side of this file, in infrastructure/storage/receipt_store.py — the
domain names the operation and never learns that it travels to S3.

The port speaks in `bytes` rather than a Receipt model on purpose. The
document's SHAPE is receipt_render.py's business; a store's business is
holding an opaque blob under a key and giving it back unchanged. Putting a
typed model here would make every future document format a change to this
port, which is precisely the coupling a port exists to prevent.

One error can come out of an implementation:

  - StorageUnavailableError (infrastructure/errors.py) — the store could
    not be reached. A statement about our dependency: not the caller's
    fault, and the same request may well succeed later. It lives in
    infrastructure for the same reason PaymentUnavailableError does — it is
    raised by the adapter, and infrastructure must not import services.

A missing object is NOT an error. It is a `None` return, because "no
receipt has been rendered yet" is the ordinary state of every order that
nobody has asked about, not a failure.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from reference_service.domain.order import OrderId


@runtime_checkable
class ReceiptStore(Protocol):
    async def get(self, order_id: OrderId) -> bytes | None:
        """Return the stored receipt, or None when none has been stored.

        Raises `StorageUnavailableError` when the store cannot be reached.
        The distinction matters: None means "render it", and the error
        means "come back later". Collapsing them would make an outage look
        like an empty bucket and silently re-render on every request.
        """
        ...

    async def put(self, order_id: OrderId, content: bytes) -> None:
        """Store the receipt, creating or replacing it."""
        ...
```

- [ ] **Step 4: Write the renderer**

Create `src/reference_service/domain/receipt_render.py`:

```python
"""Rendering an Order into a receipt document.

A pure function: same order in, same bytes out, no I/O and no clock. That
is not incidental — it is what lets GetReceipt store the result once and
serve it forever, and what lets a test assert that a re-render matches what
was stored.

Deliberately NO `generated_at` timestamp. It is the obvious field to add
and it would destroy determinism: every re-render after an eviction would
produce different bytes under the same key, so "the receipt for order X"
would depend on when it happened to be regenerated. The order carries the
facts a receipt needs; when the document was serialised is not one of them.
"""

from __future__ import annotations

import json
from typing import Any

from reference_service.domain.order import Order

RECEIPT_MEDIA_TYPE = "application/json"

# Bumped whenever the document below gains, loses or renames a field. A
# stored receipt outlives the code that wrote it, so a reader needs to know
# which shape it is holding without guessing from which keys are present.
RECEIPT_SCHEMA_VERSION = 1


def render_receipt(order: Order) -> bytes:
    """Render `order` as a receipt document.

    Built field by field rather than from `order.model_dump()`. That is the
    whole defence for `internal_note`, which the Order aggregate documents
    as never exposed over HTTP: a dump-everything renderer would publish it
    the moment someone set it, and would silently publish every future
    internal field too. An allowlist cannot be forgotten the way a denylist
    can.
    """
    document: dict[str, Any] = {
        "schema_version": RECEIPT_SCHEMA_VERSION,
        "order_id": str(order.id),
        "customer_id": str(order.customer_id),
        "authorisation_id": order.authorisation_id,
        "currency": order.total.currency,
        # Every amount is a STRING. A receipt is a financial document, and
        # JSON numbers are IEEE 754 doubles in most readers — 10.50 parses
        # back as 10.5 and 0.1 + 0.2 stops being 0.3. The Decimal the order
        # was priced in survives only as text.
        "total": str(order.total.amount),
        "lines": [
            {
                "sku": line.sku,
                "quantity": line.quantity,
                "unit_price": str(line.unit_price.amount),
                "subtotal": str(line.subtotal.amount),
            }
            for line in order.lines
        ],
    }
    # sort_keys for determinism, and a separator pair with no spaces so the
    # bytes do not depend on json's default formatting. The LINES list is
    # untouched by sort_keys — it keeps the order's own sequence, which is
    # what the receipt is describing.
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_receipt_render.py -v
```

Expected: PASS, all seven.

- [ ] **Step 6: Confirm the domain stayed sealed**

```bash
cd examples/reference-service && uv run lint-imports && uv run mypy
```

Expected: both pass. `domain-independence` proves the two new modules import no framework, no infrastructure and no service.

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service/src/reference_service/domain/receipts.py \
        examples/reference-service/src/reference_service/domain/receipt_render.py \
        examples/reference-service/tests/unit/test_receipt_render.py
git commit -m "feat(domain): add the receipt store port and a deterministic renderer"
```

---

## Task 7: The in-memory store and the GetReceipt service

**Files:**
- Create: `examples/reference-service/src/reference_service/infrastructure/memory/receipt_store.py`
- Create: `examples/reference-service/src/reference_service/services/receipt.py`
- Test: `examples/reference-service/tests/unit/test_get_receipt.py` (create)

**Interfaces:**
- Consumes: `ReceiptStore`, `render_receipt` (Task 6); `OrderRepository`, `OrderNotFoundError`.
- Produces: `InMemoryReceiptStore` (with `clear()`); `GetReceipt(orders: OrderRepository, receipts: ReceiptStore)` callable as `await get_receipt(order_id) -> bytes`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_get_receipt.py`:

```python
"""The render-on-miss use case."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest

from reference_service.domain.errors import OrderNotFoundError
from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from reference_service.domain.receipt_render import render_receipt
from reference_service.infrastructure.memory.order_repository import (
    InMemoryOrderRepository,
)
from reference_service.infrastructure.memory.receipt_store import (
    InMemoryReceiptStore,
)
from reference_service.services.receipt import GetReceipt

pytestmark = pytest.mark.asyncio


def build_order() -> Order:
    line = OrderLine(
        sku="SKU-1",
        quantity=2,
        unit_price=Money(amount=Decimal("10.50"), currency="EUR"),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=(line,),
        total=Money(amount=Decimal("21.00"), currency="EUR"),
    )


async def test_a_first_request_renders_and_stores() -> None:
    orders = InMemoryOrderRepository()
    receipts = InMemoryReceiptStore()
    order = build_order()
    await orders.save(order)

    content = await GetReceipt(orders, receipts)(order.id)

    assert content == render_receipt(order)
    assert await receipts.get(order.id) == content


async def test_a_second_request_serves_the_stored_bytes() -> None:
    """Not merely 'equal bytes' — the STORED object. A service that
    re-rendered every time would pass an equality check against the
    renderer and never touch storage at all."""
    orders = InMemoryOrderRepository()
    receipts = InMemoryReceiptStore()
    order = build_order()
    await orders.save(order)
    await GetReceipt(orders, receipts)(order.id)

    # Replace what is stored. A re-render would overwrite this; serving the
    # stored object returns it.
    await receipts.put(order.id, b"stored-earlier")

    assert await GetReceipt(orders, receipts)(order.id) == b"stored-earlier"


async def test_an_unknown_order_raises_rather_than_rendering_nothing() -> None:
    orders = InMemoryOrderRepository()
    receipts = InMemoryReceiptStore()

    with pytest.raises(OrderNotFoundError):
        await GetReceipt(orders, receipts)(OrderId(uuid4()))


async def test_an_unknown_order_writes_nothing_to_the_store() -> None:
    orders = InMemoryOrderRepository()
    receipts = InMemoryReceiptStore()
    missing = OrderId(uuid4())

    with pytest.raises(OrderNotFoundError):
        await GetReceipt(orders, receipts)(missing)

    assert await receipts.get(missing) is None
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_get_receipt.py -v
```

Expected: FAIL with `ModuleNotFoundError` for `reference_service.services.receipt`.

- [ ] **Step 3: Write the in-memory store**

Create `src/reference_service/infrastructure/memory/receipt_store.py`:

```python
"""In-memory receipt store.

The adapter selected when no object storage is configured, so the receipt
endpoint works on a laptop with nothing running but the application — the
same job InMemoryOrderRepository does for the database. Receipts vanish on
restart, which is harmless: a receipt is derived from its order and is
re-rendered on the next request.
"""

from __future__ import annotations

from reference_service.domain.order import OrderId


class InMemoryReceiptStore:
    def __init__(self) -> None:
        self._receipts: dict[OrderId, bytes] = {}

    async def get(self, order_id: OrderId) -> bytes | None:
        return self._receipts.get(order_id)

    async def put(self, order_id: OrderId, content: bytes) -> None:
        self._receipts[order_id] = content

    def clear(self) -> None:
        self._receipts.clear()
```

- [ ] **Step 4: Write the service**

Create `src/reference_service/services/receipt.py`:

```python
"""GetReceipt: serve a stored receipt, rendering it the first time.

An application service. It orchestrates — repository, renderer, store — and
holds no business rules of its own; what a receipt CONTAINS is
domain/receipt_render.py's decision.

Why the order is looked up FIRST, before the store:

  1. It gives the right answer for an unknown identifier. A store-first
     service would return a receipt for an order that no longer resolves,
     and would reach object storage for every bogus id a caller cared to
     invent.
  2. It costs almost nothing. When a cache is configured that read is a
     Redis hit, not a database query — the two halves of M4 pay for each
     other here.

Why the store is not written by PlaceOrder: an object-store outage must
never be able to fail a payment. Rendering on demand keeps storage entirely
out of the write path, at the cost of one slower first request per order.
"""

from __future__ import annotations

from reference_service.domain.errors import OrderNotFoundError
from reference_service.domain.order import OrderId
from reference_service.domain.receipt_render import render_receipt
from reference_service.domain.receipts import ReceiptStore
from reference_service.domain.repositories import OrderRepository


class GetReceipt:
    def __init__(self, orders: OrderRepository, receipts: ReceiptStore) -> None:
        self._orders = orders
        self._receipts = receipts

    async def __call__(self, order_id: OrderId) -> bytes:
        order = await self._orders.get(order_id)
        if order is None:
            raise OrderNotFoundError(order_id)

        stored = await self._receipts.get(order_id)
        if stored is not None:
            return stored

        content = render_receipt(order)
        # Not wrapped in a try. A store that cannot be written is a store
        # that cannot be read either, and its own adapter already raises
        # StorageUnavailableError, which api/errors.py maps to 503. Catching
        # it here to return the freshly rendered bytes anyway would hide a
        # broken dependency behind responses that look perfectly healthy,
        # and every request would re-render forever.
        await self._receipts.put(order_id, content)
        return content
```

- [ ] **Step 5: Run the tests to verify they pass**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_get_receipt.py -v && uv run mypy && uv run lint-imports
```

Expected: PASS, four tests, and both gates clean.

- [ ] **Step 6: Commit**

```bash
git add examples/reference-service/src/reference_service/infrastructure/memory/receipt_store.py \
        examples/reference-service/src/reference_service/services/receipt.py \
        examples/reference-service/tests/unit/test_get_receipt.py
git commit -m "feat(receipts): add the in-memory store and the GetReceipt service"
```

---

## Task 8: The receipt endpoint

**Files:**
- Modify: `examples/reference-service/src/reference_service/infrastructure/errors.py`
- Modify: `examples/reference-service/src/reference_service/api/errors.py`
- Modify: `examples/reference-service/src/reference_service/api/deps.py`
- Modify: `examples/reference-service/src/reference_service/api/v1/schemas.py`
- Modify: `examples/reference-service/src/reference_service/api/v1/router.py`
- Modify: `examples/reference-service/src/reference_service/container.py`
- Test: `examples/reference-service/tests/api/test_receipts.py` (create)
- Modify: `examples/reference-service/openapi.json` (regenerated)

**Interfaces:**
- Consumes: `GetReceipt` (Task 7), `InMemoryReceiptStore` (Task 7), `RECEIPT_MEDIA_TYPE` (Task 6).
- Produces: `StorageUnavailableError`; `Container.receipts: ReceiptStore`; `ReceiptStoreDep`, `GetReceiptDep`; `ReceiptResponse` and `ReceiptLine` schemas; `GET /api/v1/orders/{order_id}/receipt`.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_receipts.py`:

```python
"""The receipt endpoint."""

from __future__ import annotations

import json
from decimal import Decimal
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from reference_service.api.v1.schemas import ReceiptResponse
from reference_service.domain.order import (
    CustomerId,
    Money,
    Order,
    OrderId,
    OrderLine,
)
from reference_service.domain.receipt_render import render_receipt
from reference_service.infrastructure.errors import StorageUnavailableError


def build_order() -> Order:
    line = OrderLine(
        sku="SKU-1",
        quantity=2,
        unit_price=Money(amount=Decimal("10.50"), currency="EUR"),
    )
    return Order(
        id=OrderId(uuid4()),
        customer_id=CustomerId(uuid4()),
        lines=(line,),
        total=Money(amount=Decimal("21.00"), currency="EUR"),
        internal_note="must not be published",
    )


def test_a_receipt_is_returned_as_json(client: TestClient) -> None:
    order = build_order()
    container = client.app.state.container  # type: ignore[attr-defined]
    import anyio

    anyio.from_thread.run  # noqa: B018 - see conftest note on sync fixtures
    client.app.state.container.orders  # noqa: B018

    # Save through the container's own repository so the endpoint sees it.
    import asyncio

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        container.orders.save(order)
    )

    response = client.get(f"/api/v1/orders/{order.id}/receipt")

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("application/json")
    assert response.content == render_receipt(order)


def test_the_receipt_never_carries_the_internal_note(client: TestClient) -> None:
    order = build_order()
    container = client.app.state.container  # type: ignore[attr-defined]
    import asyncio

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        container.orders.save(order)
    )

    response = client.get(f"/api/v1/orders/{order.id}/receipt")

    assert b"internal_note" not in response.content
    assert b"must not be published" not in response.content


def test_an_unknown_order_is_a_problem_details_404(client: TestClient) -> None:
    response = client.get(f"/api/v1/orders/{uuid4()}/receipt")

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json()["type"].endswith("/order_not_found")


def test_a_malformed_identifier_is_a_422(client: TestClient) -> None:
    response = client.get("/api/v1/orders/not-a-uuid/receipt")

    assert response.status_code == 422


def test_an_unreachable_store_is_a_503_with_retry_after(client: TestClient) -> None:
    """503, not 500: the caller did nothing wrong and the same request may
    well succeed later — the same treatment PaymentUnavailableError gets."""
    order = build_order()
    container = client.app.state.container  # type: ignore[attr-defined]
    import asyncio

    asyncio.get_event_loop_policy().new_event_loop().run_until_complete(
        container.orders.save(order)
    )

    class BrokenStore:
        async def get(self, order_id: OrderId) -> bytes | None:
            raise StorageUnavailableError("bucket unreachable")

        async def put(self, order_id: OrderId, content: bytes) -> None:
            raise StorageUnavailableError("bucket unreachable")

    container.receipts = BrokenStore()

    response = client.get(f"/api/v1/orders/{order.id}/receipt")

    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert "Retry-After" in response.headers
    # The adapter's own message must not reach the body: it can carry a
    # bucket name, an endpoint URL and sometimes a credential fragment.
    assert "bucket unreachable" not in response.text


def test_the_documented_schema_matches_what_the_renderer_produces() -> None:
    """The drift gate for this endpoint.

    The 200 response is documented with ReceiptResponse but returned as raw
    bytes, so FastAPI never validates one against the other. Without this
    test the contract could describe a document the renderer stopped
    producing, and every consumer generated from it would be wrong.
    """
    order = build_order()

    document = json.loads(render_receipt(order))

    # Raises if the renderer's output does not satisfy the published schema.
    parsed = ReceiptResponse.model_validate(document)
    assert parsed.order_id == order.id
    assert parsed.total == "21.00"
```

**Note on the awkward `asyncio` calls above:** replace them with whatever the existing `tests/api/` suite already uses to seed the repository — read `tests/api/test_orders.py` first and follow it exactly. If it seeds through the API by POSTing an order, do that instead; it is simpler and avoids event-loop juggling entirely. The assertions are the part that matters here, not the seeding mechanism.

- [ ] **Step 2: Run to verify they fail**

```bash
cd examples/reference-service && uv run pytest tests/api/test_receipts.py -v
```

Expected: FAIL — `ImportError` for `StorageUnavailableError`.

- [ ] **Step 3: Add the error type**

Append to `infrastructure/errors.py`:

```python
class StorageUnavailableError(Exception):
    """The object store could not be reached.

    Not a DomainError, and deliberately so: the caller did nothing wrong,
    and the request may well succeed if repeated later. Like
    PaymentUnavailableError, and unlike its other siblings in this module,
    it DOES get a registered handler in api/errors.py mapping it to 503
    with a Retry-After — a 500 would tell a client "this is broken, do not
    come back", which is the wrong advice for a dependency that is merely
    down right now.

    A MISSING object is not this error. That is a None return from
    ReceiptStore.get, because "nobody has asked for this receipt yet" is
    the ordinary state of most orders, not a failure.
    """
```

- [ ] **Step 4: Map it to 503**

In `api/errors.py`, add the import and a handler modelled on `_payment_unavailable`:

```python
    @app.exception_handler(StorageUnavailableError)
    async def _storage_unavailable(
        request: Request, exc: StorageUnavailableError
    ) -> JSONResponse:
        """503, for the same reason _payment_unavailable returns one.

        `detail` is a fixed string, never `str(exc)`: a botocore error
        carries the endpoint URL, the bucket name and sometimes a fragment
        of the credential that failed, and this response is public. The full
        exception goes to the log instead.
        """
        _logger.warning("request.storage_unavailable", exc_info=exc)
        return _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/storage_unavailable",
                title="Receipt storage unavailable",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="Receipt storage could not be reached. Try again.",
                instance=request.url.path,
            ),
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )
```

`RETRY_AFTER_SECONDS`, the fixed fallback, not `_retry_after_seconds(request)`: that helper reads the payment breaker's cool-down, which has nothing to do with object storage.

- [ ] **Step 5: Add the response schemas**

In `api/v1/schemas.py`:

```python
class ReceiptLine(BaseModel):
    """One line of a receipt. Money fields are STRINGS — see ReceiptResponse."""

    sku: str
    quantity: int
    unit_price: str
    subtotal: str


class ReceiptResponse(BaseModel):
    """The receipt document, as published in the contract.

    This model documents the response; it never serialises one. The endpoint
    returns the exact bytes that were stored, because re-serialising them
    through a model would mean the receipt a client reads is not the object
    that was written. tests/api/test_receipts.py's
    test_the_documented_schema_matches_what_the_renderer_produces is what
    keeps the two in step.

    Every money field is a `str`, not a `Decimal` or a `float`, and that is
    the document's shape rather than a limitation of this model — see
    domain/receipt_render.py for why a financial document must not travel as
    an IEEE 754 double.
    """

    schema_version: int
    order_id: UUID
    customer_id: UUID
    authorisation_id: str | None
    currency: str
    total: str
    lines: list[ReceiptLine]
```

- [ ] **Step 6: Add the container field and dependencies**

In `container.py`, add the import, the field on `Container`, and the default wiring:

```python
    # The in-memory store until Task 10 wires the S3 adapter in. Never None:
    # unlike engine and http_client, there is always SOME store, because the
    # in-memory one needs no configuration.
    receipts: ReceiptStore = field(default_factory=InMemoryReceiptStore)
```

In `api/deps.py`:

```python
def get_receipts(container: ContainerDep) -> ReceiptStore:
    return container.receipts


ReceiptStoreDep = Annotated[ReceiptStore, Depends(get_receipts)]


def get_get_receipt(orders: OrdersDep, receipts: ReceiptStoreDep) -> GetReceipt:
    return GetReceipt(orders, receipts)


GetReceiptDep = Annotated[GetReceipt, Depends(get_get_receipt)]
```

- [ ] **Step 7: Add the route**

In `api/v1/router.py`:

```python
@router.get(
    "/{order_id}/receipt",
    # A raw Response, not a response_model. The endpoint returns the exact
    # bytes that were stored; handing them to a response_model would
    # re-serialise the document and the receipt a client reads would no
    # longer be the object that was written. `responses` below is what
    # publishes the shape instead.
    response_class=Response,
    responses={
        status.HTTP_200_OK: {
            "model": ReceiptResponse,
            "description": "The receipt for this order",
            "content": {RECEIPT_MEDIA_TYPE: {}},
        },
        status.HTTP_404_NOT_FOUND: problem_response("Order not found"),
        status.HTTP_503_SERVICE_UNAVAILABLE: problem_response(
            "Receipt storage unavailable"
        ),
    },
)
async def get_receipt(order_id: UUID, fetch: GetReceiptDep) -> Response:
    """Serve the receipt, rendering and storing it on the first request.

    Deliberately not a redirect to a presigned URL. A presigned URL is
    signed for the storage endpoint's own hostname, which inside compose is
    `minio:9000` — a name that resolves only on the compose network, so the
    link would be dead in a browser on the host. Streaming works identically
    from a laptop, a container and a test.
    """
    content = await fetch(OrderId(order_id))
    return Response(content=content, media_type=RECEIPT_MEDIA_TYPE)
```

- [ ] **Step 8: Run the tests to verify they pass**

```bash
cd examples/reference-service && uv run pytest tests/api/test_receipts.py -v && uv run pytest && uv run mypy
```

Expected: PASS.

- [ ] **Step 9: Regenerate the contract and run every gate**

```bash
cd examples/reference-service && just openapi && git diff --stat openapi.json
```

Expected: a new path `/api/v1/orders/{order_id}/receipt` and two new schemas.

```bash
cd examples/reference-service && just test && just contract-gates
```

Expected: drift passes, Schemathesis conformance passes, and oasdiff reports **no breaking changes** — a new path is purely additive.

If Schemathesis fails on the new operation, read the failure before relaxing anything. A 404 for a random UUID is correct and expected; if the generated checks object to it, the fix is a documented entry in the conformance exceptions list with a reason that survives being read by someone who was not here — never a disabled check.

- [ ] **Step 10: Commit**

```bash
git add examples/reference-service/src examples/reference-service/tests/api/test_receipts.py \
        examples/reference-service/openapi.json
git commit -m "feat(api): serve order receipts from GET /orders/{id}/receipt"
```

---

## Task 9: The S3 adapter

**Files:**
- Create: `examples/reference-service/src/reference_service/infrastructure/storage/__init__.py`
- Create: `examples/reference-service/src/reference_service/infrastructure/storage/client.py`
- Create: `examples/reference-service/src/reference_service/infrastructure/storage/receipt_store.py`

**Interfaces:**
- Consumes: `StorageSettings` (Task 1), `ReceiptStore` (Task 6), `StorageUnavailableError` (Task 8).
- Produces: `build_s3_session(settings) -> aioboto3.Session`, `build_client_config(settings) -> botocore.config.Config`, `S3ReceiptStore(session, config, settings)`, `receipt_key(order_id) -> str`.

There is no unit test in this task. Every behaviour worth asserting — a missing key, a dead endpoint, a real round trip — needs a real S3 implementation to be meaningful, and mocking botocore's client machinery tests the mock. Task 11 covers all of it against MinIO.

- [ ] **Step 1: Write the session builder**

Create `src/reference_service/infrastructure/storage/__init__.py` (empty) and `src/reference_service/infrastructure/storage/client.py`:

```python
"""The S3 session and its client configuration.

Construction only, mirroring infrastructure/db/engine.py and
infrastructure/cache/client.py. The adapter beside it holds only storage
behaviour.

aioboto3's Session does NOT hold a connection: `session.client(...)` is an
async context manager that opens and closes one per use. That shapes
S3ReceiptStore — see its module docstring.
"""

from __future__ import annotations

import aioboto3
from botocore.config import Config

from reference_service.settings import StorageSettings


def build_s3_session(settings: StorageSettings) -> aioboto3.Session:
    """Build the session. Credentials come from settings, never the ambient
    environment.

    Passing them explicitly rather than letting botocore discover them means
    a misconfigured deployment fails with "no credentials configured"
    instead of silently picking up an unrelated instance role and writing
    receipts into somebody else's bucket.
    """
    return aioboto3.Session(
        aws_access_key_id=settings.access_key_id.get_secret_value(),
        aws_secret_access_key=settings.secret_access_key.get_secret_value(),
        region_name=settings.region,
    )


def build_client_config(settings: StorageSettings) -> Config:
    """Deadlines and retry policy for every S3 call.

    botocore's defaults are 60 seconds for both timeouts and a retry mode
    that keeps trying — numbers chosen for batch jobs, not for a request a
    person is waiting on. Left alone, a single unreachable bucket would hold
    an HTTP handler open for minutes.

    `max_attempts=2` is one retry, not none: an S3 call crosses a network
    and a single dropped connection is common enough to be worth one more
    try. More than that belongs behind a circuit breaker, which this
    dependency does not have — and unlike the payment gateway, an
    unavailable store costs one endpoint rather than the ability to take
    money.

    `s3={"addressing_style": "path"}` is what makes MinIO work. The default,
    virtual-host addressing, sends requests to
    `<bucket>.<endpoint>` — a hostname that does not resolve for MinIO,
    which serves buckets as PATHS under one host. Real S3 accepts both, so
    path style is correct for every provider rather than a local-only
    workaround.
    """
    return Config(
        connect_timeout=settings.connect_timeout_seconds,
        read_timeout=settings.read_timeout_seconds,
        retries={"max_attempts": 2, "mode": "standard"},
        s3={"addressing_style": "path"},
    )
```

- [ ] **Step 2: Write the adapter**

Create `src/reference_service/infrastructure/storage/receipt_store.py`:

```python
"""The S3-compatible receipt store.

One adapter for every S3-compatible provider — Amazon S3, MinIO, Cloudflare
R2, Ceph, Backblaze B2 — distinguished only by StorageSettings.endpoint_url
(spec 9.1). There is deliberately no provider branch anywhere below.

A client per operation, not one held for the process's lifetime. That looks
wasteful and is not: aioboto3's `session.client()` is an async context
manager whose exit closes the underlying aiohttp connector, and a client
created once at startup outlives the event loop it was bound to, which
surfaces later as `RuntimeError: Event loop is closed` on the first call
after a reconnect. botocore pools sockets underneath, so the per-call cost
is object construction rather than a new TCP connection. The alternative —
an `AsyncExitStack` held on the container — was considered and rejected: it
buys a small saving and costs a lifetime that has to be correct across
startup, shutdown and every test fixture.
"""

from __future__ import annotations

import aioboto3
import structlog
from botocore.config import Config
from botocore.exceptions import BotoCoreError, ClientError

from reference_service.domain.order import OrderId
from reference_service.infrastructure.errors import StorageUnavailableError
from reference_service.settings import StorageSettings

_logger = structlog.get_logger(__name__)

# The `v1` is a schema generation, matching the cache's key prefix and
# RECEIPT_SCHEMA_VERSION. A receipt's shape can change; bumping this makes
# the next request render the new shape under a new key instead of serving
# a stored document that no longer matches the published contract.
KEY_PREFIX = "receipts/v1/"


def receipt_key(order_id: OrderId) -> str:
    return f"{KEY_PREFIX}{order_id}.json"


class S3ReceiptStore:
    def __init__(
        self,
        session: aioboto3.Session,
        config: Config,
        settings: StorageSettings,
    ) -> None:
        self._session = session
        self._config = config
        self._bucket = settings.bucket
        self._endpoint_url = (
            str(settings.endpoint_url) if settings.endpoint_url is not None else None
        )

    def _client(self):  # type: ignore[no-untyped-def]
        return self._session.client(
            "s3", endpoint_url=self._endpoint_url, config=self._config
        )

    async def get(self, order_id: OrderId) -> bytes | None:
        key = receipt_key(order_id)
        try:
            async with self._client() as s3:
                response = await s3.get_object(Bucket=self._bucket, Key=key)
                body: bytes = await response["Body"].read()
                return body
        except ClientError as exc:
            # A missing object is NOT an error — it is the ordinary state of
            # every order nobody has asked about, and the port says so by
            # returning None. Two distinct codes mean "not there": NoSuchKey
            # for an absent object, and 404 for a HEAD-shaped response.
            # NoSuchBucket deliberately does NOT land here: a missing bucket
            # is a deployment fault, not an empty one, and returning None
            # for it would make every request re-render and silently
            # re-attempt a write that cannot succeed.
            code = exc.response.get("Error", {}).get("Code", "")
            if code in {"NoSuchKey", "404"}:
                return None
            _logger.warning("storage.get_failed", key=key, code=code, exc_info=True)
            raise StorageUnavailableError(
                f"could not read receipt {key}"
            ) from exc
        except BotoCoreError as exc:
            # Connection failures, timeouts, DNS — everything below the HTTP
            # layer. BotoCoreError and ClientError share no base class other
            # than Exception, so both clauses are required; catching only
            # ClientError would let a connection timeout escape as itself and
            # reach the catch-all handler as a 500.
            _logger.warning("storage.get_failed", key=key, exc_info=True)
            raise StorageUnavailableError(f"could not read receipt {key}") from exc

    async def put(self, order_id: OrderId, content: bytes) -> None:
        key = receipt_key(order_id)
        try:
            async with self._client() as s3:
                await s3.put_object(
                    Bucket=self._bucket,
                    Key=key,
                    Body=content,
                    ContentType="application/json",
                )
        except (BotoCoreError, ClientError) as exc:
            _logger.warning("storage.put_failed", key=key, exc_info=True)
            raise StorageUnavailableError(f"could not write receipt {key}") from exc
```

The `StorageUnavailableError` messages carry the KEY, which is derived from an order identifier the caller already knows — never the bucket, the endpoint or a credential. `api/errors.py` does not put the message in the response body regardless, but a message that would be safe there anyway is one less thing to get wrong later.

- [ ] **Step 3: Confirm it type-checks and the layers hold**

```bash
cd examples/reference-service && uv sync && uv run mypy && uv run lint-imports && uv run ruff check .
```

Expected: all pass. `_client()` is deliberately untyped — aioboto3 returns a dynamically generated client class that has no static type, and the suppression is narrower than adding `types-aioboto3` for one method.

- [ ] **Step 4: Commit**

```bash
git add examples/reference-service/src/reference_service/infrastructure/storage
git commit -m "feat(storage): add the s3-compatible receipt store adapter"
```

---

## Task 10: Wire storage in, and add MinIO to compose

**Files:**
- Modify: `examples/reference-service/src/reference_service/container.py`
- Modify: `examples/reference-service/compose.yaml`
- Modify: `examples/reference-service/justfile`
- Test: `examples/reference-service/tests/unit/test_container.py`

**Interfaces:**
- Consumes: `build_s3_session`, `build_client_config`, `S3ReceiptStore` (Task 9); `register_informational` (Task 2).
- Produces: `Container.receipts` populated with `S3ReceiptStore` when storage settings exist; a `storage` entry under `/readyz`'s `dependencies`.

- [ ] **Step 1: Write the failing container tests**

Add to `tests/unit/test_container.py`:

```python
def test_no_storage_settings_means_the_in_memory_store() -> None:
    container = build_container(Settings(_env_file=None))

    assert isinstance(container.receipts, InMemoryReceiptStore)
    assert "storage" not in container.readiness._informational


def test_storage_settings_select_the_s3_store_and_register_a_report(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("APP_STORAGE__BUCKET", "receipts")
    monkeypatch.setenv("APP_STORAGE__ENDPOINT_URL", "http://localhost:9000")
    monkeypatch.setenv("APP_STORAGE__ACCESS_KEY_ID", "key")
    monkeypatch.setenv("APP_STORAGE__SECRET_ACCESS_KEY", "secret")
    container = build_container(Settings(_env_file=None))

    assert isinstance(container.receipts, S3ReceiptStore)
    # Reported, never gating: losing the store breaks ONE endpoint, so
    # taking the pod out of rotation would cost far more than it saves.
    assert "storage" in container.readiness._informational
    assert "storage" not in container.readiness._gating
```

- [ ] **Step 2: Run to verify they fail**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_container.py -v -k storage
```

Expected: FAIL — `receipts` is always the in-memory store.

- [ ] **Step 3: Wire it into the container**

In `build_container`, after the cache block:

```python
    receipts: ReceiptStore = InMemoryReceiptStore()
    if settings.storage is not None:
        storage_settings = settings.storage
        receipts = S3ReceiptStore(
            build_s3_session(storage_settings),
            build_client_config(storage_settings),
            storage_settings,
        )
```

Pass `receipts=receipts` to the `Container(...)` construction, and register the report after the cache's:

```python
    if settings.storage is not None:
        store = receipts
        bucket = settings.storage.bucket

        async def storage_is_reachable() -> None:
            # head_bucket, not a get or a list: it is the cheapest call that
            # proves the endpoint answers, the credentials are accepted AND
            # the bucket exists — which is the whole question. Listing keys
            # would also work and gets slower as the bucket fills.
            async with store._client() as s3:  # noqa: SLF001 - see below
                await s3.head_bucket(Bucket=bucket)

        container.readiness.register_informational("storage", storage_is_reachable)
```

`_client()` is private and SLF001 is suppressed deliberately: the alternative is a public `ping()` on the port, which would put a health-check concern into the domain's `ReceiptStore` Protocol where it does not belong. The suppression keeps the leak inside the composition root, which already knows exactly which adapter it built.

There is deliberately no `close` for storage in `close_container`: `S3ReceiptStore` opens and closes a client per call and holds no pooled connection to release. See its module docstring.

- [ ] **Step 4: Run the tests to verify they pass**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_container.py -v && uv run mypy && uv run ruff check .
```

Expected: PASS.

- [ ] **Step 5: Add MinIO to compose**

```yaml
  # The object store. MinIO speaks the S3 API, so the same adapter that runs
  # here runs against Amazon S3 in production with only endpoint_url
  # changing (spec 9.1).
  minio:
    image: minio/minio:RELEASE.2025-09-07T16-13-09Z
    command: ["server", "/data", "--console-address", ":9001"]
    environment:
      MINIO_ROOT_USER: minioadmin
      MINIO_ROOT_PASSWORD: minioadmin
    ports:
      # 9000 is the S3 API, published so `just test-record`-style host tools
      # and the AWS CLI can reach it. The application inside compose does NOT
      # use this — it connects over the compose network to `minio:9000`.
      - "9000:9000"
      # 9001 is the web console: `just minio-console`.
      - "9001:9001"
    healthcheck:
      # MinIO's own documented healthcheck. `mc` ships inside the image and
      # resolves the `local` alias itself, so this needs no curl (the image
      # has none) and no credentials on the command line.
      test: ["CMD", "mc", "ready", "local"]
      interval: 5s
      timeout: 3s
      retries: 15
    volumes:
      - minio-data:/data

  # One-shot bucket creation. MinIO does not create a bucket on demand and
  # the application deliberately does not create its own — doing so would
  # need CreateBucket permission in production, where the bucket is
  # provisioned by whoever owns the account, not by the service.
  #
  # The same shape as the `migrate` service above: a container that runs
  # once, exits 0, and that `app` waits on with
  # service_completed_successfully.
  minio-bootstrap:
    image: minio/mc:RELEASE.2025-08-13T08-35-41Z
    depends_on:
      minio:
        condition: service_healthy
    entrypoint: ["sh", "-c"]
    # --ignore-existing makes this idempotent, so a second `just up` is not
    # an error. Credentials match the MINIO_ROOT_* pair above; they are
    # local-only values and never leave this file.
    command: >
      "mc alias set local http://minio:9000 minioadmin minioadmin &&
       mc mb --ignore-existing local/receipts"
```

Add to `app`'s `depends_on`:

```yaml
      # The bucket must exist before the first receipt is requested. Same
      # arrangement as `migrate`: wait for the one-shot container to exit 0.
      minio-bootstrap:
        condition: service_completed_successfully
```

Add to `app`'s `environment`:

```yaml
      # `minio` is the compose service name above. endpoint_url is the whole
      # of "one adapter for every S3-compatible provider": unset it and the
      # same code talks to Amazon S3.
      APP_STORAGE__BUCKET: receipts
      APP_STORAGE__ENDPOINT_URL: http://minio:9000
      APP_STORAGE__ACCESS_KEY_ID: minioadmin
      APP_STORAGE__SECRET_ACCESS_KEY: minioadmin
```

And add the volume beside `postgres-data`:

```yaml
volumes:
  postgres-data:
  minio-data:
```

- [ ] **Step 6: Add the console recipe**

```just
# The MinIO web console, for looking at what the receipt store actually
# holds. Log in with minioadmin / minioadmin — local-only credentials from
# compose.yaml.
minio-console:
    @echo "http://localhost:9001 — minioadmin / minioadmin"
    @open http://localhost:9001 2>/dev/null || true
```

- [ ] **Step 7: Verify the whole stack by hand**

```bash
cd examples/reference-service && just up
```

In a second terminal:

```bash
curl -s localhost:8000/readyz | python3 -m json.tool
```

Expected: `dependencies` shows both `cache: ok` and `storage: ok`.

```bash
cd examples/reference-service && ORDER=$(curl -s -X POST localhost:8000/api/v1/orders -H 'content-type: application/json' -d '{"customer_id":"11111111-1111-1111-1111-111111111111","lines":[{"sku":"SKU-1","quantity":2,"unit_amount":"10.50","currency":"EUR"}]}' | python3 -c 'import sys,json; print(json.load(sys.stdin)["id"])') && curl -s "localhost:8000/api/v1/orders/$ORDER/receipt" | python3 -m json.tool
```

Expected: a receipt document with `schema_version`, the totals as strings, and **no** `internal_note`.

Now prove it was actually stored, and that the second read serves the stored object:

```bash
cd examples/reference-service && docker compose run --rm --entrypoint sh minio-bootstrap -c "mc alias set local http://minio:9000 minioadmin minioadmin >/dev/null && mc ls --recursive local/receipts"
```

Expected: one object, `receipts/v1/<order id>.json`.

Finally, confirm an unavailable store degrades to 503 and does not take the service down:

```bash
cd examples/reference-service && docker compose stop minio && curl -s -o /dev/null -w 'receipt:%{http_code}\n' "localhost:8000/api/v1/orders/$ORDER/receipt" && curl -s -o /dev/null -w 'order:%{http_code}\n' "localhost:8000/api/v1/orders/$ORDER" && curl -s -o /dev/null -w 'readyz:%{http_code}\n' localhost:8000/readyz
```

Expected: `receipt:503`, `order:200`, `readyz:200`. The order endpoint still working with storage down is the point of keeping the store out of the order path; `/readyz` still returning 200 is the point of Task 2.

```bash
cd examples/reference-service && docker compose start minio && just down
```

- [ ] **Step 8: Commit**

```bash
git add examples/reference-service/src/reference_service/container.py \
        examples/reference-service/compose.yaml examples/reference-service/justfile \
        examples/reference-service/tests/unit/test_container.py
git commit -m "feat(storage): wire the s3 receipt store into the container and compose"
```

---

## Task 11: MinIO integration tests

**Files:**
- Modify: `examples/reference-service/tests/integration/conftest.py`
- Test: `examples/reference-service/tests/integration/test_receipt_store.py` (create)

**Interfaces:**
- Consumes: `S3ReceiptStore`, `build_s3_session`, `build_client_config`, `receipt_key` (Task 9); `StorageSettings` (Task 1).
- Produces: session-scoped `minio_container` and `storage_settings` fixtures, a function-scoped `receipt_store` fixture, and `MINIO_IMAGE`.

- [ ] **Step 1: Add the container fixtures**

In `tests/integration/conftest.py`:

```python
from testcontainers.community.minio import MinioContainer

# Pinned to the same tag compose uses. MinioContainer's own default is
# minio/minio:RELEASE.2022-12-02T19-19-22Z — nearly four years old — so this
# is never left to the default.
MINIO_IMAGE = "minio/minio:RELEASE.2025-09-07T16-13-09Z"
MINIO_ACCESS_KEY = "minioadmin"
MINIO_SECRET_KEY = "minioadmin"
RECEIPTS_BUCKET = "receipts"


@pytest.fixture(scope="session")
def minio_container() -> Iterator[MinioContainer]:
    """One MinIO for the whole session, with the bucket created once.

    MinioContainer's constructor sets the LEGACY credential variables
    (MINIO_ACCESS_KEY / MINIO_SECRET_KEY). Modern MinIO releases read
    MINIO_ROOT_USER / MINIO_ROOT_PASSWORD, and a release that ignores the
    legacy pair comes up with its built-in minioadmin/minioadmin instead —
    so every test using the requested credentials would fail to
    authenticate. Both pairs are set below, to the same values, so this
    works whichever the pinned release honours.
    """
    container = (
        MinioContainer(
            image=MINIO_IMAGE,
            access_key=MINIO_ACCESS_KEY,
            secret_key=MINIO_SECRET_KEY,
        )
        .with_env("MINIO_ROOT_USER", MINIO_ACCESS_KEY)
        .with_env("MINIO_ROOT_PASSWORD", MINIO_SECRET_KEY)
    )
    with container as running:
        # The bucket compose's minio-bootstrap service creates. The
        # application deliberately never creates its own — see that service's
        # comment — so the test environment has to.
        running.get_client().make_bucket(RECEIPTS_BUCKET)
        yield running


@pytest.fixture(scope="session")
def storage_settings(minio_container: MinioContainer) -> StorageSettings:
    config = minio_container.get_config()
    # get_config()["endpoint"] is "host:port" with NO scheme, and botocore's
    # endpoint_url requires one. Without this prefix every call fails with an
    # unhelpful InvalidURL.
    return StorageSettings(
        bucket=RECEIPTS_BUCKET,
        endpoint_url=f"http://{config['endpoint']}",  # type: ignore[arg-type]
        access_key_id=SecretStr(MINIO_ACCESS_KEY),
        secret_access_key=SecretStr(MINIO_SECRET_KEY),
    )


@pytest.fixture
def receipt_store(storage_settings: StorageSettings) -> S3ReceiptStore:
    return S3ReceiptStore(
        build_s3_session(storage_settings),
        build_client_config(storage_settings),
        storage_settings,
    )
```

Add `SecretStr`, `StorageSettings`, `S3ReceiptStore`, `build_s3_session` and `build_client_config` to the module's imports.

- [ ] **Step 2: Write the failing tests**

Create `tests/integration/test_receipt_store.py`:

```python
"""The S3 receipt store against a real MinIO.

This module carries its own `pytestmark` with `loop_scope="session"`, per
the rule in this directory's conftest.py.
"""

from __future__ import annotations

from uuid import uuid4

import pytest

from reference_service.domain.order import OrderId
from reference_service.infrastructure.errors import StorageUnavailableError
from reference_service.infrastructure.storage.receipt_store import (
    S3ReceiptStore,
    receipt_key,
)
from reference_service.settings import StorageSettings

pytestmark = pytest.mark.asyncio(loop_scope="session")


async def test_a_receipt_round_trips(receipt_store: S3ReceiptStore) -> None:
    order_id = OrderId(uuid4())
    content = b'{"schema_version":1,"order_id":"x"}'

    await receipt_store.put(order_id, content)

    assert await receipt_store.get(order_id) == content


async def test_an_absent_object_is_none_not_an_error(
    receipt_store: S3ReceiptStore,
) -> None:
    """The distinction the port is built around: None means 'render it',
    an error means 'come back later'. Collapsing them would make an outage
    look like an empty bucket."""
    assert await receipt_store.get(OrderId(uuid4())) is None


async def test_a_put_replaces_an_existing_object(
    receipt_store: S3ReceiptStore,
) -> None:
    order_id = OrderId(uuid4())
    await receipt_store.put(order_id, b"first")

    await receipt_store.put(order_id, b"second")

    assert await receipt_store.get(order_id) == b"second"


async def test_bytes_come_back_byte_identical(
    receipt_store: S3ReceiptStore,
) -> None:
    """A receipt is served as the exact object that was stored. Any
    transcoding — a content-encoding negotiated on the way out, a stray
    decode to str — would show up here."""
    order_id = OrderId(uuid4())
    content = "receipt for € 21,00 — naïve".encode()

    await receipt_store.put(order_id, content)

    assert await receipt_store.get(order_id) == content


async def test_the_key_layout_is_what_the_adapter_documents(
    receipt_store: S3ReceiptStore, storage_settings: StorageSettings,
    minio_container: object,
) -> None:
    """Pins the on-disk layout. Objects outlive deployments, so a silent
    change to the key scheme orphans every receipt already written."""
    order_id = OrderId(uuid4())
    await receipt_store.put(order_id, b"{}")

    from testcontainers.community.minio import MinioContainer

    assert isinstance(minio_container, MinioContainer)
    names = [
        obj.object_name
        for obj in minio_container.get_client().list_objects(
            storage_settings.bucket, recursive=True
        )
    ]

    assert receipt_key(order_id) in names
    assert receipt_key(order_id).startswith("receipts/v1/")


async def test_a_missing_bucket_is_an_error_not_an_empty_result(
    storage_settings: StorageSettings,
) -> None:
    """NoSuchBucket must NOT be swallowed as None. If it were, every request
    would re-render and re-attempt a write that cannot succeed, and the
    service would look healthy while storing nothing."""
    from reference_service.infrastructure.storage.client import (
        build_client_config,
        build_s3_session,
    )

    wrong = storage_settings.model_copy(update={"bucket": "does-not-exist"})
    store = S3ReceiptStore(
        build_s3_session(wrong), build_client_config(wrong), wrong
    )

    with pytest.raises(StorageUnavailableError):
        await store.get(OrderId(uuid4()))


async def test_an_unreachable_endpoint_raises_storage_unavailable(
    storage_settings: StorageSettings,
) -> None:
    """Port 1 is reserved and never has a listener, so this exercises the
    BotoCoreError branch — connection failures, which share no base class
    with ClientError and would otherwise escape as a 500."""
    from reference_service.infrastructure.storage.client import (
        build_client_config,
        build_s3_session,
    )

    dead = storage_settings.model_copy(
        update={"endpoint_url": "http://127.0.0.1:1"}
    )
    store = S3ReceiptStore(build_s3_session(dead), build_client_config(dead), dead)

    with pytest.raises(StorageUnavailableError):
        await store.get(OrderId(uuid4()))

    with pytest.raises(StorageUnavailableError):
        await store.put(OrderId(uuid4()), b"{}")
```

`model_copy` on a frozen model returns a new instance rather than mutating, so the shared session-scoped `storage_settings` is untouched by the two failure tests.

- [ ] **Step 3: Run the tests**

```bash
cd examples/reference-service && uv run pytest -m integration -k receipt_store -v
```

Expected: PASS, all seven. The first run pulls the MinIO image.

If the credential tests fail with an authentication error, Verified Fact 3 is the cause: the pinned release honours neither credential pair as expected. Confirm with `docker logs` on the container and adjust which pair is set — do not work around it by falling back to the built-in defaults, because the fixture would then be testing different credentials from the ones compose uses.

- [ ] **Step 4: Run the whole container tier**

```bash
cd examples/reference-service && just test-integration
```

Expected: PASS — PostgreSQL, Redis and MinIO tests together. This is the first run with three containers, so watch for port or resource contention.

- [ ] **Step 5: Commit**

```bash
git add examples/reference-service/tests/integration/conftest.py \
        examples/reference-service/tests/integration/test_receipt_store.py
git commit -m "test(storage): exercise the receipt store against a real minio"
```

---

## Task 12: Instrumentation

This closes the row the M2 plan deferred: "Redis and S3 instrumentation | M4". It begins with a measurement, because Verified Fact 11 is genuinely unresolved.

**Files:**
- Modify: `examples/reference-service/src/reference_service/observability/otel.py`
- Modify: `examples/reference-service/src/reference_service/main.py`
- Modify: `examples/reference-service/ops/grafana/dashboards/service-health.json`
- Test: `examples/reference-service/tests/unit/test_otel.py`
- Test: `examples/reference-service/tests/integration/test_db_instrumentation.py` (extend, or a sibling module)

**Interfaces:**
- Consumes: `OtelRuntime`, `instrument_database`'s shape (existing); `Container.redis` (Task 4); `S3ReceiptStore` (Task 9).
- Produces: `instrument_redis(runtime)` and `instrument_botocore(runtime)`.

- [ ] **Step 1: Measure whether botocore instrumentation sees aioboto3 at all**

Do this before writing anything. `opentelemetry-instrumentation-botocore` patches `botocore`; `aioboto3` runs on `aiobotocore`, which replaces parts of that machinery. Write a throwaway script and run it against a MinIO container:

```bash
cd examples/reference-service && uv run python - <<'PY'
import asyncio
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import SimpleSpanProcessor, ConsoleSpanExporter
from opentelemetry.instrumentation.botocore import BotocoreInstrumentor

provider = TracerProvider()
provider.add_span_processor(SimpleSpanProcessor(ConsoleSpanExporter()))
trace.set_tracer_provider(provider)
BotocoreInstrumentor().instrument()

import aioboto3
from botocore.config import Config

async def main() -> None:
    session = aioboto3.Session(
        aws_access_key_id="minioadmin", aws_secret_access_key="minioadmin",
        region_name="us-east-1",
    )
    config = Config(s3={"addressing_style": "path"})
    async with session.client(
        "s3", endpoint_url="http://localhost:9000", config=config
    ) as s3:
        await s3.list_buckets()

asyncio.run(main())
PY
```

Start MinIO first with `docker compose up -d minio`. If a span named something like `S3.ListBuckets` is printed, the instrumentation works and Step 3 is straightforward. If nothing is printed, record that in this plan's Verified Facts as fact 11 resolved, skip the botocore half of Step 3, and add a row to the "deliberately does not include" table naming the reason. **Do not let this block the milestone** — storage works with or without spans, and shipping an adapter whose spans are silently absent is worse than shipping one that is honestly documented as un-instrumented.

- [ ] **Step 2: Write the failing tests**

Add to `tests/unit/test_otel.py`, following the existing tests' shape:

```python
def test_redis_is_not_instrumented_when_telemetry_is_off() -> None:
    """The default path. With APP_OTEL__ENABLED false the process must
    import no exporter, open no socket and start no background task — and
    that now covers the two new instrumentations."""
    settings = Settings(_env_file=None)
    assert settings.otel.enabled is False
    assert configure_otel(settings, "0.0.0") is None
```

And a test that the instrumentation is idempotent, which matters because these instrumentors are global rather than per-client:

```python
def test_instrumenting_redis_twice_does_not_raise() -> None:
    """RedisInstrumentor patches the library GLOBALLY, unlike
    HTTPXClientInstrumentor.instrument_client which attaches per client. A
    second call must be a no-op rather than a double-patch — the test suite
    builds many apps in one process, and each one runs the lifespan."""
    runtime = _build_runtime_for_test()
    instrument_redis(runtime)
    instrument_redis(runtime)
```

- [ ] **Step 3: Add the instrumentation functions**

In `observability/otel.py`, beside `instrument_database`:

```python
def instrument_redis(runtime: OtelRuntime) -> None:
    """Spans for every Redis command.

    A GLOBAL instrumentor, unlike instrument_http_client's per-client
    attachment: redis-py has no per-client hook, so this patches the
    library. `is_instrumented_by_opentelemetry` guards the second call —
    the test suite builds many apps in one process and each runs the
    lifespan, and instrumenting twice wraps the wrapper.

    Worth having despite the cache being optional: the span is how you find
    out that a "fast" cache read is actually costing 40ms, which is the
    exact failure a fail-open cache hides from every other signal — the
    request still succeeds, so no error rate moves.
    """
    instrumentor = RedisInstrumentor()
    if instrumentor.is_instrumented_by_opentelemetry:
        return
    instrumentor.instrument(tracer_provider=runtime.tracer_provider)


def instrument_botocore(runtime: OtelRuntime) -> None:
    """Spans for S3 calls. Same global-instrumentor caveat as above."""
    instrumentor = BotocoreInstrumentor()
    if instrumentor.is_instrumented_by_opentelemetry:
        return
    instrumentor.instrument(tracer_provider=runtime.tracer_provider)
```

Add the two imports beside the existing instrumentation imports at the top of the module.

- [ ] **Step 4: Call them from the lifespan**

In `main.py`, wherever `instrument_database` and `instrument_http_client` are called, add the two new calls under the same "telemetry enabled" condition. They are global rather than per-object, so they take only the runtime — call them once, unconditionally on the runtime being present, rather than gating on whether a cache or a store happens to be configured. Instrumenting a library nothing uses costs nothing; forgetting to instrument one that is used costs a blind spot.

- [ ] **Step 5: Run the tests**

```bash
cd examples/reference-service && uv run pytest tests/unit/test_otel.py tests/unit/test_otel_logs.py -v && uv run pytest
```

Expected: PASS. Watch specifically for a `DeprecationWarning` from either instrumentor — `filterwarnings = ["error"]` turns one into a failure, and that is the mechanism that caught the SDK's deprecated `LoggingHandler` in M2.

- [ ] **Step 6: Verify a real span end to end**

```bash
cd examples/reference-service && just o11y
```

Place an order and read it twice, then read its receipt. In Grafana at `http://localhost:3000`, open Explore, pick Tempo, and search for traces on the receipt request.

Expected: the trace shows the HTTP server span, a SQLAlchemy span for the order lookup on the first read, a Redis span on the second, and — if Step 1 showed spans — an S3 span for the receipt write.

- [ ] **Step 7: Add the Redis saturation panel**

Spec 7.4 names "database pool usage, Redis pool usage, event loop lag" as the saturation row of the service-health dashboard. The Redis panel is now possible.

Edit `ops/grafana/dashboards/service-health.json`, copying the existing database pool panel and pointing it at the Redis connection-pool metric the instrumentation emits. Confirm the metric name first rather than guessing it:

```bash
curl -s 'http://localhost:9090/api/v1/label/__name__/values' | python3 -c "
import sys, json
names = json.load(sys.stdin)['data']
print([n for n in names if 'redis' in n.lower() or 'pool' in n.lower()])
"
```

Use a name that this command actually printed. If the instrumentation emits no pool metric at all, add a Redis *latency* panel from the span metrics instead and note the substitution in a comment — a panel showing a metric that does not exist is worse than no panel, because it reads as "zero saturation" rather than "no data".

```bash
cd examples/reference-service && uv run pytest tests/unit/test_dashboards.py -v
```

Expected: PASS. That test parses the dashboard JSON, so it catches a malformed edit.

```bash
cd examples/reference-service && just o11y-down
```

- [ ] **Step 8: Commit**

```bash
git add examples/reference-service/src/reference_service/observability/otel.py \
        examples/reference-service/src/reference_service/main.py \
        examples/reference-service/ops/grafana/dashboards/service-health.json \
        examples/reference-service/tests/unit/test_otel.py
git commit -m "feat(observability): instrument redis and s3, and chart cache saturation"
```

---

## Task 13: Documentation, and the full gate run

The milestone is not finished when the code works. Every page this changes has to say what is now true.

**Files:**
- Modify: `docs/roadmap.md`
- Modify: `docs/reference/configuration.md`
- Modify: `docs/reference/observability.md`
- Modify: `docs/explanation/architecture.md`
- Modify: `docs/explanation/layers.md`
- Modify: `docs/guides/add-a-backend.md`
- Modify: `docs/reference/http-api.md`
- Modify: `docs/reference/commands.md`
- Modify: `examples/reference-service/README.md`
- Modify: `mkdocs.yml` (only if a page is added)

- [ ] **Step 1: Mark M4 done on the roadmap**

In `docs/roadmap.md`, change the M4 row's State to **Done**, and update the opening line — currently "**M0, M1, M2 and M3 are done.**" — to include M4.

The M4 row's "What exists at the end" should describe what was actually built, which is more than the original row promised:

```markdown
| **M4** | Cache and object storage | **Done** | A fail-open Redis cache as a decorator over the order repository, an S3-compatible receipt store over aioboto3, Redis and MinIO in compose, a two-tier `/readyz` that reports optional dependencies without gating on them, `GET /orders/{id}/receipt`, and integration tests against real Redis and MinIO containers. |
```

- [ ] **Step 2: Document the new settings**

In `docs/reference/configuration.md`, add rows for every field of `CacheSettings` and `StorageSettings`, matching the existing table's format: variable name, type, default, and what it does. Include the two facts a reader most needs:

- absent settings are a supported configuration, not a broken one — the service runs without either dependency
- `APP_STORAGE__ENDPOINT_URL` is left unset for real Amazon S3 and set for everything else

- [ ] **Step 3: Document the readiness change**

`/readyz`'s response gained a `dependencies` object. Wherever the health endpoints are described — `docs/reference/http-api.md` and `docs/reference/observability.md` — explain the two tiers and, most importantly, *why* a cache failure does not make the pod unready. That reasoning is the interesting part of this milestone and it will not survive in anyone's head.

- [ ] **Step 4: Describe the two adapters**

In `docs/explanation/architecture.md` and `docs/explanation/layers.md`, add the cache and the store to the layer descriptions. The caching decorator deserves a paragraph of its own: it is the clearest demonstration in the codebase of what a port buys, because the cache is added and removed by changing `container.py` alone.

In `docs/guides/add-a-backend.md`, the new adapters are two more worked examples of the pattern the guide teaches. Reference them.

- [ ] **Step 5: Document the new commands**

`docs/reference/commands.md` needs `just redis-cli` and `just minio-console`.

- [ ] **Step 6: Run every gate**

```bash
cd examples/reference-service && just check-all
```

Expected: PASS. This runs lint, mypy, import contracts, the unit and api tiers, pre-commit, the container tier, all five schema gates, the SLO gates and both contract gates.

Read the output rather than the exit code. A green run here is the claim that M4 is done, and it is the last chance to catch a gate that was quietly weakened rather than satisfied.

- [ ] **Step 7: Check the mutation score on the new logic**

```bash
cd examples/reference-service && just mutants-changed
```

`domain/receipt_render.py` and `services/receipt.py` are both inside mutmut's `only_mutate` scope. Read the survivors rather than the percentage: a surviving mutant in `render_receipt` means a field the tests never actually check, which for a financial document is worth knowing.

The cache decorator is in `infrastructure/` and is deliberately outside the scope — mutating adapters produces noise about error paths, as the M3 plan records.

- [ ] **Step 8: Commit and open the pull request**

```bash
git add docs examples/reference-service/README.md
git commit -m "docs: describe the cache, the receipt store and the two readiness tiers"
```

Open the pull request with a Conventional Commits title, because a squash merge makes that title the commit message on `main`:

```
feat(reference-service): add the redis cache and the s3 receipt store
```

Link it to a GitHub issue, creating one first if none exists, and verify the link actually registered rather than trusting the text.

---

## Self-Review

Run against the spec after the plan was complete.

**Spec coverage.** Every M4 commitment maps to a task:

| Spec requirement | Task |
|---|---|
| Redis adapter (section 13, M4 row) | 3, 4 |
| S3 adapter over aioboto3 (13, M4 row; 9.1) | 9, 10 |
| MinIO in compose (13, M4 row) | 10 |
| Integration tests for both (8.1; 13, M4 row) | 5, 11 |
| `infrastructure/cache/` and `infrastructure/storage/` in the layout (section 6 tree) | 3, 9 |
| Redis instrumentation (7.2) | 12 |
| Redis pool saturation panel (7.4) | 12, step 7 |
| `/readyz` checks database, cache and storage (12.1 item 1) | 2, 4, 10 — reported for all three, gating on the database only. The deviation and its reasoning are recorded in Verified Fact 8 |
| One adapter for every S3-compatible provider via `endpoint_url` (9.1) | 9 |
| Secrets never reach a log, traceback or response (5.1) | 1 (SecretStr), 8 (fixed `detail` strings), 9 (key-only error messages) |

**Placeholder scan.** No "TBD", no "add error handling", no "similar to Task N". Task 12's step 1 is a measurement whose outcome branches the work, and both branches are written out.

**Type consistency.** Checked across tasks: `ReceiptStore.get/put`, `render_receipt`, `CachedOrderRepository.__init__`, `build_redis_client`, `build_s3_session`, `build_client_config`, `S3ReceiptStore.__init__`, `GetReceipt.__call__`, `ReadinessReport.gating/informational/healthy`, `register_informational`, `receipt_key`, `CACHE_KEY_PREFIX`, `KEY_PREFIX`, `RECEIPT_MEDIA_TYPE`, `RECEIPT_SCHEMA_VERSION`. Names and signatures agree everywhere they are used.

**Two known soft spots**, both deliberate and both flagged in place rather than hidden:

1. **Task 8's test seeding.** The three tests that need an order in the repository are written with awkward event-loop juggling, and the step says so and tells the implementer to follow `tests/api/test_orders.py` instead. The assertions are the valuable part.
2. **Task 12's botocore instrumentation.** Verified Fact 11 is unresolved on purpose, and Task 12 opens by measuring it rather than assuming. Both outcomes have a written path, and neither blocks the milestone.
