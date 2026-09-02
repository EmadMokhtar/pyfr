# PyFr M2 — Observability Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give `examples/reference-service/` OpenTelemetry traces, metrics and opt-in log export that follow the *stable* semantic conventions, a local Grafana LGTM stack behind a compose profile, three provisioned dashboards, and multi-window multi-burn-rate service level objective alerts — so a developer runs one command and sees their own request as a trace, a metric and a log line that all point at each other.

**Architecture:** Observability is a *decorator on the edges*, never a layer the business logic knows about. `domain/` and `services/` gain no imports; the import-linter contracts grow `opentelemetry` to the forbidden list so this stays true. Everything OpenTelemetry lives under `observability/`, is constructed once in `create_app`/`lifespan`, and is entirely absent when `APP_OTEL__ENABLED` is false — which is the default, so the M0/M1 no-dependency path keeps working unchanged. The dashboards and alert rules are version-controlled files mounted into a single `grafana/otel-lgtm` container; the same JSON loads into a production Grafana.

**Tech Stack:** OpenTelemetry Python SDK 1.44.0, instrumentation packages 0.65b0 (FastAPI, SQLAlchemy, system-metrics), OTLP over gRPC, `grafana/otel-lgtm:0.11.11` (Grafana 12.2.0, Prometheus, Tempo, Loki, an OpenTelemetry collector), `promtool` (shipped inside that image).

**Spec:** `docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md` — section 7 in full (7.1 scope boundary, 7.2 instrumentation, 7.3 local stack, 7.4 dashboards, 7.5 SLOs and alerting, 7.6 structured logging), decisions D4 and D15, and section 3.4's note that dashboard JSON is copied verbatim at templatisation time.

**Predecessor:** `docs/superpowers/plans/2026-09-01-pyfr-m1-persistence.md`. M1 is merged and green.

---

## Global Constraints

Every task's requirements implicitly include these. The first fourteen are inherited from M0 and M1 unchanged; the rest are new in M2.

- **Python `>=3.13`.** `.python-version` contains `3.13`.
- **uv for everything Python.** `uv sync`, `uv run`, `uv lock`. No `pip`, no `requirements.txt`, no `pipx`, no manually activated virtual environment.
- **Plain Python only.** M2 is still Phase A. No Jinja, no cookiecutter variables, no `{{ }}` templating in any Python, YAML or compose file. Templatisation is M7.
- **Package name is `reference_service`;** distribution name is `reference-service`. All work happens under `examples/reference-service/`.
- **The domain layer imports nothing but `pydantic`.** Not FastAPI, not the service layer, not infrastructure, not SQLAlchemy, not asyncpg — and, new in M2, not `opentelemetry`.
- **The domain layer never knows an HTTP status code exists.**
- **mypy is strict on `domain/` and `services/`,** lenient elsewhere.
- **All logging goes through structlog.**
- **`/healthz` never checks a dependency.** Only `/readyz` does.
- **Line length 88.**
- **Conventional Commits** for every commit: `<type>[scope]: <description>`, imperative, lowercase, no trailing period.
- **Unit tests never need Docker.** `just test` runs `tests/unit` and `tests/api` only. Anything requiring a container lives in `tests/integration` and runs under `just test-integration`.
- **`filterwarnings = ["error"]` stays.** Any new dependency emitting a `DeprecationWarning` on import fails the suite. This bites in M2 — see the note on `InMemoryLogExporter` in Verified Facts.
- **Pinned images.** `grafana/otel-lgtm:0.11.11`, written in exactly one place and referenced from there.
- **Telemetry is off by default.** `APP_OTEL__ENABLED=false` is the default. With it false the process must import no exporter, open no socket, and start no background task. The entire M0/M1 test suite must keep passing untouched.
- **Standard output stays the source of truth for logs (D15).** OTLP log export is additive and opt-in, never a replacement.
- **The stable HTTP semantic conventions, not the legacy ones.** Metrics must be named `http.server.request.duration` in *seconds*, with attributes `http.route`, `http.request.method`, `http.response.status_code`. See Verified Facts item 2 — this does not happen by default.
- **One source of truth for the SLO numbers.** The latency threshold appears in Python (as a histogram bucket boundary) and in PromQL (as an `le` label). A unit test asserts they agree; nobody edits one without the other.

---

## What M2 deliberately does not include

| Left out | Owner |
|---|---|
| `httpx` / outbound HTTP client instrumentation | M3 — the shared outbound client does not exist yet, so there is nothing to instrument |
| Redis and S3 instrumentation | M4 — same reason |
| `openapi.json` drift gate, Schemathesis, mutmut | M3 |
| Log redaction (`redact_sensitive_fields` in spec 7.6's processor list) | M6, with the rest of the supply-chain and hardening work |
| `.github/workflows/*` — every gate runs from `just`, not from CI | M5 (release), M7 (template CI) |
| `docs/how-to/*` runbooks for reading a trace, and the generated configuration reference | M5 — the docs milestone. M2 still updates the four reference pages it changes the behaviour of |
| A production observability platform, alertmanager routing, paging integrations | Never — spec 7.1. The template emits standard telemetry and stops |
| Kubernetes manifests, ServiceMonitor resources | M9 |
| Making the SLO target and latency threshold cookiecutter prompts | M7. In M2 they are named constants in one module, which is exactly what M7 will replace with a variable |

---

## Verified Facts

Every item below was confirmed by running the real software while this plan was written, not read from documentation. They are the traps this milestone contains. **Read this section before Task 1.**

**1. Pinned versions that resolve today.**
`opentelemetry-api`, `opentelemetry-sdk`, `opentelemetry-exporter-otlp-proto-grpc` are all `1.44.0`. The instrumentation packages version separately: `opentelemetry-instrumentation-fastapi`, `-sqlalchemy` and `-system-metrics` are all `0.65b0`. The `b` is not a typo — the instrumentation line is beta-versioned and always will be.

**2. The stable HTTP semantic conventions require an explicit opt-in, and the opt-in latches.**
Out of the box `opentelemetry-instrumentation-fastapi` emits the *legacy* convention:

```
http.server.duration          unit: ms   attrs: http.method, http.status_code, http.target
```

With `OTEL_SEMCONV_STABILITY_OPT_IN=http` set, it emits what spec 7.2 asks for:

```
http.server.request.duration  unit: s    attrs: http.route, http.request.method, http.response.status_code
```

The variable is read at the *first* `instrument*()` call in the process and then cached forever in a module-level dict. Setting it after that first call changes nothing — confirmed: a second `instrument_app()` in the same process still produced `http.server.duration`. So the opt-in must be applied before **any** instrumentation runs, and it must be applied by our own code rather than left to the environment, or a developer running `just dev` gets different metric names from the compose stack.

**3. The default histogram buckets cannot express the latency SLI.**
The SDK's default boundaries for `http.server.request.duration` are:

```
0.005 0.01 0.025 0.05 0.075 0.1 0.25 0.5 0.75 1 2.5 5 7.5 10
```

There is **no 0.3 boundary**. The latency SLI is "the fraction of requests faster than 300 ms", which in PromQL is a ratio against `..._bucket{le="0.3"}` — a series that simply would not exist. `histogram_quantile` is not a substitute: it interpolates *within* a bucket and answers a different question ("what latency is the 95th percentile") than an objective needs ("what fraction beat 300 ms"). A `View` with explicit boundaries fixes it, and the added boundary was confirmed to survive all the way into Prometheus as `le="0.3"`.

**4. Exact Prometheus series and label names after OTLP ingestion.**
Confirmed by exporting real metrics into `grafana/otel-lgtm:0.11.11` and querying its Prometheus. Dots become underscores, the unit is appended as a suffix:

```
http_server_request_duration_seconds_bucket / _count / _sum
http_server_active_requests
http_server_response_body_size_bytes_bucket / _count / _sum
service_info
target_info
```

The labels on the duration series are exactly:

```
job                          = the service.name resource attribute
service_name  service_version  service_instance_id  instance
deployment_environment_name
http_route  http_request_method  http_response_status_code
url_scheme  network_protocol_version
error_type                   (present only on 5xx samples)
```

Two consequences. `job` carries `service.name`, so spec 3.4's `{{ $labels.job }}` in an alert annotation is right. And the environment label is `deployment_environment_name`, **not** `deployment_environment` — see the next item.

**5. `deployment.environment` alone will not become a Prometheus label.**
The image's `prometheus.yaml` promotes a fixed list of resource attributes to labels, and that list contains `deployment.environment.name` (the current semantic convention), not the older `deployment.environment`. Spec 7.6's log field contract names `deployment.environment`, and `observability/logging.py` already emits it and is tested for it. Both are needed and both are cheap, so the OpenTelemetry `Resource` sets **both** keys to the same value: `deployment.environment` keeps the spec's log contract, `deployment.environment.name` is what actually becomes a Prometheus label. Confirmed: with both set, `deployment_environment_name="local"` appeared on every series.

**6. Instrumenting an async SQLAlchemy engine goes through `sync_engine`.**
`SQLAlchemyInstrumentor().instrument(engine=...)` does not accept an `AsyncEngine`. Pass `engine.sync_engine`. Confirmed to produce `connect` and `SELECT` spans carrying `db.system`, `db.statement` and `db.operation`.

**7. The connection pool exposes the numbers the saturation panels need.**
`build_engine`'s configuration (`pool_size=N`, `max_overflow=0`) yields an `AsyncAdaptedQueuePool` with `size()`, `checkedout()`, `checkedin()` and `overflow()`. Confirmed on a real engine object; note that `create_async_engine` opens no connection, so reading these is safe at any time.

**8. Span and trace identifiers, and the invalid case.**
`trace.get_current_span().get_span_context()` gives `trace_id` and `span_id` as integers; the wire format is `format(value, "032x")` and `format(value, "016x")`. Outside any span the context is the invalid one — `is_valid` is `False` and `trace_id` is `0`. The structlog processor must check `is_valid` and bind nothing when false, otherwise every startup line carries `trace_id="000...0"`.

**9. `InMemoryLogExporter` is deprecated; `InMemoryLogRecordExporter` is not.**
Importing the former raises `DeprecationWarning`, which `filterwarnings = ["error"]` turns into a test failure. Use `InMemoryLogRecordExporter` from `opentelemetry.sdk._logs.export`.

**10. Every import path used in this plan was checked.**
All 24 of them resolve on the pinned versions, including the private-looking `from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter` (the underscore is upstream's, and it is the only public route to the gRPC log exporter) and `from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler`.

**11. `grafana/otel-lgtm:0.11.11` internals.**

- Grafana provisioning lives at `/otel-lgtm/grafana/conf/provisioning/{dashboards,datasources}/`.
- The datasource UIDs are `prometheus`, `tempo`, `loki`, `pyroscope`. Dashboards must reference `prometheus` by that UID.
- The Loki datasource already declares a derived field on the label `trace_id` that links to Tempo. Emitting `trace_id` on log records is therefore all that trace-to-log correlation requires; no extra configuration.
- **The image declares no `EXPOSE`d ports.** Compose must publish 3000, 4317 and 4318 explicitly or nothing is reachable.
- Anonymous access is enabled with the Admin role, so the Grafana HTTP API is usable from a test with no credentials. `GET /api/search?type=dash-db` lists provisioned dashboards.

**12. The bundled Prometheus has no `rule_files`, and mounting one over it works.**
`run-prometheus.sh` starts Prometheus with `--config.file=./prometheus.yaml`, and that shipped file contains only `otlp:` and `storage:` blocks — no scrape configs and **no rule files at all**. Recording and alerting rules therefore need a replacement config mounted over `/otel-lgtm/prometheus.yaml` that keeps those two blocks and adds `rule_files`. Confirmed end to end: with a replacement config and a rules directory mounted, `GET /api/v1/rules` reported both groups loaded and every recording rule `health=ok`.

**13. `promtool` ships inside the image, so the rule gates need no extra tooling.**
It is at `/otel-lgtm/prometheus/promtool`. Both `promtool check rules` (syntax) and `promtool test rules` (unit tests with synthetic series) were confirmed to run via `docker run --entrypoint`. The second is the valuable one: a rule unit test proved that 1000 requests/minute of `/readyz` traffic did **not** dilute a 10% error ratio, which is exactly the health-endpoint exclusion this milestone must get right.

**14. Python runtime metrics come from `opentelemetry-instrumentation-system-metrics`, and its default config is wrong for us.**
Instrumented with defaults it emits ~30 metrics including *both* the current names (`cpython.gc.collections`, `process.memory.usage`, `process.thread.count`) and the deprecated `process.runtime.cpython.*` duplicates of the same numbers, plus whole-host `system.*` series that describe the developer's laptop rather than the service. Pass an explicit `config` dict to select only what dashboard 3 needs. The exact keys accepted are `process.cpu.time`, `process.cpu.utilization`, `process.memory.usage`, `process.memory.virtual`, `process.open_file_descriptor.count`, `process.thread.count`, `cpython.gc.collections`, `cpython.gc.collected_objects`, `cpython.gc.uncollectable_objects`.

---

## File Structure

```
examples/reference-service/
  ops/                                          NEW — everything mounted into the stack
    prometheus/
      prometheus.yaml                           replaces the image's own config
      rules/
        slo.yml                                 recording rules + burn-rate alerts
        slo_test.yml                            promtool unit tests for slo.yml
    grafana/
      provisioning/
        dashboards/pyfr-dashboards.yaml         points Grafana at the directory below
      dashboards/
        service-health.json                     RED + saturation
        slo.json                                SLI, error budget, burn rate
        runtime.json                            GC, memory, worker state

  src/reference_service/
    observability/
      slo.py                    NEW — the SLO numbers, shared by code and rules
      otel.py                   NEW — resource, providers, exporters, instrumentation
      metrics.py                NEW — service_info, pool gauges, event loop lag
      logging.py                MODIFIED — trace context processor, OTLP handler
    settings.py                 MODIFIED — OtelSettings grows and validates
    main.py                     MODIFIED — build providers, instrument, shut down
    container.py                MODIFIED — expose the engine for pool metrics

  tests/
    unit/
      test_slo.py               NEW — the threshold is a real bucket boundary
      test_otel.py              NEW — resource, sampler, view, disabled path
      test_otel_logs.py         NEW — OTLP log export, opt-in only
      test_metrics.py           NEW — service_info, pool gauges, loop lag
      test_slo_rules.py         NEW — the gate: PromQL and Python agree
      test_dashboards.py        NEW — dashboard JSON is well formed and wired
      test_logging.py           MODIFIED — trace_id/span_id injection
      test_settings.py          MODIFIED — the new OTel settings
    api/
      test_instrumentation.py   NEW — a request yields a span and stable metrics
    integration/
      test_observability_stack.py  NEW — promtool, Grafana provisioning, live query
      test_db_instrumentation.py   NEW — a repository call yields a database span

  pyproject.toml                MODIFIED — five new runtime deps, one dev dep
  compose.yaml                  MODIFIED — the o11y profile
  justfile                      MODIFIED — o11y recipes and a rules gate
  .env.example                  MODIFIED — the new variables, with warnings
  .importlinter                 MODIFIED — opentelemetry joins the forbidden list
  Dockerfile                    MODIFIED — nothing to add; see Task 11's note

docs/
  reference/configuration.md    MODIFIED — the new settings
  reference/commands.md         MODIFIED — the new recipes
  reference/logging.md          MODIFIED — trace_id/span_id join the contract
  reference/observability.md    NEW — the one page M2 owes the site
  roadmap.md                    MODIFIED — M1 and M2 marked done
```

**Why `observability/` gains three modules rather than growing `logging.py`.** Each has one job and one reason to change: `slo.py` holds numbers a product owner argues about, `otel.py` holds SDK wiring that changes when a library version changes, `metrics.py` holds instruments that change when someone wants a new panel. Nothing in `slo.py` imports OpenTelemetry, which is what lets the PromQL gate in Task 9 read it without the SDK installed.

---

## Task 1: Dependencies and settings

**Files:**
- Modify: `examples/reference-service/pyproject.toml`
- Modify: `examples/reference-service/src/reference_service/settings.py` (the `OtelSettings` class)
- Modify: `examples/reference-service/.env.example`
- Modify: `examples/reference-service/.importlinter`
- Test: `examples/reference-service/tests/unit/test_settings.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `OtelSettings` with fields `enabled: bool`, `logs_enabled: bool`, `endpoint: str | None`, `sample_ratio: float`, `metric_export_interval_ms: int`. Every later task reads these off `settings.otel`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_settings.py`:

```python
def test_otel_is_off_by_default() -> None:
    """The M0/M1 no-dependency path must survive M2 untouched."""
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.otel.enabled is False
    assert settings.otel.logs_enabled is False
    assert settings.otel.endpoint is None
    assert settings.otel.sample_ratio == 1.0


def test_enabling_otel_without_an_endpoint_is_rejected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Silently dropping every span is worse than refusing to start.

    With no endpoint the SDK still builds, still samples, still batches —
    and then fails to connect on a background thread, where the failure is
    a log line nobody reads rather than a startup error.
    """
    monkeypatch.setenv("APP_OTEL__ENABLED", "true")

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None)  # type: ignore[call-arg]

    assert "APP_OTEL__ENDPOINT" in str(caught.value)


def test_otlp_logs_cannot_be_enabled_on_their_own(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """logs_enabled rides on the same providers `enabled` builds."""
    monkeypatch.setenv("APP_OTEL__LOGS_ENABLED", "true")

    with pytest.raises(ValidationError) as caught:
        Settings(_env_file=None)  # type: ignore[call-arg]

    assert "APP_OTEL__ENABLED" in str(caught.value)


@pytest.mark.parametrize("ratio", ["-0.1", "1.1"])
def test_sample_ratio_outside_zero_to_one_is_rejected(
    monkeypatch: pytest.MonkeyPatch, ratio: str
) -> None:
    monkeypatch.setenv("APP_OTEL__ENABLED", "true")
    monkeypatch.setenv("APP_OTEL__ENDPOINT", "http://localhost:4317")
    monkeypatch.setenv("APP_OTEL__SAMPLE_RATIO", ratio)

    with pytest.raises(ValidationError):
        Settings(_env_file=None)  # type: ignore[call-arg]
```

`ValidationError` is already imported at the top of `test_settings.py` by M1's tests; confirm it is, and add `from pydantic import ValidationError` if not.

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_settings.py -k otel -v`
Expected: FAIL. `test_otel_is_off_by_default` fails on `AttributeError`/`assert` for `sample_ratio`; the three validation tests fail with `DID NOT RAISE ValidationError`.

- [ ] **Step 3: Add the dependencies**

In `pyproject.toml`, add to `[project].dependencies`:

```toml
    # Traces, metrics and logs. The API/SDK/exporter line and the
    # instrumentation line version SEPARATELY and always will: 1.44.0 for the
    # first, 0.65b0 for the second. The `b` is upstream's, not a typo — the
    # instrumentation packages are permanently beta-versioned.
    "opentelemetry-sdk>=1.44,<2",
    "opentelemetry-exporter-otlp-proto-grpc>=1.44,<2",
    "opentelemetry-instrumentation-fastapi>=0.65b0",
    "opentelemetry-instrumentation-sqlalchemy>=0.65b0",
    # Garbage collection, memory and thread counts for the runtime dashboard.
    # Its defaults emit both the current metric names and their deprecated
    # `process.runtime.cpython.*` duplicates plus whole-host `system.*`
    # series; observability/otel.py passes an explicit config instead.
    "opentelemetry-instrumentation-system-metrics>=0.65b0",
```

and to `[dependency-groups].dev`:

```toml
    # Reads ops/prometheus/rules/*.yml in the SLO gate (tests/unit/
    # test_slo_rules.py), so the PromQL and the Python constants cannot
    # drift. Available transitively through pre-commit today; depended on
    # explicitly because a gate must not rest on someone else's transitive
    # dependency.
    "pyyaml>=6.0",
    "types-pyyaml>=6.0",
```

Then run `uv sync` and commit `uv.lock`.

- [ ] **Step 4: Replace `OtelSettings` in `settings.py`**

```python
class OtelSettings(BaseModel):
    # See LogSettings.model_config for why this is needed independently of
    # Settings's own frozen=True.
    model_config = ConfigDict(frozen=True)

    enabled: bool = False
    # Standard output is the source of truth for logs (spec D15). Enabling
    # this in production alongside a platform log agent doubles ingest
    # volume and cost. The local compose profile turns it on; nothing else
    # should.
    logs_enabled: bool = False
    endpoint: str | None = None
    # Parent-based sampling: a request already carrying a sampled parent is
    # always recorded, and this ratio decides only for requests that start
    # here. 1.0 locally so a developer sees the request they just made;
    # lower in production, where recording every span costs real money.
    sample_ratio: float = Field(default=1.0, ge=0.0, le=1.0)
    # How often metrics are pushed. The SDK default is 60s, which matches
    # the Grafana datasource's own 60s timeInterval; the o11y compose
    # profile lowers it so a developer is not waiting a minute to see a
    # panel move.
    metric_export_interval_ms: int = Field(default=60_000, ge=1_000)

    @model_validator(mode="after")
    def _exporting_requires_somewhere_to_export_to(self) -> OtelSettings:
        """Refuse to start rather than drop telemetry on a background thread.

        With `enabled` true and no endpoint the SDK builds happily, samples
        happily, batches happily, and then fails to connect from its own
        exporter thread — where the failure is a log line nobody is reading
        at 3am, and the symptom is "the dashboards are empty" a week later.
        Failing here makes it exit 78 with the variable named, like every
        other bad setting (see load_settings).

        `logs_enabled` is checked against `enabled` rather than against
        `endpoint` because the log exporter shares the providers `enabled`
        builds: on its own it would configure nothing at all, which is the
        same silent-nothing failure in a second costume.
        """
        if self.enabled and not self.endpoint:
            raise ValueError(
                "APP_OTEL__ENABLED is true but APP_OTEL__ENDPOINT is not "
                "set: the SDK would start and then drop every span, metric "
                "and log record from its own exporter thread. Set the "
                "collector endpoint, or set APP_OTEL__ENABLED=false."
            )
        if self.logs_enabled and not self.enabled:
            raise ValueError(
                "APP_OTEL__LOGS_ENABLED is true but APP_OTEL__ENABLED is "
                "false: OTLP log export uses the providers APP_OTEL__ENABLED "
                "builds, so on its own this setting does nothing."
            )
        return self
```

Add `model_validator` to the existing `from pydantic import (...)` block.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_settings.py -v`
Expected: PASS, including every M1 settings test.

- [ ] **Step 6: Forbid `opentelemetry` in the pure layers**

In `.importlinter`, add `opentelemetry` to `forbidden_modules` in **both** contracts, under the existing `asyncpg` line:

```
    asyncpg
    opentelemetry
```

The reasoning is the same one that keeps SQLAlchemy out: a domain rule that reaches for a span is a domain rule you cannot unit test without an SDK.

Run: `cd examples/reference-service && uv run lint-imports`
Expected: both contracts kept.

- [ ] **Step 7: Update `.env.example`**

Replace the `APP_OTEL__*` block (which currently says "OpenTelemetry arrives in M2") with:

```
# OpenTelemetry. Off by default: with `enabled` false the process imports no
# exporter, opens no socket and starts no background task, so a service that
# wants none of this pays nothing for it.
#
# `just o11y` runs the local Grafana stack and sets all of these itself; you
# do not need to uncomment anything here to try it.
APP_OTEL__ENABLED=false
# Where traces and metrics go. Required when APP_OTEL__ENABLED is true —
# enabling the SDK without it fails settings validation on purpose, because
# the alternative is silently dropping every span from a background thread.
# APP_OTEL__ENDPOINT=http://localhost:4317
# Fraction of NEW traces recorded, 0.0 to 1.0. Sampling is parent-based, so a
# request arriving with a sampled parent is recorded whatever this says.
APP_OTEL__SAMPLE_RATIO=1.0
# How often metrics are pushed, in milliseconds.
APP_OTEL__METRIC_EXPORT_INTERVAL_MS=60000
# OTLP log export, ON TOP OF standard output — never instead of it.
#
# Leave this false in production. Standard output is the source of truth: it
# survives a collector outage and captures crashes and any failure happening
# before the SDK has initialised, which is exactly the output you need when a
# service will not start. Turning this on in production ALONGSIDE a platform
# log agent means every line is ingested twice, which doubles log volume and
# the bill that follows it. It exists so that locally you see logs beside the
# matching trace in Grafana without wiring up a log scraper.
APP_OTEL__LOGS_ENABLED=false
```

- [ ] **Step 8: Run the full fast suite**

Run: `cd examples/reference-service && uv run pytest && uv run mypy && uv run lint-imports && uv run ruff check .`
Expected: all pass. The M0/M1 tests are unaffected because every new setting defaults to off.

- [ ] **Step 9: Commit**

```bash
git add examples/reference-service/pyproject.toml examples/reference-service/uv.lock examples/reference-service/src/reference_service/settings.py examples/reference-service/.env.example examples/reference-service/.importlinter examples/reference-service/tests/unit/test_settings.py
git commit -m "feat(observability): add opentelemetry dependencies and validated otel settings"
```

---

## Task 2: The SLO numbers, in one place

**Files:**
- Create: `examples/reference-service/src/reference_service/observability/slo.py`
- Test: `examples/reference-service/tests/unit/test_slo.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `SLO_AVAILABILITY_TARGET: float`, `SLO_WINDOW_DAYS: int`, `SLO_LATENCY_THRESHOLD_SECONDS: float`, `ERROR_BUDGET: float`, `HTTP_DURATION_BUCKET_BOUNDARIES: tuple[float, ...]`, `SLI_EXCLUDED_ROUTES: tuple[str, ...]`, `excluded_routes_pattern() -> str`. Task 3 imports the boundaries, Task 9's gate imports all of them.

This module deliberately imports nothing. Task 9's gate reads it in a process that has the rules YAML but does not care about the SDK, and M7 will replace these six literals with cookiecutter variables — both are easier when the file has no dependencies.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_slo.py`:

```python
"""The SLO numbers are only useful if the histogram can express them."""

from reference_service.observability.slo import (
    ERROR_BUDGET,
    HTTP_DURATION_BUCKET_BOUNDARIES,
    SLI_EXCLUDED_ROUTES,
    SLO_AVAILABILITY_TARGET,
    SLO_LATENCY_THRESHOLD_SECONDS,
    excluded_routes_pattern,
)


def test_the_latency_threshold_is_an_actual_bucket_boundary() -> None:
    """Without this the latency SLI cannot be computed at all.

    The SDK's default boundaries jump 0.25 -> 0.5, so `le="0.3"` would
    never exist as a series and the PromQL ratio in ops/prometheus/rules/
    slo.yml would silently return nothing. `histogram_quantile` is not a
    substitute: it interpolates inside a bucket, which answers "what is
    the p95 latency", not "what fraction of requests beat 300ms".
    """
    assert SLO_LATENCY_THRESHOLD_SECONDS in HTTP_DURATION_BUCKET_BOUNDARIES


def test_bucket_boundaries_are_sorted_and_unique() -> None:
    """The SDK requires strictly increasing boundaries and raises if not."""
    boundaries = list(HTTP_DURATION_BUCKET_BOUNDARIES)
    assert boundaries == sorted(boundaries)
    assert len(boundaries) == len(set(boundaries))


def test_error_budget_is_the_complement_of_the_target() -> None:
    assert ERROR_BUDGET == 1.0 - SLO_AVAILABILITY_TARGET
    # Floating point: 1 - 0.999 is 0.0009999999999999454, not 0.001. The
    # alert thresholds multiply this by burn rates up to 14.4, so the
    # module must round it rather than let the drift compound.
    assert ERROR_BUDGET == 0.001


def test_health_endpoints_are_excluded_from_the_objective() -> None:
    """A probe every two seconds otherwise dwarfs real traffic.

    With /readyz counted, a service serving ten real requests a minute
    beside 1800 readiness probes reports a 99.9% success rate no matter
    how badly the real ten are doing.
    """
    assert set(SLI_EXCLUDED_ROUTES) == {"/healthz", "/readyz", "/startupz"}


def test_the_exclusion_pattern_is_anchored_promql() -> None:
    """Prometheus label matchers are implicitly fully anchored, so the
    pattern must not accidentally match a real route that CONTAINS one of
    these names — but it must match each excluded route exactly."""
    pattern = excluded_routes_pattern()
    assert pattern == "/healthz|/readyz|/startupz"
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_slo.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reference_service.observability.slo'`.

- [ ] **Step 3: Write the module**

Create `src/reference_service/observability/slo.py`:

```python
"""The service level objective, as numbers that code and PromQL both read.

Nothing here imports anything. That is deliberate twice over: the gate in
tests/unit/test_slo_rules.py reads these constants to check the shipped
Prometheus rules agree with them, and M7 replaces the literals below with
cookiecutter variables. Both are simpler against a file with no imports.

Spec 7.5 fixes the defaults: 99.9% of requests succeed, 99.9% complete
within 300ms, measured over a rolling 30 days.
"""

from __future__ import annotations

# Fraction of requests that must not return 5xx, over the rolling window.
SLO_AVAILABILITY_TARGET = 0.999

# The window the objective is measured over.
SLO_WINDOW_DAYS = 30

# A request finishing within this many seconds counts as fast. This value
# MUST also appear in HTTP_DURATION_BUCKET_BOUNDARIES below — see the
# comment there — and as the `le` label in the latency recording rules in
# ops/prometheus/rules/slo.yml. tests/unit/test_slo.py checks the first,
# tests/unit/test_slo_rules.py checks the second.
SLO_LATENCY_THRESHOLD_SECONDS = 0.3

# How much failure the objective permits. Rounded on purpose: 1 - 0.999
# is 0.0009999999999999454 in binary floating point, and the burn-rate
# alerts multiply this by up to 14.4, so the drift would show up in the
# rendered alert thresholds.
ERROR_BUDGET = round(1.0 - SLO_AVAILABILITY_TARGET, 10)

# Explicit bucket boundaries for http.server.request.duration, in seconds.
#
# The OpenTelemetry SDK's own defaults are
#   0.005 0.01 0.025 0.05 0.075 0.1 0.25 0.5 0.75 1 2.5 5 7.5 10
# which steps straight from 0.25 to 0.5 and so has NO boundary at the
# latency threshold. Prometheus can only count requests faster than a
# boundary that exists: without adding it here, the series
# http_server_request_duration_seconds_bucket{le="0.3"} is never produced
# and the latency SLI is not merely inaccurate, it is uncomputable.
#
# Every other boundary is the SDK default, kept as-is so the numbers stay
# comparable with any other OpenTelemetry service in the same Grafana.
HTTP_DURATION_BUCKET_BOUNDARIES = (
    0.005,
    0.01,
    0.025,
    0.05,
    0.075,
    0.1,
    0.25,
    SLO_LATENCY_THRESHOLD_SECONDS,
    0.5,
    0.75,
    1.0,
    2.5,
    5.0,
    7.5,
    10.0,
)

# Routes that count towards neither SLI. Kubernetes probes a readiness
# endpoint every couple of seconds forever; counted, they would swamp real
# traffic and report a healthy objective for a service that is failing
# every request a user actually makes.
SLI_EXCLUDED_ROUTES = ("/healthz", "/readyz", "/startupz")


def excluded_routes_pattern() -> str:
    """The `http_route!~"..."` matcher body used by every SLI rule.

    Prometheus anchors label matchers at both ends already, so plain
    alternation is exact and no `^`/`$` is needed — adding them would be
    matched literally by some Prometheus versions rather than ignored.
    """
    return "|".join(SLI_EXCLUDED_ROUTES)
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_slo.py -v`
Expected: PASS, 5 tests.

- [ ] **Step 5: Commit**

```bash
git add examples/reference-service/src/reference_service/observability/slo.py examples/reference-service/tests/unit/test_slo.py
git commit -m "feat(observability): define the slo constants shared by code and promql"
```

---

## Task 3: Providers, resource, sampler and the histogram view

**Files:**
- Create: `examples/reference-service/src/reference_service/observability/otel.py`
- Test: `examples/reference-service/tests/unit/test_otel.py`

**Interfaces:**
- Consumes: `OtelSettings` (Task 1), `HTTP_DURATION_BUCKET_BOUNDARIES` (Task 2).
- Produces:
  - `build_resource(settings: Settings, service_version: str) -> Resource`
  - `build_sampler(sample_ratio: float) -> Sampler`
  - `build_views() -> tuple[View, ...]`
  - `build_providers(settings, service_version, *, span_exporter=None, metric_reader=None) -> OtelRuntime`
  - `configure_otel(settings, service_version) -> OtelRuntime | None`
  - `class OtelRuntime` with `.tracer_provider`, `.meter_provider`, `.logger_provider`, `.shutdown()`
- Task 4 calls `configure_otel` and `OtelRuntime.shutdown`; Task 5 and Task 8 take an `OtelRuntime`.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_otel.py`:

```python
"""The SDK wiring, with no network and no globals touched.

Every test here uses build_providers rather than configure_otel. Only the
latter installs the process-global providers, and OpenTelemetry allows that
exactly once per process — a test that did it would poison every test after
it in the same run.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from opentelemetry.sdk.trace.sampling import ParentBased

from reference_service.observability.otel import (
    build_providers,
    build_resource,
    build_sampler,
    build_views,
    configure_otel,
)
from reference_service.observability.slo import (
    HTTP_DURATION_BUCKET_BOUNDARIES,
    SLO_LATENCY_THRESHOLD_SECONDS,
)
from reference_service.settings import Settings


def _enabled_settings() -> Settings:
    return Settings(  # type: ignore[call-arg]
        _env_file=None,
        environment="production",
        otel={"enabled": True, "endpoint": "http://localhost:4317"},
    )


def test_resource_carries_the_three_attributes_the_log_contract_names() -> None:
    resource = build_resource(_enabled_settings(), "1.2.3")

    assert resource.attributes["service.name"] == "reference-service"
    assert resource.attributes["service.version"] == "1.2.3"
    assert resource.attributes["deployment.environment"] == "production"


def test_resource_also_carries_the_current_semconv_environment_key() -> None:
    """`deployment.environment` alone never becomes a Prometheus label.

    grafana/otel-lgtm's Prometheus promotes a fixed list of resource
    attributes to labels and that list contains the newer
    `deployment.environment.name`. Spec 7.6's log field contract names the
    older `deployment.environment`, and logging.py already emits and is
    tested for it. Both keys, same value, is what satisfies both.
    """
    resource = build_resource(_enabled_settings(), "1.2.3")

    assert resource.attributes["deployment.environment.name"] == "production"


def test_sampler_is_parent_based() -> None:
    """A request arriving with a sampled parent must stay sampled.

    Otherwise a trace crossing two services is recorded in one and dropped
    in the next, which is worse than not tracing: the gap looks like the
    second service never received the request.
    """
    assert isinstance(build_sampler(0.25), ParentBased)


@pytest.mark.parametrize("ratio", [0.0, 0.5, 1.0])
def test_sampler_accepts_the_whole_configured_range(ratio: float) -> None:
    assert build_sampler(ratio) is not None


def test_the_duration_view_adds_the_slo_bucket_boundary() -> None:
    """Verified fact 3: the SDK default set has no 0.3 boundary."""
    views = build_views()

    duration_views = [
        view
        for view in views
        if getattr(view, "_instrument_name", None) == "http.server.request.duration"
    ]
    assert len(duration_views) == 1

    aggregation = duration_views[0]._aggregation
    assert isinstance(aggregation, ExplicitBucketHistogramAggregation)
    assert tuple(aggregation._boundaries) == HTTP_DURATION_BUCKET_BOUNDARIES
    assert SLO_LATENCY_THRESHOLD_SECONDS in aggregation._boundaries


def test_build_providers_accepts_injected_exporters() -> None:
    """The seam every later task's tests hang off."""
    runtime = build_providers(
        _enabled_settings(),
        "1.2.3",
        span_exporter=InMemorySpanExporter(),
        metric_reader=InMemoryMetricReader(),
    )

    assert runtime.tracer_provider is not None
    assert runtime.meter_provider is not None
    # logs_enabled is false in these settings, so no logger provider.
    assert runtime.logger_provider is None

    runtime.shutdown()


def test_shutdown_is_idempotent() -> None:
    """lifespan's finally block can run after an already-failed startup."""
    runtime = build_providers(
        _enabled_settings(),
        "1.2.3",
        span_exporter=InMemorySpanExporter(),
        metric_reader=InMemoryMetricReader(),
    )

    runtime.shutdown()
    runtime.shutdown()


def test_configure_otel_returns_none_when_disabled() -> None:
    """The default path: no providers, no exporter, no background thread."""
    settings = Settings(_env_file=None, environment="production")  # type: ignore[call-arg]

    assert configure_otel(settings, "1.2.3") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_otel.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reference_service.observability.otel'`.

- [ ] **Step 3: Write the module**

Create `src/reference_service/observability/otel.py`:

```python
"""OpenTelemetry SDK wiring: resource, providers, exporters, instrumentation.

Everything the SDK needs is built here and nowhere else, so the rest of the
service never imports `opentelemetry` — a rule the import-linter contracts
enforce for domain/ and services/.

Two functions build providers. `build_providers` is pure construction and
takes exporter overrides, which is what the tests use. `configure_otel`
wraps it and additionally installs the process-global providers, so that
application code written later can call `trace.get_tracer(__name__)` and
get a real tracer. OpenTelemetry permits that global installation exactly
once per process, which is why no test calls `configure_otel` twice.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from urllib.parse import urlsplit

from opentelemetry import metrics, trace
from opentelemetry._logs import set_logger_provider
from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import BatchLogRecordProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import (
    MetricReader,
    PeriodicExportingMetricReader,
)
from opentelemetry.sdk.metrics.view import ExplicitBucketHistogramAggregation, View
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace.sampling import ParentBased, Sampler, TraceIdRatioBased

from reference_service.observability.slo import HTTP_DURATION_BUCKET_BOUNDARIES
from reference_service.settings import Settings

# Selects the STABLE HTTP semantic conventions. Without it the FastAPI
# instrumentation emits the legacy set — `http.server.duration` in
# milliseconds with `http.method` and `http.status_code` — instead of the
# `http.server.request.duration` in seconds with `http.route`,
# `http.request.method` and `http.response.status_code` that spec 7.2
# requires and that every dashboard and SLO rule in ops/ queries.
#
# This is read on the FIRST instrument*() call in the process and cached
# for the life of the process; setting it afterwards changes nothing.
# Verified directly: instrumenting once without it and then setting it
# still produced the legacy names. So it is applied by
# _opt_in_to_stable_semconv() below, called at the top of BOTH
# instrumentation entry points rather than left to the environment —
# a developer running `just dev` must not get different metric names from
# the compose stack.
_STABLE_SEMCONV_ENV_VAR = "OTEL_SEMCONV_STABILITY_OPT_IN"
_STABLE_SEMCONV_VALUE = "http"


def _opt_in_to_stable_semconv() -> None:
    """Ask for the stable HTTP conventions before anything instruments.

    `setdefault`, not assignment: an operator who has deliberately set this
    variable — to add `database` alongside `http`, say — keeps their value.
    """
    os.environ.setdefault(_STABLE_SEMCONV_ENV_VAR, _STABLE_SEMCONV_VALUE)


def _is_insecure(endpoint: str) -> bool:
    """Plain http:// means no TLS; anything else is treated as TLS.

    The gRPC exporters take this as a separate flag rather than reading the
    scheme themselves, and defaulting it wrongly fails at connect time on a
    background thread rather than at startup.
    """
    return urlsplit(endpoint).scheme == "http"


def build_resource(settings: Settings, service_version: str) -> Resource:
    """The attributes every span, metric and log record carries.

    `deployment.environment` and `deployment.environment.name` are both set
    to the same value on purpose. The first is what spec 7.6's log field
    contract names and what observability/logging.py already emits. The
    second is the current semantic convention, and it is the one Prometheus
    promotes to a label — with only the first set, no environment label
    reaches the dashboards at all.
    """
    return Resource.create(
        {
            "service.name": settings.service_name,
            "service.version": service_version,
            "deployment.environment": settings.environment,
            "deployment.environment.name": settings.environment,
        }
    )


def build_sampler(sample_ratio: float) -> Sampler:
    """Parent-based ratio sampling.

    Parent-based is the part that matters. A request arriving with a
    sampled parent is always recorded regardless of the ratio, so a trace
    crossing several services is never half-recorded — a gap in the middle
    of a distributed trace reads as "the next service never got the
    request", which is a much more alarming thing to see than no trace.
    The ratio then decides only for requests whose trace starts here.
    """
    return ParentBased(root=TraceIdRatioBased(sample_ratio))


def build_views() -> tuple[View, ...]:
    """Metric views. One, and it is load-bearing for the latency SLO.

    See observability/slo.py's comment on HTTP_DURATION_BUCKET_BOUNDARIES:
    the SDK's default boundaries step from 0.25s straight to 0.5s, so the
    series http_server_request_duration_seconds_bucket{le="0.3"} would
    never exist and the latency objective could not be computed at all.
    """
    return (
        View(
            instrument_name="http.server.request.duration",
            aggregation=ExplicitBucketHistogramAggregation(
                boundaries=HTTP_DURATION_BUCKET_BOUNDARIES
            ),
        ),
    )


@dataclass
class OtelRuntime:
    """The providers, held so `lifespan` can flush and close them."""

    tracer_provider: TracerProvider
    meter_provider: MeterProvider
    logger_provider: LoggerProvider | None
    _shut_down: bool = False

    def shutdown(self) -> None:
        """Flush and close every provider. Safe to call more than once.

        Idempotence is not decoration: `lifespan`'s finally block runs even
        when startup raised partway, and the SDK's own shutdown methods log
        a warning when called twice. One flag here keeps that noise out of
        the shutdown path of a process that is already having a bad day.

        Order matters. Logs go last because the other two providers can
        emit log records while shutting down, and a closed logger provider
        would drop exactly the lines explaining why shutdown was unhappy.
        """
        if self._shut_down:
            return
        self._shut_down = True
        self.tracer_provider.shutdown()
        self.meter_provider.shutdown()
        if self.logger_provider is not None:
            self.logger_provider.shutdown()


def build_providers(
    settings: Settings,
    service_version: str,
    *,
    span_exporter: SpanExporter | None = None,
    metric_reader: MetricReader | None = None,
) -> OtelRuntime:
    """Construct the providers. Installs nothing globally.

    The two keyword arguments exist for the tests, which substitute
    in-memory exporters so the suite needs no collector and no network.
    Production passes neither and gets the OTLP exporters.
    """
    endpoint = settings.otel.endpoint or ""
    insecure = _is_insecure(endpoint)
    resource = build_resource(settings, service_version)

    tracer_provider = TracerProvider(
        resource=resource, sampler=build_sampler(settings.otel.sample_ratio)
    )
    tracer_provider.add_span_processor(
        BatchSpanProcessor(
            span_exporter
            if span_exporter is not None
            else OTLPSpanExporter(endpoint=endpoint, insecure=insecure)
        )
    )

    reader = (
        metric_reader
        if metric_reader is not None
        else PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=endpoint, insecure=insecure),
            export_interval_millis=settings.otel.metric_export_interval_ms,
        )
    )
    meter_provider = MeterProvider(
        resource=resource, metric_readers=[reader], views=build_views()
    )

    logger_provider: LoggerProvider | None = None
    if settings.otel.logs_enabled:
        logger_provider = LoggerProvider(resource=resource)
        logger_provider.add_log_record_processor(
            BatchLogRecordProcessor(
                OTLPLogExporter(endpoint=endpoint, insecure=insecure)
            )
        )

    return OtelRuntime(
        tracer_provider=tracer_provider,
        meter_provider=meter_provider,
        logger_provider=logger_provider,
    )


def configure_otel(settings: Settings, service_version: str) -> OtelRuntime | None:
    """Build the providers and install them globally, or do nothing.

    Returns None when telemetry is off, which is the default. On that path
    this function imports no exporter, opens no socket and starts no
    thread: a generated service that wants none of this pays nothing.

    The global installation is what makes `trace.get_tracer(__name__)` work
    in code written later, in a service generated from this template, that
    wants a manual span around something this milestone knows nothing
    about. It happens once per process; tests use build_providers instead.
    """
    if not settings.otel.enabled:
        return None

    runtime = build_providers(settings, service_version)
    trace.set_tracer_provider(runtime.tracer_provider)
    metrics.set_meter_provider(runtime.meter_provider)
    if runtime.logger_provider is not None:
        set_logger_provider(runtime.logger_provider)
    return runtime
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_otel.py -v`
Expected: PASS, 10 tests — the sampler-range case is parametrised three ways.

If `test_the_duration_view_adds_the_slo_bucket_boundary` fails on an
attribute name, the SDK's private attributes on `View` moved between
versions. Print `vars(views[0])` and adjust the two `_`-prefixed reads;
do not weaken the assertion to "a view exists", because the boundary
being present is the entire point of the test.

- [ ] **Step 5: Check types and imports**

Run: `cd examples/reference-service && uv run mypy && uv run lint-imports && uv run ruff check .`
Expected: all pass.

- [ ] **Step 6: Commit**

```bash
git add examples/reference-service/src/reference_service/observability/otel.py examples/reference-service/tests/unit/test_otel.py
git commit -m "feat(observability): build opentelemetry providers, sampler and slo histogram view"
```

---

## Task 4: Instrument FastAPI and wire it into the application factory

**Files:**
- Modify: `examples/reference-service/src/reference_service/observability/otel.py` (add `instrument_fastapi`)
- Modify: `examples/reference-service/src/reference_service/main.py`
- Test: `examples/reference-service/tests/api/test_instrumentation.py`

**Interfaces:**
- Consumes: `OtelRuntime`, `build_providers`, `configure_otel` (Task 3).
- Produces: `instrument_fastapi(app: FastAPI, runtime: OtelRuntime) -> None`. `create_app` stores the runtime on `app.state.otel` and shuts it down in `lifespan`.

- [ ] **Step 1: Write the failing tests**

Create `tests/api/test_instrumentation.py`:

```python
"""A real request through the real app, with in-memory exporters.

No collector, no network, no globals: build_providers takes the exporters
and instrument_fastapi is handed the result.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)

from reference_service.main import create_app
from reference_service.observability.otel import (
    OtelRuntime,
    build_providers,
    instrument_fastapi,
)
from reference_service.observability.slo import SLO_LATENCY_THRESHOLD_SECONDS
from reference_service.settings import Settings


@pytest.fixture
def exporters() -> tuple[InMemorySpanExporter, InMemoryMetricReader]:
    return InMemorySpanExporter(), InMemoryMetricReader()


@pytest.fixture
def runtime(
    settings: Settings,
    exporters: tuple[InMemorySpanExporter, InMemoryMetricReader],
) -> Iterator[OtelRuntime]:
    span_exporter, metric_reader = exporters
    enabled = settings.model_copy(
        update={
            "otel": settings.otel.model_copy(
                update={"enabled": True, "endpoint": "http://localhost:4317"}
            )
        }
    )
    built = build_providers(
        enabled, "1.2.3", span_exporter=span_exporter, metric_reader=metric_reader
    )
    yield built
    built.shutdown()


@pytest.fixture
def instrumented_client(
    settings: Settings, runtime: OtelRuntime
) -> Iterator[TestClient]:
    app = create_app(settings)
    instrument_fastapi(app, runtime)
    with TestClient(app) as client:
        yield client


def _metric_names(reader: InMemoryMetricReader) -> set[str]:
    data = reader.get_metrics_data()
    return {
        metric.name
        for resource_metrics in data.resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
    }


def test_a_request_produces_a_server_span_naming_the_route_template(
    instrumented_client: TestClient,
    exporters: tuple[InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    """The template, never the raw path.

    Same reasoning as the access log's http.route field: a raw path makes
    every order identifier its own distinct value, which is the standard
    way to overwhelm a tracing backend.
    """
    span_exporter, _ = exporters

    instrumented_client.get("/api/v1/orders/does-not-exist")

    routes = {
        span.attributes["http.route"]
        for span in span_exporter.get_finished_spans()
        if span.attributes and "http.route" in span.attributes
    }
    assert "/api/v1/orders/{order_id}" in routes


def test_metrics_use_the_stable_semantic_conventions(
    instrumented_client: TestClient,
    exporters: tuple[InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    """Verified fact 2 — this does NOT happen by default.

    Without the opt-in the instrumentation emits `http.server.duration` in
    milliseconds, and every PromQL expression in ops/ queries a series
    that would then never exist.
    """
    _, metric_reader = exporters

    instrumented_client.get("/api/v1/orders/does-not-exist")

    names = _metric_names(metric_reader)
    assert "http.server.request.duration" in names
    assert "http.server.duration" not in names, "legacy convention leaked in"


def test_the_duration_histogram_has_the_slo_bucket(
    instrumented_client: TestClient,
    exporters: tuple[InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    """End to end proof that build_views reached the real instrument."""
    _, metric_reader = exporters

    instrumented_client.get("/api/v1/orders/does-not-exist")

    boundaries: list[float] = []
    for resource_metrics in metric_reader.get_metrics_data().resource_metrics:
        for scope_metrics in resource_metrics.scope_metrics:
            for metric in scope_metrics.metrics:
                if metric.name == "http.server.request.duration":
                    for point in metric.data.data_points:
                        boundaries = list(point.explicit_bounds)

    assert SLO_LATENCY_THRESHOLD_SECONDS in boundaries


def test_health_endpoints_produce_no_spans(
    instrumented_client: TestClient,
    exporters: tuple[InMemorySpanExporter, InMemoryMetricReader],
) -> None:
    """A readiness probe every two seconds is not a trace anyone wants.

    Same exclusion the access log already applies, for the same reason:
    left in, probe traffic is most of what the backend stores and most of
    what it charges for.
    """
    span_exporter, _ = exporters

    instrumented_client.get("/healthz")
    instrumented_client.get("/readyz")

    assert span_exporter.get_finished_spans() == ()


def test_create_app_leaves_the_app_uninstrumented_when_otel_is_off(
    settings: Settings,
) -> None:
    """The default path stays exactly what M1 shipped."""
    app = create_app(settings)

    assert getattr(app, "_is_instrumented_by_opentelemetry", False) is False


def test_create_app_instruments_and_shuts_down_when_otel_is_on(
    monkeypatch: pytest.MonkeyPatch, settings: Settings, runtime: OtelRuntime
) -> None:
    """`configure_otel` is substituted so no OTLP exporter is constructed."""
    monkeypatch.setattr(
        "reference_service.main.configure_otel",
        lambda _settings, _version: runtime,
    )

    app = create_app(settings)
    with TestClient(app) as client:
        client.get("/api/v1/orders/does-not-exist")
        assert app.state.otel is runtime

    assert runtime._shut_down is True, "lifespan must flush telemetry on exit"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd examples/reference-service && uv run pytest tests/api/test_instrumentation.py -v`
Expected: FAIL with `ImportError: cannot import name 'instrument_fastapi'`.

- [ ] **Step 3: Add `instrument_fastapi` to `observability/otel.py`**

Add the import at the top:

```python
from fastapi import FastAPI
from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
```

and the function at the end of the module:

```python
# Traced and measured for nobody's benefit: an orchestrator probes these
# every couple of seconds forever, so left in they become most of what the
# tracing backend stores and most of what it bills for. The same three
# paths api/middleware.py already keeps out of the access log.
#
# The SLI recording rules in ops/prometheus/rules/slo.yml ALSO exclude
# these routes, which is deliberate duplication rather than an oversight:
# this setting is about cost, and an operator may reasonably widen or
# narrow it, while the objective's definition must not change when they
# do.
_UNTRACED_PATHS = "healthz,readyz,startupz"


def instrument_fastapi(app: FastAPI, runtime: OtelRuntime) -> None:
    """Add the server span and the RED metrics to one application.

    Call this AFTER the application's own middleware has been added.
    Starlette makes the most recently added middleware the outermost one,
    so instrumenting last puts the OpenTelemetry middleware outside
    AccessLogMiddleware — which is what allows the access log record to
    carry the trace_id of the span the request is running in. Instrument
    first and the span does not exist yet when that line is written, so
    every access log entry loses its link to its own trace.
    """
    _opt_in_to_stable_semconv()
    FastAPIInstrumentor.instrument_app(
        app,
        tracer_provider=runtime.tracer_provider,
        meter_provider=runtime.meter_provider,
        excluded_urls=_UNTRACED_PATHS,
    )
```

- [ ] **Step 4: Wire it into `main.py`**

Add the imports:

```python
from reference_service.observability.otel import (
    OtelRuntime,
    configure_otel,
    instrument_fastapi,
)
```

In `create_app`, insert this **before** the existing `configure_logging(...)`
call, and leave `configure_logging` exactly where it is otherwise:

```python
    # Before configure_logging, not after. Task 7 gives configure_logging an
    # optional logger_provider argument for OTLP log export, and that
    # provider is built here — so this has to run first or logging would
    # have to be configured twice. Nothing in configure_otel logs anything,
    # so nothing is lost by the swap: it is pure construction, and a
    # failure inside it surfaces as a traceback on stderr exactly as a
    # settings failure already does.
    #
    # Returns None when APP_OTEL__ENABLED is false, which is the default
    # and the entire M0/M1 path.
    otel_runtime: OtelRuntime | None = configure_otel(resolved, __version__)
```

In `lifespan`, extend the `finally` block:

```python
        finally:
            # Runs on SIGTERM, after in-flight requests finish. uvicorn's
            # --timeout-graceful-shutdown bounds how long that may take.
            container.started = False
            await close_container(container)
            if otel_runtime is not None:
                # Last, and after close_container: shutting the providers
                # down flushes whatever is still batched, and the lines
                # and spans produced BY closing the database pool are
                # exactly the ones you want when a shutdown goes wrong.
                otel_runtime.shutdown()
```

At the end of `create_app`, after both `add_middleware` calls and before `return app`:

```python
    app.state.otel = otel_runtime
    if otel_runtime is not None:
        # Last, so the OpenTelemetry middleware ends up outermost — see
        # instrument_fastapi's docstring for why the ordering is
        # load-bearing rather than incidental.
        instrument_fastapi(app, otel_runtime)
    return app
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd examples/reference-service && uv run pytest tests/api/test_instrumentation.py -v`
Expected: PASS, 6 tests.

- [ ] **Step 6: Run the whole fast suite and the checks**

Run: `cd examples/reference-service && uv run pytest && uv run mypy && uv run lint-imports && uv run ruff check .`
Expected: all pass. Every M0/M1 test still passes untouched, because `configure_otel` returns `None` under the default settings.

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service/src/reference_service/observability/otel.py examples/reference-service/src/reference_service/main.py examples/reference-service/tests/api/test_instrumentation.py
git commit -m "feat(observability): instrument fastapi with stable http semantic conventions"
```

---

## Task 5: Instrument the database

**Files:**
- Modify: `examples/reference-service/src/reference_service/observability/otel.py` (add `instrument_database`)
- Modify: `examples/reference-service/src/reference_service/main.py` (call it from `lifespan`)
- Test: `examples/reference-service/tests/integration/test_db_instrumentation.py`

**Interfaces:**
- Consumes: `OtelRuntime` (Task 3), `Container.engine` (already exists from M1).
- Produces: `instrument_database(engine: AsyncEngine, runtime: OtelRuntime) -> None`.

This task's test lives in the integration tier because a database span needs a database. The existing `tests/integration/conftest.py` already provides a migrated PostgreSQL container; reuse its fixtures rather than adding another.

- [ ] **Step 1: Read the existing integration fixtures**

Run: `cd examples/reference-service && sed -n '1,80p' tests/integration/conftest.py`

Note the fixture that yields a configured `AsyncEngine` or a DSN, and its scope. The test below assumes a fixture named `engine`; rename to match what is actually there.

- [ ] **Step 2: Write the failing test**

Create `tests/integration/test_db_instrumentation.py`:

```python
"""A repository call must appear as a child span of the request.

Without this, a slow endpoint tells you only that it was slow. With it,
the trace shows whether the time went to the database and to which
statement.
"""

from __future__ import annotations

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import (
    InMemorySpanExporter,
)
from sqlalchemy.ext.asyncio import AsyncEngine

from reference_service.observability.otel import build_providers, instrument_database
from reference_service.settings import Settings

pytestmark = pytest.mark.integration


async def test_a_query_produces_a_database_span(
    engine: AsyncEngine, settings: Settings
) -> None:
    span_exporter = InMemorySpanExporter()
    enabled = settings.model_copy(
        update={
            "otel": settings.otel.model_copy(
                update={"enabled": True, "endpoint": "http://localhost:4317"}
            )
        }
    )
    runtime = build_providers(enabled, "1.2.3", span_exporter=span_exporter)
    instrument_database(engine, runtime)

    try:
        from sqlalchemy import text

        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

        systems = {
            span.attributes.get("db.system")
            for span in span_exporter.get_finished_spans()
            if span.attributes
        }
        assert "postgresql" in systems
    finally:
        runtime.shutdown()
        # Instrumentation attaches event listeners to the engine and this
        # engine is shared with other tests in the session. Removing them
        # again keeps the spans of one test out of another's exporter.
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor

        SQLAlchemyInstrumentor().uninstrument()
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `cd examples/reference-service && uv run pytest tests/integration/test_db_instrumentation.py -v -m integration`
Expected: FAIL with `ImportError: cannot import name 'instrument_database'`. Docker must be running.

- [ ] **Step 4: Add `instrument_database`**

In `observability/otel.py`, add the imports:

```python
from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
from sqlalchemy.ext.asyncio import AsyncEngine
```

and the function:

```python
def instrument_database(engine: AsyncEngine, runtime: OtelRuntime) -> None:
    """Add a span per statement to an async engine.

    `engine.sync_engine`, not `engine`: SQLAlchemyInstrumentor attaches to
    the synchronous core event system and does not accept an AsyncEngine
    at all. The async engine is a thin wrapper over exactly that core, so
    instrumenting the inner object covers every statement the outer one
    runs.

    Deliberately no meter_provider argument. The instrumentation's own
    connection-pool metrics duplicate the ones observability/metrics.py
    registers from the pool object directly, and the two disagree at the
    edges because they count at different moments. One source for a number
    is worth more than two nearly-right ones.
    """
    _opt_in_to_stable_semconv()
    SQLAlchemyInstrumentor().instrument(
        engine=engine.sync_engine, tracer_provider=runtime.tracer_provider
    )
```

- [ ] **Step 5: Call it from `lifespan` in `main.py`**

Inside `lifespan`, after `app.state.container = container` and before `container.started = True`:

```python
        if otel_runtime is not None and container.engine is not None:
            # Here rather than in create_app because the engine does not
            # exist until the container is built, and here rather than in
            # container.py because the composition root has no business
            # importing an SDK — container.py stays a module about wiring
            # adapters together.
            instrument_database(container.engine, otel_runtime)
```

- [ ] **Step 6: Run the test to verify it passes**

Run: `cd examples/reference-service && uv run pytest tests/integration/test_db_instrumentation.py -v -m integration`
Expected: PASS.

- [ ] **Step 7: Run everything**

Run: `cd examples/reference-service && uv run pytest && uv run pytest -m integration && uv run mypy && uv run lint-imports`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add examples/reference-service/src/reference_service/observability/otel.py examples/reference-service/src/reference_service/main.py examples/reference-service/tests/integration/test_db_instrumentation.py
git commit -m "feat(observability): trace sqlalchemy statements through the async engine"
```

---

## Task 6: Trace-to-log correlation

**Files:**
- Modify: `examples/reference-service/src/reference_service/observability/logging.py`
- Test: `examples/reference-service/tests/unit/test_logging.py`

**Interfaces:**
- Consumes: nothing from earlier tasks — the processor reads the *ambient* span from the OpenTelemetry context, so it works whatever built the provider.
- Produces: two new keys, `trace_id` and `span_id`, on every record emitted inside a span. Completes spec 7.6's field contract, whose only missing rows these were.

- [ ] **Step 1: Write the failing tests**

Append to `tests/unit/test_logging.py`:

```python
def test_a_record_inside_a_span_carries_the_trace_and_span_ids(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """The last two rows of spec 7.6's field contract.

    This is the whole point of trace-to-log correlation: given a slow
    trace in Tempo you can pivot straight to the log lines that request
    produced, and given an alarming log line you can pivot to its trace.
    """
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    configure_logging(environment="production", level="info", levels={})
    tracer = TracerProvider().get_tracer("test")

    with tracer.start_as_current_span("unit") as span:
        structlog.get_logger().info("order.placed")
        context = span.get_span_context()

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["trace_id"] == format(context.trace_id, "032x")
    assert payload["span_id"] == format(context.span_id, "016x")


def test_a_record_outside_any_span_carries_neither_key(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Not a cosmetic choice.

    Outside a span the context is the invalid one, whose trace_id is
    literally zero. Formatting it anyway would stamp
    trace_id="00000000000000000000000000000000" on every startup and
    shutdown line — a value that looks like a real identifier, matches
    nothing in Tempo, and groups every unrelated record in the service
    under one enormous fake trace.
    """
    configure_logging(environment="production", level="info", levels={})

    structlog.get_logger().info("app.starting")

    payload = json.loads(capsys.readouterr().out.strip())
    assert "trace_id" not in payload
    assert "span_id" not in payload


def test_a_standard_library_record_inside_a_span_is_correlated_too(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """uvicorn and SQLAlchemy lines must be pivotable, not just ours."""
    from opentelemetry import trace
    from opentelemetry.sdk.trace import TracerProvider

    configure_logging(environment="production", level="info", levels={})
    tracer = TracerProvider().get_tracer("test")

    with tracer.start_as_current_span("unit") as span:
        logging.getLogger("some.library").warning("connection retried")
        context = span.get_span_context()

    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["trace_id"] == format(context.trace_id, "032x")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_logging.py -k "span" -v`
Expected: FAIL — `KeyError: 'trace_id'` on the first and third; the second passes already but must keep passing.

- [ ] **Step 3: Add the processor**

In `observability/logging.py`, add the import:

```python
from opentelemetry import trace
```

and the processor, next to `_bind_resource_attributes`:

```python
def _add_otel_context(
    logger: Any, method_name: str, event_dict: MutableMapping[str, Any]
) -> MutableMapping[str, Any]:
    """Stamp the active trace and span identifiers onto the record.

    Reads the AMBIENT span from the OpenTelemetry context rather than any
    provider, so this works no matter who configured the SDK — and costs
    almost nothing when nobody did, because with telemetry off there is
    never a valid span and the function returns after one check.

    The `is_valid` guard is load-bearing. Outside a span the context is
    the invalid one, whose trace_id is the integer zero: formatting it
    regardless would put
    trace_id="00000000000000000000000000000000" on every record emitted
    at startup, shutdown, or from a background task. That value looks
    exactly like a real identifier, matches nothing in Tempo, and files
    every uncorrelated line in the service under a single enormous
    fictional trace.

    The 32- and 16-hex-digit formats are the W3C Trace Context wire
    formats, which is what Tempo indexes and what the Loki datasource in
    the local stack already has a derived-field link configured for.
    """
    context = trace.get_current_span().get_span_context()
    if context.is_valid:
        event_dict["trace_id"] = format(context.trace_id, "032x")
        event_dict["span_id"] = format(context.span_id, "016x")
    return event_dict
```

Then add it to `_shared_processors`, immediately after `_bind_resource_attributes(...)`:

```python
        _add_otel_context,
```

Placing it in `_shared_processors` rather than only in the structlog chain is
what makes the third test pass: `_shared_processors` is also the
`foreign_pre_chain`, so a record from uvicorn or SQLAlchemy is correlated
on the same terms as one of ours.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_logging.py -v`
Expected: PASS — the three new tests plus every M0/M1 logging test.

- [ ] **Step 5: Commit**

```bash
git add examples/reference-service/src/reference_service/observability/logging.py examples/reference-service/tests/unit/test_logging.py
git commit -m "feat(observability): stamp trace and span ids onto every log record"
```

---

## Task 7: OTLP log export, opt-in and additive

**Files:**
- Modify: `examples/reference-service/src/reference_service/observability/logging.py`
- Modify: `examples/reference-service/src/reference_service/main.py`
- Test: `examples/reference-service/tests/unit/test_otel_logs.py`

**Interfaces:**
- Consumes: `OtelRuntime.logger_provider` (Task 3), `_shared_processors` (existing).
- Produces: `configure_logging(..., logger_provider: LoggerProvider | None = None)`. The new keyword is the only signature change; every existing caller keeps working.

This is D15 in code: standard output stays the source of truth and OTLP is
added *beside* it, never instead of it.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_otel_logs.py`:

```python
"""OTLP log export (spec D15). Additive, opt-in, never a replacement."""

from __future__ import annotations

import json
import logging
from collections.abc import Iterator

import pytest
import structlog
from opentelemetry.sdk._logs import LoggerProvider
from opentelemetry.sdk._logs.export import (
    InMemoryLogRecordExporter,
    SimpleLogRecordProcessor,
)

from reference_service.observability.logging import configure_logging


@pytest.fixture(autouse=True)
def _reset_logging() -> Iterator[None]:
    yield
    structlog.reset_defaults()
    logging.getLogger().handlers.clear()


@pytest.fixture
def exporter() -> InMemoryLogRecordExporter:
    # InMemoryLogRecordExporter, NOT InMemoryLogExporter: the latter is
    # deprecated and emits a DeprecationWarning on import, which this
    # project's filterwarnings = ["error"] turns into a test failure.
    return InMemoryLogRecordExporter()


@pytest.fixture
def logger_provider(exporter: InMemoryLogRecordExporter) -> LoggerProvider:
    provider = LoggerProvider()
    provider.add_log_record_processor(SimpleLogRecordProcessor(exporter))
    return provider


def test_without_a_provider_nothing_is_exported(
    capsys: pytest.CaptureFixture[str], exporter: InMemoryLogRecordExporter
) -> None:
    """The default. Standard output only."""
    configure_logging(environment="production", level="info", levels={})

    structlog.get_logger().info("order.placed")

    assert capsys.readouterr().out.strip() != ""
    assert exporter.get_finished_logs() == ()


def test_with_a_provider_the_record_goes_BOTH_places(
    capsys: pytest.CaptureFixture[str],
    exporter: InMemoryLogRecordExporter,
    logger_provider: LoggerProvider,
) -> None:
    """D15: OTLP is added on top of standard output, not instead of it.

    Standard output survives a collector outage and captures crashes and
    anything failing before the SDK started, which is exactly the output
    you need when a service will not start. Losing it in exchange for
    OTLP would be a downgrade dressed as an upgrade.
    """
    configure_logging(
        environment="production",
        level="info",
        levels={},
        logger_provider=logger_provider,
    )

    structlog.get_logger().info("order.placed", order_id="abc")

    stdout_payload = json.loads(capsys.readouterr().out.strip())
    assert stdout_payload["event"] == "order.placed"

    exported = exporter.get_finished_logs()
    assert len(exported) == 1
    assert json.loads(exported[0].log_record.body)["order_id"] == "abc"


def test_the_exported_body_is_json_even_in_local_mode(
    exporter: InMemoryLogRecordExporter, logger_provider: LoggerProvider
) -> None:
    """Locally stdout is colourised console text for a human to read.

    A backend is not a human. The OTLP handler renders JSON regardless of
    environment, so what Loki stores is always machine-parseable and
    always the same shape as production.
    """
    configure_logging(
        environment="local",
        level="info",
        levels={},
        logger_provider=logger_provider,
    )

    structlog.get_logger().info("order.placed", order_id="abc")

    body = exporter.get_finished_logs()[0].log_record.body
    assert json.loads(body)["event"] == "order.placed"


def test_a_third_party_record_is_exported_too(
    exporter: InMemoryLogRecordExporter, logger_provider: LoggerProvider
) -> None:
    """One pipeline for every record, OTLP leg included."""
    configure_logging(
        environment="production",
        level="info",
        levels={},
        logger_provider=logger_provider,
    )

    logging.getLogger("some.library").warning("connection retried")

    body = exporter.get_finished_logs()[0].log_record.body
    assert json.loads(body)["logger"] == "some.library"
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_otel_logs.py -v`
Expected: FAIL with `TypeError: configure_logging() got an unexpected keyword argument 'logger_provider'` on three of the four.

- [ ] **Step 3: Extend `configure_logging`**

In `observability/logging.py`, add the imports:

```python
from opentelemetry.sdk._logs import LoggerProvider, LoggingHandler
```

Add the `logger_provider` parameter to `configure_logging`:

```python
    logger_provider: LoggerProvider | None = None,
```

and, at the end of the function body — after the root handler is installed
and before the per-logger levels loop — add:

```python
    if logger_provider is not None:
        # A SECOND handler on the same root logger, so every record goes to
        # standard output AND to OTLP. Standard output is the source of
        # truth (spec D15): it survives a collector outage and captures
        # crashes and any failure happening before the SDK initialised.
        # This leg exists so that locally a developer sees log lines beside
        # the matching trace in Grafana without wiring up a log scraper.
        #
        # Its own ProcessorFormatter instance, not the one above, for two
        # reasons. The renderer differs — a backend has no use for the
        # colourised console output `local` gets on stdout, so this leg is
        # always JSON — and two handlers formatting the same record through
        # one shared formatter object is a needless shared-mutation risk
        # for the sake of saving an allocation made once per process.
        #
        # trace_id and span_id are set on the OTLP record automatically by
        # LoggingHandler from the active span; the copies inside the JSON
        # body come from _add_otel_context and are for whoever reads the
        # body directly.
        otlp_handler = LoggingHandler(
            level=level.upper(), logger_provider=logger_provider
        )
        otlp_handler.setFormatter(
            structlog.stdlib.ProcessorFormatter(
                foreign_pre_chain=shared,
                processors=[
                    structlog.stdlib.ProcessorFormatter.remove_processors_meta,
                    structlog.processors.JSONRenderer(serializer=_json_dumps),
                ],
            )
        )
        root.addHandler(otlp_handler)
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_otel_logs.py tests/unit/test_logging.py -v`
Expected: PASS.

- [ ] **Step 5: Pass the provider from `main.py`**

In `create_app`, change the `configure_logging(...)` call to add one argument:

```python
        logger_provider=(
            otel_runtime.logger_provider if otel_runtime is not None else None
        ),
```

This is why Task 4 placed `configure_otel` above `configure_logging`.

- [ ] **Step 6: Run everything**

Run: `cd examples/reference-service && uv run pytest && uv run mypy && uv run lint-imports && uv run ruff check .`
Expected: all pass.

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service/src/reference_service/observability/logging.py examples/reference-service/src/reference_service/main.py examples/reference-service/tests/unit/test_otel_logs.py
git commit -m "feat(observability): add opt-in otlp log export beside standard output"
```

---

## Task 8: The saturation and runtime metrics

**Files:**
- Create: `examples/reference-service/src/reference_service/observability/metrics.py`
- Modify: `examples/reference-service/src/reference_service/observability/otel.py` (one more view)
- Modify: `examples/reference-service/src/reference_service/main.py` (start and stop them)
- Test: `examples/reference-service/tests/unit/test_metrics.py`

**Interfaces:**
- Consumes: `OtelRuntime` (Task 3), `Container.engine` (M1).
- Produces:
  - `register_runtime_metrics(runtime, *, service_version, engine=None) -> RuntimeMetrics`
  - `class RuntimeMetrics` with `async def stop() -> None`
  - Instruments: `service.info`, `db.client.connection.count`, `db.client.connection.max`, `event_loop.lag`, plus the selected process and garbage-collection metrics.

RED metrics come free from Task 4. This task adds what spec 7.4 calls the
signals that *predict* outages rather than describe them: a pool at its
ceiling and an event loop that has stopped keeping up both show minutes
before the error rate moves.

- [ ] **Step 1: Write the failing tests**

Create `tests/unit/test_metrics.py`:

```python
"""The saturation signals, read through an in-memory reader."""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from typing import Any

import pytest
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import InMemoryMetricReader
from opentelemetry.sdk.trace import TracerProvider
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from reference_service.observability.metrics import register_runtime_metrics
from reference_service.observability.otel import OtelRuntime, build_views


@pytest.fixture(autouse=True)
def _uninstrument_system_metrics() -> Iterator[None]:
    """SystemMetricsInstrumentor is a process-wide singleton.

    Left instrumented, the second test in this module gets
    "Attempting to instrument while already instrumented" and its meter
    provider never receives the process metrics.
    """
    yield
    from opentelemetry.instrumentation.system_metrics import (
        SystemMetricsInstrumentor,
    )

    SystemMetricsInstrumentor().uninstrument()


@pytest.fixture
def reader() -> InMemoryMetricReader:
    return InMemoryMetricReader()


@pytest.fixture
def runtime(reader: InMemoryMetricReader) -> OtelRuntime:
    return OtelRuntime(
        tracer_provider=TracerProvider(),
        meter_provider=MeterProvider(metric_readers=[reader], views=build_views()),
        logger_provider=None,
    )


@pytest.fixture
def engine() -> AsyncEngine:
    """No connection is opened by create_async_engine, so no database."""
    return create_async_engine(
        "postgresql+asyncpg://u:p@localhost:5432/db", pool_size=7, max_overflow=0
    )


def _points(reader: InMemoryMetricReader, name: str) -> list[Any]:
    return [
        point
        for resource_metrics in reader.get_metrics_data().resource_metrics
        for scope_metrics in resource_metrics.scope_metrics
        for metric in scope_metrics.metrics
        if metric.name == name
        for point in metric.data.data_points
    ]


async def test_service_info_reports_one_carrying_the_version(
    runtime: OtelRuntime, reader: InMemoryMetricReader
) -> None:
    """Spec 7.4: the metric that lets a dashboard annotate deployments.

    Its value is always 1 and carries no information. The information is
    the service_version label, promoted from the resource, which changes
    the instant a new release starts serving — so a latency step and the
    deployment that caused it land on the same chart.
    """
    metrics = register_runtime_metrics(runtime, service_version="1.2.3")
    try:
        assert [point.value for point in _points(reader, "service.info")] == [1]
    finally:
        await metrics.stop()


async def test_pool_gauges_report_used_idle_and_the_ceiling(
    runtime: OtelRuntime, reader: InMemoryMetricReader, engine: AsyncEngine
) -> None:
    """A pool at its ceiling is a queue, and a queue is latency.

    This is visible minutes before the error rate moves, which is the
    entire reason spec 7.4 asks for saturation beside RED.
    """
    metrics = register_runtime_metrics(runtime, service_version="1.2.3", engine=engine)
    try:
        states = {
            point.attributes["state"]: point.value
            for point in _points(reader, "db.client.connection.count")
        }
        assert states == {"used": 0, "idle": 0}

        assert [point.value for point in _points(reader, "db.client.connection.max")] == [7]
    finally:
        await metrics.stop()
        await engine.dispose()


async def test_no_pool_gauges_without_a_database(
    runtime: OtelRuntime, reader: InMemoryMetricReader
) -> None:
    """The in-memory adapter path must not report a pool it does not have."""
    metrics = register_runtime_metrics(runtime, service_version="1.2.3")
    try:
        assert _points(reader, "db.client.connection.count") == []
    finally:
        await metrics.stop()


async def test_event_loop_lag_is_recorded(
    runtime: OtelRuntime, reader: InMemoryMetricReader
) -> None:
    """Lag is how long a ready callback waited for the loop to reach it.

    It is the number that explains a service being slow while the
    database is fast and the CPU is idle: something is blocking the loop.
    """
    metrics = register_runtime_metrics(
        runtime, service_version="1.2.3", event_loop_probe_interval_seconds=0.01
    )
    try:
        await asyncio.sleep(0.05)
        points = _points(reader, "event_loop.lag")
        assert points, "the probe task recorded nothing"
        assert points[0].count >= 1
        assert points[0].sum >= 0.0
    finally:
        await metrics.stop()


async def test_stop_cancels_the_probe_task(runtime: OtelRuntime) -> None:
    """A task left running past shutdown keeps the loop alive."""
    metrics = register_runtime_metrics(
        runtime, service_version="1.2.3", event_loop_probe_interval_seconds=0.01
    )

    await metrics.stop()

    assert metrics.probe_task is not None
    assert metrics.probe_task.done()


async def test_stop_is_idempotent(runtime: OtelRuntime) -> None:
    metrics = register_runtime_metrics(runtime, service_version="1.2.3")

    await metrics.stop()
    await metrics.stop()


async def test_process_and_gc_metrics_are_present_but_not_the_host_ones(
    runtime: OtelRuntime, reader: InMemoryMetricReader
) -> None:
    """Verified fact 14: the instrumentor's defaults are wrong for us.

    Left at defaults it emits both the current names and their deprecated
    `process.runtime.cpython.*` duplicates, plus whole-host `system.*`
    series describing the developer's laptop rather than this service.
    """
    metrics = register_runtime_metrics(runtime, service_version="1.2.3")
    try:
        names = {
            metric.name
            for resource_metrics in reader.get_metrics_data().resource_metrics
            for scope_metrics in resource_metrics.scope_metrics
            for metric in scope_metrics.metrics
        }
        assert "process.memory.usage" in names
        assert "process.thread.count" in names
        assert "cpython.gc.collections" in names

        assert not [name for name in names if name.startswith("system.")]
        assert not [name for name in names if name.startswith("process.runtime.")]
    finally:
        await metrics.stop()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_metrics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'reference_service.observability.metrics'`.

- [ ] **Step 3: Add a view for the lag histogram**

In `observability/otel.py`, extend `build_views` to return two views:

```python
        View(
            instrument_name="event_loop.lag",
            aggregation=ExplicitBucketHistogramAggregation(
                # Finer at the bottom than the SDK default, which starts at
                # 5ms. A loop lagging 5ms is healthy; the interesting
                # question is whether it is lagging 1ms or 100ms, and the
                # default boundaries cannot tell those apart usefully.
                boundaries=(
                    0.001, 0.0025, 0.005, 0.01, 0.025, 0.05,
                    0.1, 0.25, 0.5, 1.0, 2.5, 5.0,
                )
            ),
        ),
```

Task 3's test filters views by instrument name, so it keeps passing.

- [ ] **Step 4: Write `observability/metrics.py`**

```python
"""Instruments this service reports about itself.

RED — rate, errors, duration — arrives free from the FastAPI
instrumentation. What is here instead is saturation: the signals that
move BEFORE the error rate does, which is what makes them worth a panel.
A connection pool sitting at its ceiling is a queue, and a queue is
latency that has not been served yet. An event loop that has stopped
keeping up is the explanation for a service being slow while the database
is fast and the processor is idle.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterable
from dataclasses import dataclass

from opentelemetry.instrumentation.system_metrics import SystemMetricsInstrumentor
from opentelemetry.metrics import CallbackOptions, Meter, Observation
from sqlalchemy.ext.asyncio import AsyncEngine

from reference_service.observability.otel import OtelRuntime

METER_NAME = "reference_service.runtime"

# How often the event loop is probed. Every tick is one histogram
# observation, so this trades resolution against series volume; two
# seconds is frequent enough to catch a blocking call inside one scrape
# interval and rare enough to be free.
DEFAULT_EVENT_LOOP_PROBE_INTERVAL_SECONDS = 2.0

# Exactly what dashboard 3 draws, and nothing else. The instrumentor's
# own defaults emit around thirty metrics: the current process and
# garbage-collection names, their deprecated `process.runtime.cpython.*`
# duplicates carrying the SAME numbers under different names, and a set
# of whole-host `system.*` series that describe the machine rather than
# this service — actively misleading in a container, where the host is
# shared with everything else on the node.
_PROCESS_METRICS_CONFIG: dict[str, list[str] | None] = {
    "process.cpu.utilization": ["user", "system"],
    "process.memory.usage": None,
    "process.memory.virtual": None,
    "process.open_file_descriptor.count": None,
    "process.thread.count": None,
    "cpython.gc.collections": None,
    "cpython.gc.collected_objects": None,
    "cpython.gc.uncollectable_objects": None,
}


@dataclass
class RuntimeMetrics:
    """Handle for the one thing here that needs stopping."""

    probe_task: asyncio.Task[None] | None

    async def stop(self) -> None:
        """Cancel the probe and wait for it to actually finish.

        Awaiting the cancellation rather than firing and forgetting is
        what makes shutdown deterministic: an un-awaited cancelled task
        can still be pending when the loop closes, which asyncio reports
        as "Task was destroyed but it is pending" on the way out — noise
        in exactly the logs someone is reading to find out why shutdown
        went wrong. Safe to call twice; lifespan's finally block may run
        after a startup that already failed.
        """
        if self.probe_task is None or self.probe_task.done():
            return
        self.probe_task.cancel()
        try:
            await self.probe_task
        except asyncio.CancelledError:
            # Ours, and expected: we asked for it one line above.
            pass


def _register_service_info(meter: Meter, service_version: str) -> None:
    """A constant 1 whose labels are the point (spec 7.4).

    The value never changes and means nothing. `service_version` — which
    Prometheus promotes from the resource onto every series — changes the
    moment a new release starts serving, so a dashboard can draw the
    deployment as a marker and put a latency step beside its cause.

    An OBSERVABLE gauge rather than a plain one: a plain gauge set once
    depends on the SDK holding that last value for the life of the
    process, whereas a callback is asked afresh on every collection and
    cannot go stale.
    """

    def observe(options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(1, {"service.version": service_version})

    meter.create_observable_gauge(
        "service.info",
        callbacks=[observe],
        unit="{info}",
        description="Always 1. Carries the running version as a label.",
    )


def _register_pool_metrics(meter: Meter, engine: AsyncEngine) -> None:
    """Connections in use, idle, and the hard ceiling.

    Read straight off the pool object rather than taken from the
    SQLAlchemy instrumentation's own pool metrics, which measure at a
    different moment and would disagree at the edges. One number with one
    source beats two nearly-right ones.

    `db.client.connection.count` with a `state` attribute is the
    OpenTelemetry convention, so this panel works unchanged against a
    service written in another language.

    build_engine pins max_overflow to 0, which is what makes `max` an
    exact ceiling rather than a floor — see its comment in
    infrastructure/db/engine.py.
    """

    def observe_count(options: CallbackOptions) -> Iterable[Observation]:
        pool = engine.pool
        yield Observation(pool.checkedout(), {"state": "used"})
        yield Observation(pool.checkedin(), {"state": "idle"})

    def observe_max(options: CallbackOptions) -> Iterable[Observation]:
        yield Observation(engine.pool.size())

    meter.create_observable_gauge(
        "db.client.connection.count",
        callbacks=[observe_count],
        unit="{connection}",
        description="Connections currently checked out of, or idle in, the pool.",
    )
    meter.create_observable_gauge(
        "db.client.connection.max",
        callbacks=[observe_max],
        unit="{connection}",
        description="The pool ceiling. Exact, because max_overflow is 0.",
    )


async def _probe_event_loop_lag(histogram: Any, interval_seconds: float) -> None:
    """Sleep a known interval and record how much longer it really took.

    That overshoot IS the lag: the time between the sleep becoming ready
    and the loop getting round to it. On an idle loop it is microseconds.
    When something synchronous blocks — a large JSON parse, a driver
    without an async path, a call that forgot its `await` — it climbs
    immediately, while every other signal still looks fine.

    `loop.time()` rather than `time.perf_counter()` because it is the
    same clock asyncio schedules against, so the subtraction has no
    cross-clock error in it.
    """
    loop = asyncio.get_running_loop()
    while True:
        started = loop.time()
        await asyncio.sleep(interval_seconds)
        lag = loop.time() - started - interval_seconds
        # Clamped: a clock adjustment can make this microscopically
        # negative, and a negative observation on a histogram is an error
        # the SDK logs rather than a number anyone can use.
        histogram.record(max(lag, 0.0))


def register_runtime_metrics(
    runtime: OtelRuntime,
    *,
    service_version: str,
    engine: AsyncEngine | None = None,
    event_loop_probe_interval_seconds: float = (
        DEFAULT_EVENT_LOOP_PROBE_INTERVAL_SECONDS
    ),
) -> RuntimeMetrics:
    """Register every instrument and start the event loop probe.

    Must be called from inside a running event loop — the probe task
    needs one — which is why `lifespan` calls it rather than `create_app`.
    """
    meter = runtime.meter_provider.get_meter(METER_NAME)

    _register_service_info(meter, service_version)
    if engine is not None:
        _register_pool_metrics(meter, engine)

    SystemMetricsInstrumentor(config=_PROCESS_METRICS_CONFIG).instrument(
        meter_provider=runtime.meter_provider
    )

    lag = meter.create_histogram(
        "event_loop.lag",
        unit="s",
        description="How long a ready callback waited for the event loop.",
    )
    return RuntimeMetrics(
        probe_task=asyncio.create_task(
            _probe_event_loop_lag(lag, event_loop_probe_interval_seconds),
            name="event-loop-lag-probe",
        )
    )
```

Add `from typing import Any` to the imports for `_probe_event_loop_lag`'s
histogram parameter — the SDK's `Histogram` type is not exported in a form
mypy accepts cleanly here, and this module is outside the strict-mypy set.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_metrics.py -v`
Expected: PASS, 7 tests.

- [ ] **Step 6: Start and stop them from `lifespan`**

In `main.py`, add the import:

```python
from reference_service.observability.metrics import (
    RuntimeMetrics,
    register_runtime_metrics,
)
```

In `lifespan`, replace the database-instrumentation block added in Task 5 with:

```python
        runtime_metrics: RuntimeMetrics | None = None
        if otel_runtime is not None:
            if container.engine is not None:
                instrument_database(container.engine, otel_runtime)
            # Here, not in create_app: the probe task needs a running
            # event loop, and create_app runs before there is one.
            runtime_metrics = register_runtime_metrics(
                otel_runtime,
                service_version=__version__,
                engine=container.engine,
            )
```

and in the `finally` block, before the `otel_runtime.shutdown()` call:

```python
            if runtime_metrics is not None:
                # Before the providers shut down, so the final collection
                # still has instruments to read.
                await runtime_metrics.stop()
```

- [ ] **Step 7: Run everything**

Run: `cd examples/reference-service && uv run pytest && uv run mypy && uv run lint-imports && uv run ruff check .`
Expected: all pass.

- [ ] **Step 8: Commit**

```bash
git add examples/reference-service/src/reference_service/observability/metrics.py examples/reference-service/src/reference_service/observability/otel.py examples/reference-service/src/reference_service/main.py examples/reference-service/tests/unit/test_metrics.py
git commit -m "feat(observability): report pool saturation, event loop lag and service info"
```

---

## Task 9: Prometheus configuration, SLO rules, and the gate that keeps them honest

**Files:**
- Create: `examples/reference-service/ops/prometheus/prometheus.yaml`
- Create: `examples/reference-service/ops/prometheus/rules/slo.yml`
- Create: `examples/reference-service/ops/prometheus/rules/slo_test.yml`
- Test: `examples/reference-service/tests/unit/test_slo_rules.py`

**Interfaces:**
- Consumes: every constant in `observability/slo.py` (Task 2); the metric and label names in Verified Facts 4.
- Produces: recording rules named `job:slo_availability_errors:ratio_rate<window>` and `job:slo_latency_errors:ratio_rate<window>` for the windows `5m 30m 1h 6h 3d 30d`, and three alerts. Task 10's dashboards query these names; Task 11 mounts these files.

**Why a replacement `prometheus.yaml` at all.** Verified fact 12: the image
starts Prometheus with `--config.file=./prometheus.yaml`, and the shipped
file has an `otlp:` block, a `storage:` block, and **no `rule_files` key**.
There is no other way in — no scrape config to attach to, no rules
directory it already watches. So the config is replaced wholesale, keeping
the two blocks it already had.

- [ ] **Step 1: Write the Prometheus configuration**

Create `ops/prometheus/prometheus.yaml`:

```yaml
---
# Replaces the copy inside grafana/otel-lgtm, which is started with
# --config.file=./prometheus.yaml and ships with NO rule_files key at all.
# The otlp and storage blocks below are that file's, kept verbatim: drop
# them and resource attributes stop becoming labels, which silently breaks
# every `job=` and `service_version=` matcher in the rules and dashboards.
otlp:
  keep_identifying_resource_attributes: true
  promote_resource_attributes:
    - service.instance.id
    - service.name
    - service.namespace
    - service.version
    # NOT `deployment.environment`. The current semantic convention is the
    # `.name` form and this promotion list is what decides which resource
    # attributes become labels — which is why observability/otel.py's
    # build_resource sets both spellings.
    - deployment.environment.name

storage:
  tsdb:
    # Absorbs export retries and network delay. A metric arriving a few
    # minutes late is still worth having.
    out_of_order_time_window: 10m

rule_files:
  - /otel-lgtm/rules/*.yml
```

- [ ] **Step 2: Write the SLO rules**

Create `ops/prometheus/rules/slo.yml`:

```yaml
---
# Service level objectives for the reference service.
#
# EVERY NUMBER BELOW IS ALSO A PYTHON CONSTANT in
# src/reference_service/observability/slo.py, and
# tests/unit/test_slo_rules.py fails if the two disagree. Change one, change
# the other, or the gate stops the commit.
#
#   availability target  99.9% of requests do not return 5xx
#   latency target       99.9% of requests finish within 300ms
#   window               rolling 30 days
#   error budget         0.001 of requests
#
# The `le="0.3"` matcher in the latency rules only works because
# observability/otel.py adds an explicit 0.3 histogram bucket boundary.
# The OpenTelemetry default boundaries step from 0.25 straight to 0.5, and
# without that view this series does not exist and every latency rule
# below silently evaluates to nothing.
#
# /healthz, /readyz and /startupz are excluded from both indicators. An
# orchestrator probes them every couple of seconds forever; counted, a
# service serving ten real requests a minute beside eighteen hundred
# probes reports a healthy objective while failing every request a user
# actually makes.

groups:
  # Short windows: the fast half of each burn-rate pair, evaluated often
  # because they are what makes a page arrive within minutes.
  - name: slo_sli_short
    interval: 30s
    rules:
      - record: job:slo_availability_errors:ratio_rate5m
        expr: |
          sum by (job) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5..",http_route!~"/healthz|/readyz|/startupz"}[5m]))
          /
          sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[5m]))

      - record: job:slo_availability_errors:ratio_rate30m
        expr: |
          sum by (job) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5..",http_route!~"/healthz|/readyz|/startupz"}[30m]))
          /
          sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[30m]))

      - record: job:slo_availability_errors:ratio_rate1h
        expr: |
          sum by (job) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5..",http_route!~"/healthz|/readyz|/startupz"}[1h]))
          /
          sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[1h]))

      - record: job:slo_latency_errors:ratio_rate5m
        expr: |
          1 - (
            sum by (job) (rate(http_server_request_duration_seconds_bucket{le="0.3",http_route!~"/healthz|/readyz|/startupz"}[5m]))
            /
            sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[5m]))
          )

      - record: job:slo_latency_errors:ratio_rate30m
        expr: |
          1 - (
            sum by (job) (rate(http_server_request_duration_seconds_bucket{le="0.3",http_route!~"/healthz|/readyz|/startupz"}[30m]))
            /
            sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[30m]))
          )

      - record: job:slo_latency_errors:ratio_rate1h
        expr: |
          1 - (
            sum by (job) (rate(http_server_request_duration_seconds_bucket{le="0.3",http_route!~"/healthz|/readyz|/startupz"}[1h]))
            /
            sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[1h]))
          )

  # Long windows. Evaluated every five minutes rather than every thirty
  # seconds: a `rate(...[30d])` is expensive and a number covering thirty
  # days does not change meaningfully in half a minute.
  - name: slo_sli_long
    interval: 5m
    rules:
      - record: job:slo_availability_errors:ratio_rate6h
        expr: |
          sum by (job) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5..",http_route!~"/healthz|/readyz|/startupz"}[6h]))
          /
          sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[6h]))

      - record: job:slo_availability_errors:ratio_rate3d
        expr: |
          sum by (job) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5..",http_route!~"/healthz|/readyz|/startupz"}[3d]))
          /
          sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[3d]))

      - record: job:slo_availability_errors:ratio_rate30d
        expr: |
          sum by (job) (rate(http_server_request_duration_seconds_count{http_response_status_code=~"5..",http_route!~"/healthz|/readyz|/startupz"}[30d]))
          /
          sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[30d]))

      - record: job:slo_latency_errors:ratio_rate6h
        expr: |
          1 - (
            sum by (job) (rate(http_server_request_duration_seconds_bucket{le="0.3",http_route!~"/healthz|/readyz|/startupz"}[6h]))
            /
            sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[6h]))
          )

      - record: job:slo_latency_errors:ratio_rate3d
        expr: |
          1 - (
            sum by (job) (rate(http_server_request_duration_seconds_bucket{le="0.3",http_route!~"/healthz|/readyz|/startupz"}[3d]))
            /
            sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[3d]))
          )

      - record: job:slo_latency_errors:ratio_rate30d
        expr: |
          1 - (
            sum by (job) (rate(http_server_request_duration_seconds_bucket{le="0.3",http_route!~"/healthz|/readyz|/startupz"}[30d]))
            /
            sum by (job) (rate(http_server_request_duration_seconds_count{http_route!~"/healthz|/readyz|/startupz"}[30d]))
          )

  # Multi-window, multi-burn-rate alerting, from Google's Site Reliability
  # Engineering workbook.
  #
  # The idea, in one paragraph. Alerting when the error rate crosses a fixed
  # line either pages constantly during harmless blips or stays silent
  # through a slow bleed, depending on where the line is put. Burn rate
  # asks a better question: how fast is the error budget being spent? A
  # burn rate of 1 spends the whole 30-day budget in exactly 30 days. A
  # burn rate of 14.4 spends 2% of it in an hour.
  #
  # Each alert requires a LONG window and a SHORT window to be over the
  # threshold at the same time. The long window is the signal — something
  # is genuinely wrong. The short window is the reset — it drops back
  # quickly once the problem stops, so the alert clears instead of
  # smouldering for hours after recovery. Neither window alone gives both
  # properties, which is the entire reason there are two.
  - name: slo_burn_alerts
    rules:
      - alert: SLOAvailabilityFastBurn
        # 2% of the 30-day budget in one hour.
        expr: |
          job:slo_availability_errors:ratio_rate1h > (14.4 * 0.001)
          and
          job:slo_availability_errors:ratio_rate5m > (14.4 * 0.001)
        for: 2m
        labels:
          severity: page
          slo: availability
        annotations:
          summary: "{{ $labels.job }} is burning its availability budget 14.4x too fast"
          description: >-
            At this rate the entire 30-day error budget is gone in about two
            days. Something is broken now, not drifting.

      - alert: SLOAvailabilitySlowBurn
        # 5% of the budget in six hours.
        expr: |
          job:slo_availability_errors:ratio_rate6h > (6 * 0.001)
          and
          job:slo_availability_errors:ratio_rate30m > (6 * 0.001)
        for: 15m
        labels:
          severity: page
          slo: availability
        annotations:
          summary: "{{ $labels.job }} is burning its availability budget 6x too fast"
          description: >-
            Sustained elevated errors. Slower than a fast burn, still fast
            enough to exhaust the month's budget in five days.

      - alert: SLOAvailabilityBudgetBleed
        # 10% of the budget in three days: a ticket, not a page.
        expr: |
          job:slo_availability_errors:ratio_rate3d > (1 * 0.001)
          and
          job:slo_availability_errors:ratio_rate6h > (1 * 0.001)
        for: 1h
        labels:
          severity: ticket
          slo: availability
        annotations:
          summary: "{{ $labels.job }} is steadily spending its availability budget"
          description: >-
            Nothing is on fire and the budget is still draining. Worth an
            engineer's morning, not their night.

      - alert: SLOLatencyFastBurn
        expr: |
          job:slo_latency_errors:ratio_rate1h > (14.4 * 0.001)
          and
          job:slo_latency_errors:ratio_rate5m > (14.4 * 0.001)
        for: 2m
        labels:
          severity: page
          slo: latency
        annotations:
          summary: "{{ $labels.job }} is burning its latency budget 14.4x too fast"
          description: >-
            Requests are returning, just not within 300ms. Check saturation
            first: pool usage and event loop lag move before this does.

      - alert: SLOLatencyBudgetBleed
        expr: |
          job:slo_latency_errors:ratio_rate3d > (1 * 0.001)
          and
          job:slo_latency_errors:ratio_rate6h > (1 * 0.001)
        for: 1h
        labels:
          severity: ticket
          slo: latency
        annotations:
          summary: "{{ $labels.job }} is steadily spending its latency budget"
          description: >-
            A slow drift towards the 300ms threshold. Often a dataset
            growing rather than anything that broke.
```

- [ ] **Step 3: Write the `promtool` rule unit tests**

Create `ops/prometheus/rules/slo_test.yml`:

```yaml
---
# Unit tests for slo.yml, run by `promtool test rules`. Synthetic series
# in, expected rule output out — no running service required.
#
# These are not decoration. The health-endpoint exclusion is a matcher in
# a string inside a YAML file: nothing else in this repository would
# notice if a future edit dropped it, and the symptom would be an
# objective that reports 99.99% forever while users see failures.

rule_files:
  - slo.yml

evaluation_interval: 1m

tests:
  # 9 successes and 1 server error per minute is a 10% error ratio, and
  # 1000 readiness probes per minute must not change that.
  - interval: 1m
    name: health probe traffic does not dilute the error ratio
    input_series:
      - series: 'http_server_request_duration_seconds_count{job="reference-service",http_route="/api/v1/orders",http_response_status_code="200"}'
        values: "0+9x20"
      - series: 'http_server_request_duration_seconds_count{job="reference-service",http_route="/api/v1/orders",http_response_status_code="500"}'
        values: "0+1x20"
      - series: 'http_server_request_duration_seconds_count{job="reference-service",http_route="/readyz",http_response_status_code="200"}'
        values: "0+1000x20"
    promql_expr_test:
      - expr: job:slo_availability_errors:ratio_rate5m
        eval_time: 20m
        exp_samples:
          - labels: 'job:slo_availability_errors:ratio_rate5m{job="reference-service"}'
            value: 0.1

  # Every request slower than the threshold: the latency indicator must
  # read 100% bad, not 0%. Gets the direction of the `1 - (...)` right.
  - interval: 1m
    name: requests above the threshold are latency errors
    input_series:
      - series: 'http_server_request_duration_seconds_count{job="reference-service",http_route="/api/v1/orders",http_response_status_code="200"}'
        values: "0+10x20"
      # Nothing landed in the 0.3 bucket, so every request was slower.
      - series: 'http_server_request_duration_seconds_bucket{job="reference-service",http_route="/api/v1/orders",http_response_status_code="200",le="0.3"}'
        values: "0+0x20"
    promql_expr_test:
      - expr: job:slo_latency_errors:ratio_rate5m
        eval_time: 20m
        exp_samples:
          - labels: 'job:slo_latency_errors:ratio_rate5m{job="reference-service"}'
            value: 1

  # And the healthy direction: everything inside the threshold is 0 bad.
  - interval: 1m
    name: requests below the threshold are not latency errors
    input_series:
      - series: 'http_server_request_duration_seconds_count{job="reference-service",http_route="/api/v1/orders",http_response_status_code="200"}'
        values: "0+10x20"
      - series: 'http_server_request_duration_seconds_bucket{job="reference-service",http_route="/api/v1/orders",http_response_status_code="200",le="0.3"}'
        values: "0+10x20"
    promql_expr_test:
      - expr: job:slo_latency_errors:ratio_rate5m
        eval_time: 20m
        exp_samples:
          - labels: 'job:slo_latency_errors:ratio_rate5m{job="reference-service"}'
            value: 0

  # A sustained 100% error rate must page, and must page on the FAST rule
  # rather than waiting for a long window to catch up.
  - interval: 1m
    name: a total outage triggers the fast burn page
    input_series:
      - series: 'http_server_request_duration_seconds_count{job="reference-service",http_route="/api/v1/orders",http_response_status_code="500"}'
        values: "0+10x120"
    alert_rule_test:
      - eval_time: 90m
        alertname: SLOAvailabilityFastBurn
        exp_alerts:
          - exp_labels:
              severity: page
              slo: availability
              job: reference-service
            exp_annotations:
              summary: "reference-service is burning its availability budget 14.4x too fast"
              description: >-
                At this rate the entire 30-day error budget is gone in about
                two days. Something is broken now, not drifting.
```

- [ ] **Step 4: Run `promtool` and iterate until green**

Run:

```bash
cd examples/reference-service && docker run --rm -v "$PWD/ops/prometheus/rules:/rules" \
  --entrypoint sh grafana/otel-lgtm:0.11.11 \
  -c 'cd /rules && /otel-lgtm/prometheus/promtool check rules slo.yml && /otel-lgtm/prometheus/promtool test rules slo_test.yml'
```

Expected: `SUCCESS: 17 rules found` then `SUCCESS` for the tests.

If the alert test fails on annotation text, `promtool` compares the
*rendered* string. Copy the exact rendering out of the failure message
rather than guessing how the YAML folded block collapsed its newlines.

- [ ] **Step 5: Write the drift gate**

Create `tests/unit/test_slo_rules.py`:

```python
"""The gate: the shipped PromQL and the Python constants must agree.

Every SLO number lives twice — once in observability/slo.py where the code
reads it, once in ops/prometheus/rules/slo.yml where Prometheus reads it.
Nothing at runtime would notice them diverging. The symptom of divergence
is the worst kind there is: an objective that reports a comfortable number
while users experience something else.

Pure Python and no Docker, so this runs in the fast tier on every commit.
`just gates` runs promtool over the same files in the container tier.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from reference_service.observability.slo import (
    ERROR_BUDGET,
    SLO_LATENCY_THRESHOLD_SECONDS,
    excluded_routes_pattern,
)

RULES_FILE = (
    Path(__file__).resolve().parents[2] / "ops" / "prometheus" / "rules" / "slo.yml"
)


@pytest.fixture(scope="module")
def rules() -> list[dict[str, Any]]:
    document = yaml.safe_load(RULES_FILE.read_text())
    return [rule for group in document["groups"] for rule in group["rules"]]


def _expressions(rules: list[dict[str, Any]]) -> list[str]:
    return [rule["expr"] for rule in rules]


def test_the_rules_file_is_where_this_test_thinks_it_is() -> None:
    """Guards the other tests: a moved file must fail loudly, not vacuously.

    Without this, relocating ops/ makes `rules` an empty list and every
    assertion below passes by having nothing to check.
    """
    assert RULES_FILE.is_file(), f"{RULES_FILE} not found"


def test_every_latency_bucket_matcher_uses_the_python_threshold(
    rules: list[dict[str, Any]],
) -> None:
    """`le="0.3"` and SLO_LATENCY_THRESHOLD_SECONDS are one number.

    Compared as floats, not strings: Prometheus renders bucket boundaries
    with the shortest representation that round-trips, so a threshold of
    1.0 is stored as le="1" while Python's str() gives "1.0".
    """
    found = [
        float(value)
        for expression in _expressions(rules)
        for value in re.findall(r'le="([0-9.]+)"', expression)
    ]

    assert found, "no le= matcher found at all; the latency rules are missing"
    assert set(found) == {SLO_LATENCY_THRESHOLD_SECONDS}


def test_every_burn_rate_threshold_uses_the_python_error_budget(
    rules: list[dict[str, Any]],
) -> None:
    """The alerts are written as `<burn rate> * <error budget>`.

    Keeping the multiplication visible in the PromQL is deliberate: a
    bare 0.0144 says nothing about where it came from, and nobody can
    review a number whose origin is invisible.
    """
    budgets = [
        float(value)
        for rule in rules
        if "alert" in rule
        for value in re.findall(r"\*\s*([0-9.]+)\)", rule["expr"])
    ]

    assert budgets, "no burn-rate threshold found; the alerts are missing"
    assert set(budgets) == {ERROR_BUDGET}


def test_every_sli_rule_excludes_the_health_endpoints(
    rules: list[dict[str, Any]],
) -> None:
    """The exclusion is a string in a YAML file and nothing else guards it.

    Dropped, the objective silently starts measuring readiness probes —
    which never fail — and reports a healthy service forever.
    """
    pattern = excluded_routes_pattern()
    recording_rules = [rule for rule in rules if "record" in rule]

    assert recording_rules, "no recording rules found"
    for rule in recording_rules:
        assert f'http_route!~"{pattern}"' in rule["expr"], (
            f"{rule['record']} does not exclude the health endpoints"
        )


def test_every_window_an_alert_uses_has_a_recording_rule(
    rules: list[dict[str, Any]],
) -> None:
    """A typo in an alert's window is otherwise invisible.

    PromQL against a series that does not exist is not an error; it is an
    empty result, and an empty result never fires. The alert would simply
    never trigger, and nothing would ever say so.
    """
    recorded = {rule["record"] for rule in rules if "record" in rule}
    referenced = {
        name
        for rule in rules
        if "alert" in rule
        for name in re.findall(r"job:slo_\w+:ratio_rate\w+", rule["expr"])
    }

    assert referenced, "no alert references a recording rule"
    assert referenced <= recorded, f"alerts reference missing rules: {referenced - recorded}"


def test_both_indicators_are_alerted_on(rules: list[dict[str, Any]]) -> None:
    """Spec 7.5 names two indicators; two objectives need two alerts."""
    slos = {rule["labels"]["slo"] for rule in rules if "alert" in rule}

    assert slos == {"availability", "latency"}
```

- [ ] **Step 6: Run the gate**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_slo_rules.py -v`
Expected: PASS, 6 tests.

Then prove the gate actually bites: temporarily change
`SLO_LATENCY_THRESHOLD_SECONDS` to `0.5`, re-run, and confirm
`test_every_latency_bucket_matcher_uses_the_python_threshold` fails.
Change it back. A gate nobody has watched fail is a gate nobody knows works.

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service/ops examples/reference-service/tests/unit/test_slo_rules.py
git commit -m "feat(observability): add slo recording rules, burn-rate alerts and a drift gate"
```

---

## Task 10: Three dashboards

**Files:**
- Create: `examples/reference-service/ops/grafana/provisioning/dashboards/pyfr-dashboards.yaml`
- Create: `examples/reference-service/ops/grafana/dashboards/service-health.json`
- Create: `examples/reference-service/ops/grafana/dashboards/slo.json`
- Create: `examples/reference-service/ops/grafana/dashboards/runtime.json`
- Test: `examples/reference-service/tests/unit/test_dashboards.py`

**Interfaces:**
- Consumes: the Prometheus series in Verified Fact 4, the instruments from Task 8, and the recording rule names from Task 9.
- Produces: three dashboards with the UIDs `pyfr-service-health`, `pyfr-slo`, `pyfr-runtime`. Task 11 mounts them and asserts Grafana loaded all three.

**Why every panel uses a `$service` variable and no hard-coded name.** Spec
3.4: at templatisation these files are copied *verbatim*, not rendered
through Jinja, precisely because they contain Grafana's own `{{ }}` syntax.
That only works if the JSON is already service-agnostic — one hard-coded
`job="reference-service"` and every generated project ships a dashboard
showing somebody else's service.

- [ ] **Step 1: Discover the real Prometheus names first**

Do not write a PromQL expression against a series name you have not seen.
The translation from an OpenTelemetry metric name to a Prometheus one
appends the unit and replaces dots, and the details differ per instrument
type. Get the list from the running stack:

```bash
docker rm -f pyfr-names >/dev/null 2>&1; docker run -d --name pyfr-names -p 4317:4317 grafana/otel-lgtm:0.11.11
```

Wait about 30 seconds, then run the reference service against it:

```bash
cd examples/reference-service && APP_OTEL__ENABLED=true APP_OTEL__ENDPOINT=http://localhost:4317 \
  APP_OTEL__METRIC_EXPORT_INTERVAL_MS=5000 uv run uvicorn reference_service.main:create_app \
  --factory --port 8000
```

In another terminal make a few requests (`curl localhost:8000/api/v1/orders/x`),
wait ten seconds, then:

```bash
docker exec pyfr-names curl -s 'http://127.0.0.1:9090/api/v1/label/__name__/values'
```

Write the exact names down. The ones below were confirmed this way while
this plan was written and should match:

| OpenTelemetry instrument | Prometheus series |
|---|---|
| `http.server.request.duration` | `http_server_request_duration_seconds_bucket` / `_count` / `_sum` |
| `http.server.active_requests` | `http_server_active_requests` |
| `service.info` | `service_info` |
| `db.client.connection.count` | `db_client_connection_count` |
| `db.client.connection.max` | `db_client_connection_max` |
| `event_loop.lag` | `event_loop_lag_seconds_bucket` / `_count` / `_sum` |
| `process.memory.usage` | `process_memory_usage_bytes` |
| `process.thread.count` | `process_thread_count` |
| `cpython.gc.collections` | `cpython_gc_collections_total` |

If any row disagrees with what the command printed, **the command wins** —
correct the dashboard, and correct this table in the plan so the next
reader is not misled. Then `docker rm -f pyfr-names`.

- [ ] **Step 2: Write the provisioning file**

Create `ops/grafana/provisioning/dashboards/pyfr-dashboards.yaml`:

```yaml
---
# Grafana scans the directory below on start and on an interval, so
# editing a dashboard JSON on the host shows up without restarting the
# container.
#
# This is the ONLY file in ops/grafana that M7 renders through Jinja. The
# dashboards themselves are copied verbatim — they contain Grafana's own
# {{ }} legend syntax, which Jinja would eat (spec 3.4).
apiVersion: 1

providers:
  - name: "pyfr"
    orgId: 1
    folder: "PyFr"
    type: file
    disableDeletion: false
    updateIntervalSeconds: 10
    allowUiUpdates: true
    options:
      path: /otel-lgtm/pyfr-dashboards
      foldersFromFilesStructure: false
```

- [ ] **Step 3: Write `service-health.json`**

This is the worked example; the other two follow its shape exactly.
Create `ops/grafana/dashboards/service-health.json`:

```json
{
  "uid": "pyfr-service-health",
  "title": "Service health",
  "tags": ["pyfr"],
  "timezone": "browser",
  "schemaVersion": 39,
  "version": 1,
  "refresh": "10s",
  "time": { "from": "now-1h", "to": "now" },
  "templating": {
    "list": [
      {
        "name": "service",
        "label": "Service",
        "type": "query",
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "query": {
          "qryType": 1,
          "query": "label_values(http_server_request_duration_seconds_count, job)",
          "refId": "PrometheusVariableQueryEditor-VariableQuery"
        },
        "refresh": 1,
        "includeAll": false,
        "multi": false,
        "current": {},
        "options": []
      }
    ]
  },
  "annotations": {
    "list": [
      {
        "name": "Deployments",
        "enable": true,
        "iconColor": "blue",
        "datasource": { "type": "prometheus", "uid": "prometheus" },
        "expr": "sum by (service_version) (service_info{job=\"$service\"})",
        "titleFormat": "Deployed",
        "textFormat": "{{service_version}}"
      }
    ]
  },
  "panels": [
    {
      "type": "timeseries",
      "title": "Request rate",
      "description": "Requests per second by route template. Never by raw path: one series per order id is how a metrics backend is destroyed.",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 0 },
      "fieldConfig": { "defaults": { "unit": "reqps" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "sum by (http_route) (rate(http_server_request_duration_seconds_count{job=\"$service\"}[$__rate_interval]))",
          "legendFormat": "{{http_route}}"
        }
      ]
    },
    {
      "type": "timeseries",
      "title": "Error rate",
      "description": "Percentage of requests returning 5xx. This is the availability indicator, before the health endpoints are excluded.",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 0 },
      "fieldConfig": {
        "defaults": { "unit": "percent", "min": 0 },
        "overrides": []
      },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "100 * sum(rate(http_server_request_duration_seconds_count{job=\"$service\",http_response_status_code=~\"5..\"}[$__rate_interval])) / sum(rate(http_server_request_duration_seconds_count{job=\"$service\"}[$__rate_interval]))",
          "legendFormat": "5xx"
        }
      ]
    },
    {
      "type": "timeseries",
      "title": "Latency percentiles",
      "description": "p50, p95 and p99 of http.server.request.duration. The SLO threshold is drawn as a line: crossing it is the latency budget being spent.",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "h": 8, "w": 12, "x": 0, "y": 8 },
      "fieldConfig": {
        "defaults": {
          "unit": "s",
          "min": 0,
          "thresholds": {
            "mode": "absolute",
            "steps": [
              { "color": "green", "value": null },
              { "color": "red", "value": 0.3 }
            ]
          }
        },
        "overrides": []
      },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "histogram_quantile(0.50, sum by (le) (rate(http_server_request_duration_seconds_bucket{job=\"$service\"}[$__rate_interval])))",
          "legendFormat": "p50"
        },
        {
          "refId": "B",
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "histogram_quantile(0.95, sum by (le) (rate(http_server_request_duration_seconds_bucket{job=\"$service\"}[$__rate_interval])))",
          "legendFormat": "p95"
        },
        {
          "refId": "C",
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "histogram_quantile(0.99, sum by (le) (rate(http_server_request_duration_seconds_bucket{job=\"$service\"}[$__rate_interval])))",
          "legendFormat": "p99"
        }
      ]
    },
    {
      "type": "timeseries",
      "title": "Responses by status",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "h": 8, "w": 12, "x": 12, "y": 8 },
      "fieldConfig": { "defaults": { "unit": "reqps" }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "sum by (http_response_status_code) (rate(http_server_request_duration_seconds_count{job=\"$service\"}[$__rate_interval]))",
          "legendFormat": "{{http_response_status_code}}"
        }
      ]
    },
    {
      "type": "timeseries",
      "title": "Database connection pool",
      "description": "Saturation, not throughput. A pool pinned at its ceiling is a queue, and a queue is latency that has not happened yet — this moves minutes before the error rate does.",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "h": 8, "w": 8, "x": 0, "y": 16 },
      "fieldConfig": { "defaults": { "unit": "short", "min": 0 }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "sum by (state) (db_client_connection_count{job=\"$service\"})",
          "legendFormat": "{{state}}"
        },
        {
          "refId": "B",
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "max(db_client_connection_max{job=\"$service\"})",
          "legendFormat": "ceiling"
        }
      ]
    },
    {
      "type": "timeseries",
      "title": "Event loop lag (p99)",
      "description": "How long a ready callback waited for the loop. Climbs when something synchronous blocks — the explanation for a slow service whose database is fast and whose processor is idle.",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "h": 8, "w": 8, "x": 8, "y": 16 },
      "fieldConfig": { "defaults": { "unit": "s", "min": 0 }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "histogram_quantile(0.99, sum by (le) (rate(event_loop_lag_seconds_bucket{job=\"$service\"}[$__rate_interval])))",
          "legendFormat": "p99"
        }
      ]
    },
    {
      "type": "timeseries",
      "title": "Requests in flight",
      "datasource": { "type": "prometheus", "uid": "prometheus" },
      "gridPos": { "h": 8, "w": 8, "x": 16, "y": 16 },
      "fieldConfig": { "defaults": { "unit": "short", "min": 0 }, "overrides": [] },
      "targets": [
        {
          "refId": "A",
          "datasource": { "type": "prometheus", "uid": "prometheus" },
          "expr": "sum(http_server_active_requests{job=\"$service\"})",
          "legendFormat": "in flight"
        }
      ]
    }
  ]
}
```

- [ ] **Step 4: Write `slo.json`**

Same skeleton — copy the `templating`, `annotations`, `timezone`,
`schemaVersion`, `version` and `refresh` blocks verbatim from
`service-health.json` — with `"uid": "pyfr-slo"`, `"title": "SLI and SLO"`,
`"time": { "from": "now-30d", "to": "now" }`, and these panels:

| # | Type | Title | gridPos `h,w,x,y` | Unit | Expression | Notes |
|---|---|---|---|---|---|---|
| 1 | `stat` | Availability SLI (30d) | 6,6,0,0 | `percentunit` | `1 - job:slo_availability_errors:ratio_rate30d{job="$service"}` | thresholds: red `null`, green `0.999` |
| 2 | `stat` | Latency SLI (30d) | 6,6,6,0 | `percentunit` | `1 - job:slo_latency_errors:ratio_rate30d{job="$service"}` | same thresholds |
| 3 | `gauge` | Availability budget remaining | 6,6,12,0 | `percentunit` | `1 - (job:slo_availability_errors:ratio_rate30d{job="$service"} / 0.001)` | `min` 0, `max` 1; thresholds red `null`, orange `0.25`, green `0.5` |
| 4 | `gauge` | Latency budget remaining | 6,6,18,0 | `percentunit` | `1 - (job:slo_latency_errors:ratio_rate30d{job="$service"} / 0.001)` | same |
| 5 | `timeseries` | Availability burn rate | 8,12,0,6 | `short` | A: `job:slo_availability_errors:ratio_rate1h{job="$service"} / 0.001` legend `1h`; B: `job:slo_availability_errors:ratio_rate5m{job="$service"} / 0.001` legend `5m` | thresholds green `null`, orange `6`, red `14.4` — the two page thresholds, drawn so the chart shows what the alerts see |
| 6 | `timeseries` | Latency burn rate | 8,12,12,6 | `short` | A: `job:slo_latency_errors:ratio_rate1h{job="$service"} / 0.001` legend `1h`; B: `job:slo_latency_errors:ratio_rate5m{job="$service"} / 0.001` legend `5m` | same thresholds |
| 7 | `timeseries` | 30-day trend | 8,24,0,14 | `percentunit` | A: `1 - job:slo_availability_errors:ratio_rate30d{job="$service"}` legend `availability`; B: `1 - job:slo_latency_errors:ratio_rate30d{job="$service"}` legend `latency` | `min` 0.99, so the interesting range is not squashed against the top of the chart |

Give panel 3 and 4 the description: *"How much of the month's error budget
is left. At zero the objective is missed for this window; the number
recovers as the window rolls forward."* Give panel 5 and 6: *"1.0 means the
budget will be exactly spent over 30 days. 14.4 means it is gone in two."*

- [ ] **Step 5: Write `runtime.json`**

Same skeleton, `"uid": "pyfr-runtime"`, `"title": "Runtime"`,
`"time": { "from": "now-1h", "to": "now" }`, and these panels — using the
names Step 1 confirmed:

| # | Type | Title | gridPos `h,w,x,y` | Unit | Expression |
|---|---|---|---|---|---|
| 1 | `timeseries` | Resident memory | 8,12,0,0 | `bytes` | `process_memory_usage_bytes{job="$service"}` legend `rss` |
| 2 | `timeseries` | Virtual memory | 8,12,12,0 | `bytes` | `process_memory_virtual_bytes{job="$service"}` legend `vms` |
| 3 | `timeseries` | Garbage collections | 8,12,0,8 | `ops` | `sum by (generation) (rate(cpython_gc_collections_total{job="$service"}[$__rate_interval]))` legend `gen {{generation}}` |
| 4 | `timeseries` | Uncollectable objects | 8,12,12,8 | `short` | `sum(rate(cpython_gc_uncollectable_objects_total{job="$service"}[$__rate_interval]))` legend `uncollectable` |
| 5 | `timeseries` | Threads | 8,8,0,16 | `short` | `process_thread_count{job="$service"}` legend `threads` |
| 6 | `timeseries` | Open file descriptors | 8,8,8,16 | `short` | `process_open_file_descriptor_count{job="$service"}` legend `fds` |
| 7 | `timeseries` | Process CPU | 8,8,16,16 | `percentunit` | `sum by (type) (process_cpu_utilization_ratio{job="$service"})` legend `{{type}}` |

Give panel 4 the description: *"Objects the collector could not free.
Steadily above zero means a reference cycle holding something the process
cannot release — a memory leak with a name."*

- [ ] **Step 6: Write the dashboard test**

Create `tests/unit/test_dashboards.py`:

```python
"""Structural checks on the dashboard JSON.

These cannot tell you a dashboard is USEFUL. They can tell you it will
load, point at a datasource that exists, and not hard-code a service name
— which are the three ways a provisioned dashboard fails silently, showing
an empty panel rather than an error.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

DASHBOARD_DIR = (
    Path(__file__).resolve().parents[2] / "ops" / "grafana" / "dashboards"
)
EXPECTED_UIDS = {"pyfr-service-health", "pyfr-slo", "pyfr-runtime"}


def _dashboards() -> list[tuple[str, dict[str, Any]]]:
    return [
        (path.name, json.loads(path.read_text()))
        for path in sorted(DASHBOARD_DIR.glob("*.json"))
    ]


def test_all_three_dashboards_exist() -> None:
    assert DASHBOARD_DIR.is_dir(), f"{DASHBOARD_DIR} not found"
    assert {dashboard["uid"] for _, dashboard in _dashboards()} == EXPECTED_UIDS


@pytest.mark.parametrize(("name", "dashboard"), _dashboards(), ids=lambda value: str(value))
def test_dashboard_has_a_title_and_a_stable_uid(
    name: str, dashboard: dict[str, Any]
) -> None:
    """The uid is the permalink. Changing it breaks every saved link."""
    assert dashboard.get("uid"), f"{name} has no uid"
    assert dashboard.get("title"), f"{name} has no title"


@pytest.mark.parametrize(("name", "dashboard"), _dashboards(), ids=lambda value: str(value))
def test_every_panel_targets_the_prometheus_datasource(
    name: str, dashboard: dict[str, Any]
) -> None:
    """`prometheus` is the datasource uid grafana/otel-lgtm provisions.

    A panel referencing any other uid renders "Datasource not found" —
    which looks like a broken dashboard rather than a broken reference.
    """
    for panel in dashboard["panels"]:
        assert panel["datasource"]["uid"] == "prometheus", (
            f"{name}: panel {panel['title']!r} points at the wrong datasource"
        )
        for target in panel["targets"]:
            assert target["datasource"]["uid"] == "prometheus"


@pytest.mark.parametrize(("name", "dashboard"), _dashboards(), ids=lambda value: str(value))
def test_no_panel_hard_codes_the_service_name(
    name: str, dashboard: dict[str, Any]
) -> None:
    """Spec 3.4: these files are copied verbatim into every generated
    project, never rendered. A hard-coded job name would ship every
    generated service a dashboard showing this one."""
    for panel in dashboard["panels"]:
        for target in panel["targets"]:
            assert "reference-service" not in target["expr"], (
                f"{name}: panel {panel['title']!r} hard-codes the service name"
            )


@pytest.mark.parametrize(("name", "dashboard"), _dashboards(), ids=lambda value: str(value))
def test_every_panel_has_a_title_and_at_least_one_target(
    name: str, dashboard: dict[str, Any]
) -> None:
    for panel in dashboard["panels"]:
        assert panel.get("title"), f"{name}: a panel has no title"
        assert panel.get("targets"), f"{name}: panel {panel['title']!r} queries nothing"


def test_the_service_variable_is_declared_everywhere_it_is_used() -> None:
    """`$service` in a query with no matching variable silently matches
    nothing, and the panel just looks like a service with no traffic."""
    for name, dashboard in _dashboards():
        variables = {
            variable["name"] for variable in dashboard["templating"]["list"]
        }
        assert "service" in variables, f"{name} uses $service without declaring it"
```

- [ ] **Step 7: Run the tests**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_dashboards.py -v`
Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add examples/reference-service/ops/grafana examples/reference-service/tests/unit/test_dashboards.py
git commit -m "feat(observability): add service health, slo and runtime dashboards"
```

---

## Task 11: The `o11y` compose profile, the recipes, and the end-to-end test

**Files:**
- Modify: `examples/reference-service/compose.yaml`
- Modify: `examples/reference-service/justfile`
- Test: `examples/reference-service/tests/integration/test_observability_stack.py`

**Interfaces:**
- Consumes: `ops/` (Tasks 9 and 10), `instrument_fastapi` and `build_providers` (Tasks 3 and 4).
- Produces: `just o11y`, `just o11y-down`, `just o11y-gates`. `check-all` gains `o11y-gates`.

- [ ] **Step 1: Add the profile to `compose.yaml`**

Add this service, and nothing else at the top level:

```yaml
  # The whole local observability stack in one container: Grafana,
  # Prometheus, Tempo, Loki and an OpenTelemetry collector. One image
  # rather than five services, with OUR dashboards and rules mounted in —
  # the same portable JSON that loads into a production Grafana.
  #
  # Behind a profile, so `just up` stays a database and an API. This image
  # is around 1GB and runs five processes; nobody wants it started by
  # default on a laptop.
  lgtm:
    profiles: ["o11y"]
    image: grafana/otel-lgtm:0.11.11
    ports:
      # The image declares no EXPOSE at all, so every port has to be
      # published explicitly or nothing here is reachable.
      - "3000:3000"  # Grafana
      - "4317:4317"  # OTLP over gRPC — what the app exports to
      - "4318:4318"  # OTLP over HTTP
    volumes:
      # Replaces the image's own Prometheus config. Its copy has no
      # rule_files key at all, and there is no other way to load rules —
      # no scrape config to attach to, no directory it already watches.
      - ./ops/prometheus/prometheus.yaml:/otel-lgtm/prometheus.yaml:ro
      - ./ops/prometheus/rules:/otel-lgtm/rules:ro
      # Added ALONGSIDE the image's own dashboard provider file rather
      # than over it, so the bundled RED and JVM dashboards survive.
      - ./ops/grafana/provisioning/dashboards/pyfr-dashboards.yaml:/otel-lgtm/grafana/conf/provisioning/dashboards/pyfr-dashboards.yaml:ro
      - ./ops/grafana/dashboards:/otel-lgtm/pyfr-dashboards:ro
    healthcheck:
      test: ["CMD", "curl", "-sf", "http://127.0.0.1:3000/api/health"]
      interval: 5s
      timeout: 3s
      retries: 30
```

Then extend the `app` service's `environment` block:

```yaml
      # Defaulted rather than hardcoded so one compose file serves both
      # `just up` (telemetry off) and `just o11y` (telemetry on), which
      # sets these two in its own environment.
      APP_OTEL__ENABLED: ${APP_OTEL__ENABLED:-false}
      APP_OTEL__LOGS_ENABLED: ${APP_OTEL__LOGS_ENABLED:-false}
      # `lgtm` is the compose service name above. Harmless when telemetry
      # is off — settings only require an endpoint when enabled.
      APP_OTEL__ENDPOINT: http://lgtm:4317
      # 60s is the SDK default and far too slow to iterate against: you
      # make a request and wait a minute to see the panel move.
      APP_OTEL__METRIC_EXPORT_INTERVAL_MS: 10000
```

**Deliberately no `depends_on: lgtm` on `app`.** Compose refuses to start a
service that depends on one in an inactive profile, so adding it would
break plain `just up` entirely. It is also unnecessary: the OTLP exporters
batch and retry, so an app that starts before the collector loses at most
the first few seconds of telemetry rather than failing.

- [ ] **Step 2: Add the recipes to the `justfile`**

```just
# Everything `up` starts, plus Grafana, Prometheus, Tempo and Loki with the
# dashboards and SLO rules from ops/ mounted in. Grafana is on
# http://localhost:3000 with anonymous admin access — no login.
#
# The two variables are set here rather than in compose.yaml so that one
# compose file serves both this and plain `up`.
o11y:
    APP_OTEL__ENABLED=true APP_OTEL__LOGS_ENABLED=true docker compose --profile o11y up --build

# Stop it and delete the volumes, telemetry included.
o11y-down:
    docker compose --profile o11y down -v

# Validate the SLO rules with promtool, which ships inside the pinned
# grafana/otel-lgtm image — so this needs no separate Prometheus install
# and can never drift from the version that actually evaluates the rules.
#
# `check rules` is syntax. `test rules` is the one that matters: it feeds
# synthetic series through the real rules and asserts the numbers that come
# out, which is the only thing standing between a dropped health-endpoint
# exclusion and an objective that reports 99.99% forever.
o11y-gates:
    docker run --rm -v "$PWD/ops/prometheus/rules:/rules" \
        --entrypoint sh grafana/otel-lgtm:0.11.11 \
        -c 'cd /rules && /otel-lgtm/prometheus/promtool check rules slo.yml && /otel-lgtm/prometheus/promtool test rules slo_test.yml'
```

Change the `check-all` recipe's dependency list to include it:

```just
check-all: check test-integration gates o11y-gates
```

- [ ] **Step 3: Verify the stack by hand once**

Run: `cd examples/reference-service && just o11y`

Then in another terminal:

```bash
curl -s localhost:8000/api/v1/orders/does-not-exist >/dev/null
```

Open `http://localhost:3000`, find the **PyFr** folder, and confirm all
three dashboards are there and the service-health panels have data. Then
open Explore, pick Loki, and confirm a log line carries a `trace_id` that
links through to Tempo. Stop with `just o11y-down`.

Do this before writing the automated test. The test asserts what you have
already seen work; debugging both at once is how a whole afternoon
disappears.

- [ ] **Step 4: Write the end-to-end test**

Create `tests/integration/test_observability_stack.py`:

```python
"""The whole chain, once: app -> OTLP -> Prometheus -> rules -> Grafana.

Every other test in this milestone checks one link. This one checks that
they are actually connected, which is the failure the others cannot see:
each half correct, the join wrong, and every dashboard empty.

Slow — roughly a minute — and container-bound, so it lives in the
integration tier.
"""

from __future__ import annotations

import json
import time
import urllib.request
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from testcontainers.core.container import DockerContainer
from testcontainers.core.waiting_utils import wait_for_logs

from reference_service.main import create_app
from reference_service.observability.otel import build_providers, instrument_fastapi
from reference_service.settings import Settings

pytestmark = pytest.mark.integration

LGTM_IMAGE = "grafana/otel-lgtm:0.11.11"
OPS = Path(__file__).resolve().parents[2] / "ops"
EXPECTED_DASHBOARD_UIDS = {"pyfr-service-health", "pyfr-slo", "pyfr-runtime"}


def _get_json(url: str) -> Any:
    with urllib.request.urlopen(url, timeout=10) as response:  # noqa: S310
        return json.loads(response.read())


@pytest.fixture(scope="module")
def stack() -> Iterator[DockerContainer]:
    """The same image, mounts and ports the o11y compose profile uses.

    Kept in step with compose.yaml by hand. If a mount is added there and
    not here, this test stops covering it — which is why the mounts below
    name the same four paths in the same order as the compose service.
    """
    container = (
        DockerContainer(LGTM_IMAGE)
        .with_exposed_ports(3000, 4317, 9090)
        .with_volume_mapping(
            str(OPS / "prometheus" / "prometheus.yaml"),
            "/otel-lgtm/prometheus.yaml",
            "ro",
        )
        .with_volume_mapping(str(OPS / "prometheus" / "rules"), "/otel-lgtm/rules", "ro")
        .with_volume_mapping(
            str(OPS / "grafana" / "provisioning" / "dashboards" / "pyfr-dashboards.yaml"),
            "/otel-lgtm/grafana/conf/provisioning/dashboards/pyfr-dashboards.yaml",
            "ro",
        )
        .with_volume_mapping(
            str(OPS / "grafana" / "dashboards"), "/otel-lgtm/pyfr-dashboards", "ro"
        )
    )
    with container as started:
        wait_for_logs(started, "The OpenTelemetry collector and the Grafana LGTM stack are up", timeout=180)
        yield started


@pytest.fixture(scope="module")
def prometheus_url(stack: DockerContainer) -> str:
    return f"http://{stack.get_container_host_ip()}:{stack.get_exposed_port(9090)}"


@pytest.fixture(scope="module")
def grafana_url(stack: DockerContainer) -> str:
    return f"http://{stack.get_container_host_ip()}:{stack.get_exposed_port(3000)}"


def test_prometheus_loaded_our_rule_groups(prometheus_url: str) -> None:
    """Verified fact 12: the image's own config has no rule_files key.

    If ops/prometheus/prometheus.yaml stops being mounted, or loses its
    rule_files entry, every SLO recording rule quietly ceases to exist —
    and every SLO dashboard panel goes blank rather than erroring.
    """
    payload = _get_json(f"{prometheus_url}/api/v1/rules")

    groups = {group["name"] for group in payload["data"]["groups"]}
    assert {"slo_sli_short", "slo_sli_long", "slo_burn_alerts"} <= groups

    unhealthy = [
        rule["name"]
        for group in payload["data"]["groups"]
        for rule in group["rules"]
        if rule["type"] == "recording" and rule["health"] != "ok"
    ]
    assert unhealthy == [], f"recording rules failed to evaluate: {unhealthy}"


def test_grafana_provisioned_all_three_dashboards(grafana_url: str) -> None:
    """Anonymous admin access is on in this image, so no credentials."""
    dashboards = _get_json(f"{grafana_url}/api/search?type=dash-db")

    assert EXPECTED_DASHBOARD_UIDS <= {dashboard["uid"] for dashboard in dashboards}


def test_a_real_request_reaches_prometheus_with_the_stable_names(
    stack: DockerContainer, prometheus_url: str, settings: Settings
) -> None:
    """The join every other test takes on trust.

    Proves three things at once that are each invisible in isolation: the
    semantic convention opt-in survived into the exported data, the
    histogram view's extra boundary survived the round trip, and the
    resource attributes were promoted to the labels the rules match on.
    """
    endpoint = f"http://{stack.get_container_host_ip()}:{stack.get_exposed_port(4317)}"
    enabled = settings.model_copy(
        update={
            "otel": settings.otel.model_copy(
                update={
                    "enabled": True,
                    "endpoint": endpoint,
                    "metric_export_interval_ms": 1000,
                }
            )
        }
    )
    runtime = build_providers(enabled, "1.2.3")
    app: FastAPI = create_app(settings)
    instrument_fastapi(app, runtime)

    try:
        with TestClient(app) as client:
            for _ in range(5):
                client.get("/api/v1/orders/does-not-exist")
        runtime.meter_provider.force_flush()

        # Prometheus ingests over OTLP through the collector's batch
        # processor, so the sample is not queryable the instant it is
        # pushed. Poll rather than sleep a guessed interval.
        deadline = time.monotonic() + 60
        series: list[dict[str, Any]] = []
        while time.monotonic() < deadline:
            payload = _get_json(
                f"{prometheus_url}/api/v1/query"
                f"?query=http_server_request_duration_seconds_count"
            )
            series = payload["data"]["result"]
            if series:
                break
            time.sleep(2)

        assert series, "no http.server.request.duration reached Prometheus"

        labels = series[0]["metric"]
        assert labels["job"] == "reference-service"
        assert labels["service_version"] == "1.2.3"
        assert "http_route" in labels, "legacy semantic conventions leaked in"
        assert "http_target" not in labels
    finally:
        runtime.shutdown()


def test_the_slo_latency_bucket_exists_in_prometheus(prometheus_url: str) -> None:
    """The single series the entire latency objective rests on.

    Without observability/otel.py's histogram view the boundaries jump
    0.25 -> 0.5, this series never exists, and every latency rule
    evaluates to nothing at all — silently, because an empty PromQL
    result is not an error.
    """
    payload = _get_json(
        f"{prometheus_url}/api/v1/query"
        f'?query=http_server_request_duration_seconds_bucket{{le="0.3"}}'
    )

    assert payload["data"]["result"], 'no bucket with le="0.3"'
```

- [ ] **Step 5: Find the real readiness log line**

The `wait_for_logs` string above must match what the image actually prints.
Confirm it:

```bash
docker run --rm --name lgtm-probe grafana/otel-lgtm:0.11.11 2>&1 | head -40
```

Use the last line printed once everything is up, and adjust `wait_for_logs`.
If no such line is stable, replace that call with a polling loop against
`http://<host>:<port>/api/health` bounded by the same 180-second deadline —
do not replace it with a fixed sleep, which is slow when it is too long and
flaky when it is too short.

- [ ] **Step 6: Run the integration test**

Run: `cd examples/reference-service && uv run pytest tests/integration/test_observability_stack.py -v -m integration`
Expected: PASS, 4 tests. Allow a minute or two on the first run while the
image is pulled.

- [ ] **Step 7: Run every gate**

Run: `cd examples/reference-service && just check-all`
Expected: all pass, `o11y-gates` included.

- [ ] **Step 8: Commit**

```bash
git add examples/reference-service/compose.yaml examples/reference-service/justfile examples/reference-service/tests/integration/test_observability_stack.py
git commit -m "feat(observability): add the o11y compose profile, recipes and stack tests"
```

---

## Task 12: Documentation

**Files:**
- Create: `docs/reference/observability.md`
- Modify: `docs/reference/configuration.md`
- Modify: `docs/reference/commands.md`
- Modify: `docs/reference/logging.md`
- Modify: `docs/roadmap.md`
- Modify: `mkdocs.yml`
- Modify: `examples/reference-service/README.md`

**Interfaces:** none — this task ships no code.

The site describes what is true now. Four pages stop being true the moment
Task 11 merges, and M2 owes them. The Diátaxis restructure, the *generated*
configuration reference and the on-call runbook remain M5's.

- [ ] **Step 1: Write `docs/reference/observability.md`**

Cover, in this order, and in the voice the existing reference pages use —
short sentences, a reason for every default:

1. **What ships and what does not** (spec 7.1). Instrumentation, dashboards
   and rules ship. A production observability platform does not: teams
   already have one, and the service's only commitment is emitting
   OpenTelemetry data to whatever `APP_OTEL__ENDPOINT` names.
2. **Turning it on.** `just o11y`, then `http://localhost:3000`, no login.
   State plainly that telemetry is off by default and that the default
   costs nothing — no exporter imported, no socket opened, no task started.
3. **What you get.** A table of the three dashboards with their UIDs and
   what question each answers.
4. **The three signals and how they join up.** A trace in Tempo; the log
   lines for that trace, found through the `trace_id` the Loki datasource
   links on; the metrics whose `job` label is the same `service.name`.
5. **The objectives.** 99.9% availability and 99.9% of requests within
   300 ms, over a rolling 30 days. Explain error budget and burn rate in
   plain words — a burn rate of 1 spends the whole month's budget in
   exactly a month, 14.4 spends it in two days. Say why two windows are
   used together: the long one is the signal, the short one is what makes
   the alert clear again after recovery.
6. **Changing the objectives.** Both numbers live in
   `src/reference_service/observability/slo.py`. Changing the latency
   threshold means changing the histogram boundary *and* the `le=` matcher
   in `ops/prometheus/rules/slo.yml`, and `just test` fails until they
   agree. Say so explicitly — someone will try to change one.
7. **Sampling in production.** `APP_OTEL__SAMPLE_RATIO` is parent-based, so
   a lower ratio never breaks a trace in half.
8. **The log export warning.** Repeat spec 7.6's warning verbatim in
   substance: OTLP log export in production *alongside* a platform log
   agent means every line is ingested twice and the bill doubles.

- [ ] **Step 2: Add the settings to `docs/reference/configuration.md`**

Follow the existing table format exactly. Six rows:

| Variable | Default | Meaning |
| --- | --- | --- |
| `APP_OTEL__ENABLED` | `false` | Turns on traces and metrics. Off by default; with it off nothing OpenTelemetry is constructed at all. |
| `APP_OTEL__ENDPOINT` | unset | The OTLP endpoint, over gRPC. **Required** when `APP_OTEL__ENABLED` is true — enabling the SDK with nowhere to send data fails at startup rather than dropping every span from a background thread. |
| `APP_OTEL__SAMPLE_RATIO` | `1.0` | Fraction of *new* traces recorded. Sampling is parent-based, so a request arriving with a sampled parent is always recorded whatever this says. |
| `APP_OTEL__METRIC_EXPORT_INTERVAL_MS` | `60000` | How often metrics are pushed. The `o11y` profile lowers it to 10000 so panels move while you watch. |
| `APP_OTEL__LOGS_ENABLED` | `false` | Exports logs over OTLP **in addition to** standard output. Requires `APP_OTEL__ENABLED`. Leave false in production: alongside a platform log agent it doubles ingest volume and cost. |

Add the warning admonition the page uses elsewhere for the last row.

- [ ] **Step 3: Add the recipes to `docs/reference/commands.md`**

Three rows, matching the page's existing format: `just o11y`,
`just o11y-down`, `just o11y-gates`. For `o11y-gates`, say what it validates
and that `promtool` comes from inside the pinned image rather than being a
separate install.

- [ ] **Step 4: Extend `docs/reference/logging.md`**

Add two rows to the "Fields on every record" table, immediately after
`deployment.environment`:

| Field | Meaning |
| --- | --- |
| `trace_id` | The active trace, as 32 hex digits. Present only on records emitted inside a span, which is why a startup line does not carry one. Links a log line to its trace in Tempo. |
| `span_id` | The active span, as 16 hex digits. Same condition. |

Then add a short section after "Correlation identifiers", titled
**`correlation_id` and `trace_id` are not the same thing**, explaining: the
correlation identifier is ours, comes from the `X-Request-ID` header or is
generated, is present on every record during a request whether or not
telemetry is on, and is what a support engineer quotes from a customer's
error page. The trace identifier is OpenTelemetry's, exists only when
telemetry is on and only inside a span, and is what Tempo indexes. Both are
worth having; neither replaces the other.

- [ ] **Step 5: Update `docs/roadmap.md`**

Change the **M1** row's state from `Planned` to `**Done**` — it merged in
`fec06bb` and the roadmap was never updated — and the **M2** row likewise.
Then update the line under the table, which currently reads "**M0 is done.**
Everything on this site describes code that exists today.", to name M0, M1
and M2.

- [ ] **Step 6: Add the page to `mkdocs.yml`**

In `nav:`, under `Reference:`, after `Logging: reference/logging.md`:

```yaml
      - Observability: reference/observability.md
```

- [ ] **Step 7: Update the reference service README**

Add a short section pointing at `just o11y` and the documentation page. Keep
it to a paragraph; the README orients, the site explains.

- [ ] **Step 8: Build the site strictly**

Run: `uv run mkdocs build --strict`
Expected: builds with no warnings. `--strict` turns a broken link or a page
missing from the nav into a failure, so this is the check that the new page
is actually reachable.

- [ ] **Step 9: Commit**

```bash
git add docs mkdocs.yml examples/reference-service/README.md
git commit -m "docs: describe the observability stack, slos and the new settings"
```

---

## Final verification

Run every gate in one go, from `examples/reference-service`:

```bash
just check-all
```

Expected, in order: ruff clean, mypy clean, both import contracts kept
(including the new `opentelemetry` ban on `domain/` and `services/`), the
fast test tier green, pre-commit clean with no tree modifications, the
container tier green, all five schema gates green, and `o11y-gates` green.

Then, from the repository root:

```bash
uv run mkdocs build --strict
```

Then confirm the two claims this milestone makes that no automated test can
make for you:

1. `just up` still works with no observability container running, and the
   application logs contain no OpenTelemetry errors. This is the default
   path and the one most generated services will use.
2. `just o11y`, one request, and then in Grafana: a trace in Tempo, its log
   lines reachable from that trace, and the service-health dashboard
   showing the request. That is the sentence spec 7.3 exists to make true.

---

## Self-review notes

Recorded here so a reviewer can check the same things.

**Spec coverage.** 7.1 scope boundary → Task 12's documentation page and the
`o11y` profile keeping the stack optional. 7.2 instrumentation → Tasks 3, 4,
5; resource attributes Task 3; sampling Task 3; OTLP for traces and metrics
Task 3. 7.3 local stack → Task 11. 7.4 dashboards → Task 10, with the
saturation instruments in Task 8 and `service_info` in Task 8. 7.5 SLOs and
multi-window multi-burn-rate alerting → Task 9. 7.6 structured logging →
Tasks 6 and 7; the field contract completed by Task 6; D15's transport split
by Task 7. D4 → Task 11. Spec 3.4's `_copy_without_render` requirement for
dashboards → Task 10's rule that no panel hard-codes a service name, with a
test.

**Deliberate spec deviations, both recorded in the plan body.** The
`Resource` sets `deployment.environment` *and* `deployment.environment.name`
where spec 7.2 names only the first — without the second no environment
label reaches Prometheus at all. And `redact_sensitive_fields`, which
appears in spec 7.6's processor list, stays in M6 with the rest of the
hardening work, as the exclusions table records.

**Known gaps left open on purpose.** The dashboards are validated
structurally and by provisioning successfully, not by asserting that every
panel returns data — several legitimately return nothing until the stack
has run for days (the 3-day and 30-day windows). The Prometheus names in
Task 10's table were confirmed for the HTTP and `service_info` series but
the process and garbage-collection ones were derived from the documented
translation rule, which is why Task 10 opens with a step that reads the real
names off a running stack and says the command wins over the table.
