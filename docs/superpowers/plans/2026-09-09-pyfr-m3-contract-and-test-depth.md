# PyFr M3 — Contract and Test Depth Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn `examples/reference-service/`'s API contract into a governed artifact — committed, drift-gated, conformance-tested and checked for breaking changes — and give the service its first outbound dependency: one shared `httpx` client with explicit timeouts, bounded retries and a circuit breaker, exercised by a real payment authorisation in the place-order flow, recorded to VCR cassettes, with mutation testing measuring whether the tests around all of it actually assert anything.

**Architecture:** The contract is generated *from* the code and committed *beside* it, so an API change appears in a pull request as a diff of `openapi.json` rather than buried in a router. Three offline gates guard it: bytes (drift), behaviour (Schemathesis over ASGI), and compatibility (`oasdiff` against a committed baseline, cross-checked against the version). The outbound client is infrastructure: `domain/payments.py` declares a `PaymentGateway` port that imports nothing but Pydantic, `infrastructure/http/` implements it over `httpx`, and `PlaceOrder` depends on the port. The circuit breaker wraps the retry policy — never the reverse — so N retries of one logical call count as one failure, not N.

**Tech Stack:** httpx 0.28.1, stamina 26.1.0 (retries; pulls tenacity 9.1.4), a hand-written circuit breaker, Schemathesis 4.26.1, pytest-recording 0.13.4 (vcrpy 8.3.0), mutmut 3.7.0, `tufin/oasdiff:v1.31.0` (pinned image, no Go toolchain), opentelemetry-instrumentation-httpx 0.65b0.

**Spec:** `docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md` — section 8.1 (test tiers, VCR, mutation testing), section 8.2 (the three contract gates), section 10.2 (the gate tying the contract to the version), section 12 item 5 (outbound HTTP policy), and decision D9.

**Predecessor:** `docs/superpowers/plans/2026-09-02-pyfr-m2-observability.md`. M2 is merged and green.

---

## Global Constraints

Every task's requirements implicitly include these. The first eighteen are inherited from M0, M1 and M2 unchanged; the rest are new in M3.

- **Python `>=3.13`.** `.python-version` contains `3.13`.
- **uv for everything Python.** `uv sync`, `uv run`, `uv lock`. No `pip`, no `requirements.txt`, no `pipx`, no manually activated virtual environment.
- **Plain Python only.** M3 is still Phase A. No Jinja, no cookiecutter variables, no `{{ }}` templating in any Python, YAML or compose file. Templatisation is M7.
- **Package name is `reference_service`;** distribution name is `reference-service`. All work happens under `examples/reference-service/`.
- **The domain layer imports nothing but `pydantic`.** Not FastAPI, not the service layer, not infrastructure, not SQLAlchemy, not asyncpg, not `opentelemetry` — and, new in M3, not `httpx` and not `stamina`.
- **The domain layer never knows an HTTP status code exists.**
- **mypy is strict on `domain/` and `services/`,** lenient elsewhere.
- **All logging goes through structlog.**
- **`/healthz` never checks a dependency.** Only `/readyz` does.
- **Line length 88.**
- **Conventional Commits** for every commit: `<type>[scope]: <description>`, imperative, lowercase, no trailing period.
- **Unit tests never need Docker.** `just test` runs `tests/unit` and `tests/api` only. Anything requiring a container lives in `tests/integration` and runs under `just test-integration`.
- **`filterwarnings = ["error"]` stays.** This bites hard in M3 — see Verified Fact 4.
- **Pinned images.** `tufin/oasdiff:v1.31.0` and the payment stub's image, each written in exactly one place and referenced from there.
- **Telemetry is off by default.** `APP_OTEL__ENABLED=false` is the default. With it false the process must import no exporter, open no socket, and start no background task. This extends to the new httpx instrumentation.
- **Standard output stays the source of truth for logs (D15).**
- **The stable HTTP semantic conventions, not the legacy ones.**
- **One source of truth for the SLO numbers.**
- **The committed contract is generated, never hand-edited.** `openapi.json` is an artifact of the code. The only way to change it is to change a route or a schema and run `just openapi`. A task that edits it by hand has done something wrong.
- **Every gate runs from `just`.** No `.github/workflows/` file is added in M3; M5 wires the same recipes into CI. A gate that only works inside a CI runner is not finished.
- **The contract tier never runs in the default selection.** `tests/contract/` is marked and deselected exactly as `tests/integration/` is, for the reason in Verified Fact 4.
- **No outbound request in a test ever reaches the network.** `record_mode=none` is pytest-recording's default and stays; a test attempting an unrecorded request must fail.
- **The breaker wraps the retry, not the reverse.** Retries are attempts at one logical call. Nested the other way, three retries against a dead upstream count as three failures and the breaker trips at a third of its configured threshold.
- **Never retry a decline.** A 402 is a successful call with a negative answer. Retrying it re-submits a payment. Only `httpx.TransportError`, 429 and 5xx are retryable.

---

## What M3 deliberately does not include

| Left out | Owner |
|---|---|
| `.github/workflows/*` — every gate runs from `just` | M5 (release), M7 (template CI) |
| Replacing the version cross-check with the Conventional Commits range check | M5, where Commitizen, tags and releases arrive together. M3 checks the version in `pyproject.toml`, which needs neither |
| Redis and S3 adapters, and their instrumentation | M4 |
| Log redaction of the payment payloads | M6, with the rest of the hardening work |
| A weekly job re-recording cassettes against a real upstream | M5. There is no real payment provider here to record — see Task 11's note on what the stub does and does not prove |
| The Diátaxis documentation restructure and the generated configuration reference | M5. M3 updates only the pages whose behaviour it changes, plus the roadmap row |
| Consumer-driven contract testing (Pact) | Never — spec 8.2. It pays off only with consumer-team buy-in and a hosted broker |
| Retrying or reconciling an order whose authorisation succeeded but whose write failed | Deliberately out of scope. Task 12 documents the window rather than pretending it does not exist |
| Making the payment provider a cookiecutter prompt | M7. In M3 it is one adapter behind one port, which is exactly what M7 will make optional |
| A coverage threshold (spec 8.1 names 85%) | Not in the roadmap's M3 row, and no coverage tooling exists yet. M3 adds the *stronger* of the two signals; whoever adds `pytest-cov` should add the threshold with it |
| Running mutation testing nightly | M5, with the rest of the scheduled CI work. M3 provides the recipe and the gate it will call |

---

## Verified Facts

Every item below was confirmed by running the real software while this plan was written, not read from documentation. They are the traps this milestone contains. **Read this section before Task 1.**

**1. These six additions resolve together and break nothing.**
`httpx 0.28.1`, `stamina 26.1.0` (which pulls `tenacity 9.1.4`), `schemathesis 4.26.1`, `pytest-recording 0.13.4` (which pulls `vcrpy 8.3.0`), `mutmut 3.7.0`, `opentelemetry-instrumentation-httpx 0.65b0`. Schemathesis pins Hypothesis but did **not** move the existing one — it resolved to `hypothesis 6.165.10`, above the project's `>=6.112` floor. With all six installed and nothing else changed, the existing suite still reports `220 passed, 23 deselected`.

**2. The generated contract is byte-stable across processes.**
`json.dumps(create_app().openapi(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"` produced the identical SHA-256 in two separate Python processes (`e309f8e3…`), 25,349 bytes, `openapi: 3.1.0`. So the drift gate can compare **bytes**, which gives a readable diff, rather than parsed structures, which do not diff usefully.

**3. Schemathesis reaches the app over ASGI with no network and no server.**
`schemathesis.openapi.from_asgi("/openapi.json", app)` exists in 4.26.1 and works against `create_app()`. The pytest integration is `@schema.parametrize()` on a sync test function taking `case`, calling `case.call_and_validate()`. It parametrises one test per operation, so failures name the operation: `test_api_conforms_to_its_own_contract[POST /api/v1/orders]`.

**4. Schemathesis's ASGI transport leaks anyio memory streams, and under `filterwarnings = ["error"]` that fails UNRELATED tests.**
Every conformance test errored at teardown with:

```
ResourceWarning: Unclosed <MemoryObjectReceiveStream at 0x…>
  → pytest.PytestUnraisableExceptionWarning
```

This is worse than it first looks. The warning fires whenever the garbage collector gets round to the stream, so pytest attributes it to **whatever test is running at that moment**. Running the whole suite with `tests/contract/` present failed `tests/api/test_errors.py::test_a_domain_error_becomes_problem_details` — a test that passes on its own and has nothing to do with contracts. Removing `tests/contract/` returned the suite to `220 passed`.

Our own code is **not** the cause: both middlewares in `api/middleware.py` are plain ASGI callables, not `BaseHTTPMiddleware` subclasses, so the usual Starlette explanation does not apply here. The fix is therefore containment, not a code change: the contract tier gets its own marker and is deselected by default (Task 5), with a narrow `filterwarnings` ignore scoped to that tier alone.

**5. The published contract for `unit_amount` is more permissive than the model.**
Pydantic renders a constrained `Decimal` as a two-branch `anyOf`. `max_digits` and `decimal_places` reach only the **string** branch's regex; the **number** branch carries `minimum` alone:

```json
"unit_amount": {"anyOf": [
  {"type": "number", "minimum": 0.0},
  {"type": "string", "pattern": "^(?!^[-+.]*$)[+-]?0*(?:\\d{0,12}|(?=[\\d.]{1,15}0*$)\\d{0,12}\\.\\d{0,2}0*$)"}
]}
```

Schemathesis sent `unit_amount: 1.0605661518203426e+308` — valid against that contract — and the app answered 422 `decimal_max_digits`. The contract is wrong, not the app.

**6. That string branch's regex is not fully anchored, and JSON Schema `pattern` is a partial match.**
The first alternative, `\d{0,12}`, has no closing `$`; only the second does. Confirmed directly:

```python
re.search(pattern,   '070ªPz\U000e5ec4ú\x1bh')  # → matches
re.fullmatch(pattern,'070ªPz\U000e5ec4ú\x1bh')  # → does not match
```

JSON Schema's `pattern` is explicitly unanchored, so a validator is required to use search semantics. Schemathesis generated that string legitimately; the app answered 422 `decimal_parsing`. Again the contract is wrong. Both branches must be replaced by an explicit, accurate schema (Task 4).

**7. Individually valid lines can overflow the order total, and today that is a 500.**
`quantity: 2147483646` with `unit_amount: 272486.81` — each within its own documented bound — makes a subtotal far beyond `Money`'s `NUMERIC(14, 2)` limit. `Money` construction raises inside `PlaceOrder`, which wraps it as `ServiceDefectError`, which falls through to the catch-all and returns **500 for ordinary, schema-valid client input**. Reproduced from the generated payload. The existing comments on `OrderLineIn.quantity` and `.unit_amount` say those bounds exist precisely to stop this class of failure; they close it one field at a time, and the product of two fields slips through.

**8. Framework-raised `HTTPException`s bypass Problem Details entirely.**
`api/errors.py` registers handlers for `DomainError`, `RequestValidationError`, `PydanticValidationError` and a catch-all `Exception` — and **none for `HTTPException`**. Starlette handles that before the catch-all ever sees it. Confirmed responses, all `content-type: application/json` rather than `application/problem+json`:

| Request | Status | Body |
|---|---|---|
| `PUT /api/v1/orders` | 405 | `{"detail":"Method Not Allowed"}` |
| `GET /api/v1/nope` | 404 | `{"detail":"Not Found"}` |
| `POST /api/v1/orders` with body `b"\xff\x11"` | 400 | `{"detail":"There was an error parsing the body"}` |

The 400 is what Schemathesis reported as `Undocumented HTTP status code — Documented: 201, 422, 500; Received: 400`. Note that a *malformed but valid UTF-8* body (`b"{not json"`) does produce a correct 422 Problem Details — the hole is specifically `HTTPException`, and undecodable bytes are just one way to reach it.

**9. `oasdiff` runs from a pinned image and its exit codes are usable.**
`tufin/oasdiff:v1.31.0`. Identical pair → `No changes detected`, exit 0. A deliberately broken pair (removed a required response property, added a required request property) → exit **1** with `--fail-on ERR`, printing three findings. With `-f json` each finding carries `id`, `level: 3`, `operation`, `path` and a stable `fingerprint` — enough for the cross-check script to read without scraping prose.

**10. pytest-recording refuses unrecorded requests with no flag needed.**
`none` is already the default record mode. An `httpx.AsyncClient` request with no cassette raised `vcr.errors.CannotOverwriteExistingCassetteException` and failed the test, with and without an explicit `--record-mode=none`. Cassettes are written to `tests/<dir>/cassettes/<module>/<test>.yaml`.

**11. mutmut needs three configuration facts, each learned by hitting it.**

*(a) Where the config lives, and when it loads.* `[tool.mutmut]` in `pyproject.toml`, keys `source_paths`, `only_mutate`, `do_not_mutate`, `also_copy`, `pytest_add_cli_args_test_selection`. (`paths_to_mutate` and `tests_dir` still work but warn as deprecated — do not use them.) The config is read at **import** time, and with no `source_paths` and no guessable layout it raises `FileNotFoundError` before the CLI prints anything.

*(b) It runs the suite inside a `mutants/` copy that does not contain `ops/`.* The copy holds `source_paths`, `tests/`, and a fixed list of lock and config files. M2's `tests/unit/test_dashboards.py` failed there with `mutants/ops/grafana/dashboards not found`. `also_copy = ["ops", "migrations"]` fixes it — `migrations` for the same reason, because `test_migration_files.py` hashes those files.

*(c) It injects its own import into every mutated module.* M0's `tests/unit/test_layer_purity.py` then fails inside `mutants/`:

```
AssertionError: third-party imports found: {'order.py': {'mutmut'}, …}
```

Do **not** add `mutmut` to that gate's allow-list — that would weaken a real M0 gate in ordinary runs to satisfy a tool. Point mutmut at behaviour tests instead: a file-shape gate can never kill a mutant, so including it buys nothing and costs a false failure.

**12. The mutation baseline, measured.**
With `pytest_add_cli_args_test_selection` set to `test_order.py`, `test_order_service.py`, `test_domain_errors.py`, `test_memory_repository.py` and `tests/api/test_orders.py`: **58 mutants, 51 killed, 7 survived, 4.2 seconds wall clock**, 34.9 mutations/second. Score 87.9%.

All seven survivors are error-*message* mutations, of exactly this shape:

```diff
-        raise ValueError("cannot total an empty list of lines")
+        raise ValueError(None)
```

That matters for how the threshold is set. Chasing a message-string survivor produces tests that assert on prose and break when someone rewords a message — the opposite of what M0's `capture_logs` guidance asks for. Task 14 sets the floor at 85% and says so in the docs.

**13. stamina's API surface.**
`stamina.retry(*, on, attempts=10, timeout=45.0, wait_initial=0.1, wait_max=5.0, wait_jitter=1.0, wait_exp_base=2)`. Two extras matter here: `stamina.set_testing(True)` removes all waiting so retry tests take microseconds rather than seconds, and `stamina.instrumentation.StructlogOnRetryHook` emits each retry through structlog, which is already this service's logging chain.

**14. httpx instrumentation attaches to one client, not globally.**
`HTTPXClientInstrumentor.instrument_client(client, tracer_provider=…)` instruments a single instance. That is what lets M2's rule hold: with `APP_OTEL__ENABLED` false, nothing is instrumented and no SDK object is constructed.

**15. There is no maintained asyncio circuit breaker to depend on.**
`pybreaker` 1.4.1 is actively maintained (September 2025) but its asynchronous support is **Tornado**-based, not `asyncio` — its own documentation offers `__pybreaker_call_async=True` for Tornado coroutines and mentions neither `await` nor `asyncio`. `purgatory-circuitbreaker` last released 0.7.2 in January 2022; `aiobreaker` 1.2.0 in May 2021. Writing roughly eighty lines is the smaller long-term cost, and it is the one piece here with genuinely no good library.

**16. Replacing Starlette's HTTPException handler drops the `Allow` header, and the conformance gate catches it in one run.**
Starlette's default 405 response carries `Allow: POST`, which RFC 9110 requires. A replacement handler that renders Problem Details from `exc.detail` and `exc.status_code` alone silently loses it, because `exc.headers` is where Starlette puts it. Confirmed: with the naive handler, every operation failed Schemathesis's `unsupported_method` check with `TRACE returned 405 without required Allow header`; forwarding `exc.headers` restored `Allow: POST` and turned the tier green. This is the single best argument for the conformance gate in this milestone — a hand-written fix to an error path broke a header nobody would have thought to test, and the gate found it in the same run it was introduced.

**17. `stamina.set_testing(True)` removes retries, not merely the waiting.**
Its signature is `set_testing(testing, *, attempts=1, cap=False)` — the default sets attempts to **1**, so a test using it plainly sees no retry at all and a "we retry three times" assertion passes for the wrong reason. Confirmed: with `set_testing(True)` a retryable 503 produced one upstream call; with it off, three. Use `stamina.set_testing(True, attempts=100, cap=True)` when a test needs the real attempt count without the backoff — `cap=True` keeps the configured value when it is smaller.

Also confirmed: stamina finds structlog on its own and logs each retry as a `stamina.retry_scheduled` warning carrying `retry_num`, `wait_for`, `waited_so_far` and `caused_by`. No hook wiring is needed for retries to appear in this service's log stream.

**18. The retry-inside-breaker nesting was measured, not assumed.**
With `attempts=3`, a breaker threshold of 2, and an upstream answering 503:

| Call | Upstream requests (cumulative) | Breaker after |
|---|---|---|
| 1st `authorise` | 3 | `closed` — three retries, **one** logical failure |
| 2nd `authorise` | 6 | `open` |
| 3rd `authorise` | 6 — unchanged | `open`, refused with `CircuitOpenError` |

And a 402: one request, returned as an answer, breaker still `closed`. That last row is the property that matters most — a decline neither retries nor trips the breaker.

**19. mutmut has a machine-readable summary, so the threshold needs no output scraping.**
`mutmut export-cicd-stats` writes `mutants/mutmut-cicd-stats.json`. On the baseline run it contained exactly:

```json
{"killed": 51, "survived": 7, "total": 58, "no_tests": 0, "skipped": 0,
 "suspicious": 0, "timeout": 0, "check_was_interrupted_by_user": 0, "segfault": 0}
```

Parsing `mutmut results` text instead would break the first time its formatting changes.

---

## File Structure

**Created:**

| Path | Responsibility |
|---|---|
| `openapi.json` | The committed contract. Generated, never hand-edited |
| `openapi.baseline.json` | The last released contract, and — via its own `info.version` — the version it was taken at. `oasdiff` compares against this |
| `schemathesis.toml` | The documented conformance exceptions. One entry, with a comment saying why |
| `src/reference_service/infrastructure/http/__init__.py` | Package marker |
| `src/reference_service/infrastructure/http/breaker.py` | `CircuitBreaker`: the closed/open/half-open state machine. No HTTP, no I/O, injected clock |
| `src/reference_service/infrastructure/http/client.py` | `build_http_client`: one `httpx.AsyncClient` with explicit timeouts and connection limits |
| `src/reference_service/infrastructure/http/payment_gateway.py` | `HttpPaymentGateway`: the adapter implementing the domain port, wrapping retry inside breaker |
| `src/reference_service/domain/payments.py` | The `PaymentGateway` port and the `Authorisation` value object. Imports Pydantic and nothing else |
| `migrations/000003_add_order_authorisation.up.sql` / `.down.sql` | `orders.authorisation_id` |
| `scripts/check_contract_compatibility.py` | Runs `oasdiff`, and fails when a breaking change is not matched by a version bump |
| `tests/contract/__init__.py`, `tests/contract/conftest.py` | The contract tier's marker and its scoped warning filter |
| `tests/contract/test_drift.py` | The committed contract matches the code, byte for byte |
| `tests/contract/test_conformance.py` | Schemathesis over ASGI |
| `tests/unit/test_breaker.py` | The state machine, against a fake clock |
| `tests/unit/test_http_client.py` | Timeouts and the retry policy — what retries and, more importantly, what does not |
| `tests/unit/test_payment_gateway.py` | The adapter's mapping from responses and transport failures onto errors |
| `tests/unit/test_contract_compatibility.py` | The cross-check script's own logic, on fixtures |
| `tests/cassettes/` | Recorded outbound HTTP |
| `ops/payment-stub/` | The local stub upstream that `just test-record` records against |

**Modified:**

| Path | Change |
|---|---|
| `pyproject.toml` | Six dependencies, the `contract` marker, `[tool.mutmut]` |
| `src/reference_service/settings.py` | `PaymentSettings`, and `payment` on `Settings` |
| `src/reference_service/domain/errors.py` | `PaymentDeclinedError` |
| `src/reference_service/domain/order.py` | `authorisation_id` on `Order` |
| `src/reference_service/infrastructure/errors.py` | `PaymentUnavailableError` |
| `src/reference_service/services/order.py` | `PlaceOrder` takes the gateway; authorise, then save |
| `src/reference_service/api/errors.py` | An `HTTPException` handler; 402 and 503 in the status map; the new documented responses |
| `src/reference_service/api/v1/schemas.py` | The accurate `unit_amount` schema; the total-fits-in-`Money` validator |
| `src/reference_service/api/v1/router.py` | 402 and 503 on `place_order` |
| `src/reference_service/api/deps.py` | `get_payments`, and `PlaceOrder` built with it |
| `tests/fakes.py` | Three payment gateway doubles |
| `src/reference_service/container.py` | Builds the client and the gateway; closes the client at shutdown |
| `src/reference_service/main.py` | Instruments the client when telemetry is on |
| `src/reference_service/observability/otel.py` | `instrument_http_client` |
| `.importlinter` | `httpx` and `stamina` forbidden in `domain` and `services` |
| `compose.yaml` | The payment stub service |
| `justfile` | `openapi`, `contract-gates`, `contract-release`, `test-contract`, `test-record`, `mutants`, `mutants-gate`, `mutants-changed` |
| `docs/*` | The roadmap row, and the reference pages whose behaviour changed |

---

## Task 1: Dependencies and the contract test tier

The contract tier must exist and be deselected *before* any contract test is written, or the first one written poisons the whole suite (Verified Fact 4).

**Files:**
- Modify: `examples/reference-service/pyproject.toml`
- Modify: `examples/reference-service/justfile`
- Create: `examples/reference-service/tests/contract/__init__.py`
- Create: `examples/reference-service/tests/contract/conftest.py`

**Interfaces:**
- Consumes: nothing.
- Produces: the `contract` pytest marker; `just test-contract`; `httpx`, `stamina`, `schemathesis`, `pytest-recording`, `mutmut` and `opentelemetry-instrumentation-httpx` available to later tasks.

- [ ] **Step 1: Add the runtime dependencies**

`httpx` moves out of the `dev` group: from this milestone on it is production code, not a test helper.

```bash
cd examples/reference-service
uv add "httpx>=0.28" "stamina>=26.1" "opentelemetry-instrumentation-httpx>=0.65b0"
```

Then delete the now-duplicated `"httpx>=0.27",` line from `[dependency-groups].dev` in `pyproject.toml`, and add these comments above the two new runtime entries:

```toml
    # The shared outbound client (spec 12, item 5). A runtime dependency
    # from M3 on, not a test helper: infrastructure/http/client.py is
    # production code.
    "httpx>=0.28",
    # Bounded retries with exponential backoff and jitter. Chosen over
    # writing one: stamina is asyncio-native, typed, and wraps tenacity,
    # which has solved retry budgets and jitter properly for years. The
    # circuit breaker beside it IS hand-written, because no maintained
    # asyncio implementation exists — see the plan's Verified Fact 15.
    "stamina>=26.1",
    # Outbound spans for the payment call. Closes the first row of the M2
    # plan's "deliberately does not include" table.
    "opentelemetry-instrumentation-httpx>=0.65b0",
```

- [ ] **Step 2: Add the development dependencies**

```bash
uv add --group dev "schemathesis>=4.26" "pytest-recording>=0.13" "mutmut>=3.7"
```

- [ ] **Step 3: Register the `contract` marker and deselect it by default**

In `pyproject.toml`, extend `addopts` and `markers`:

```toml
[tool.pytest.ini_options]
addopts = "-q --strict-markers --strict-config -m 'not integration and not contract'"
testpaths = ["tests"]
asyncio_mode = "auto"
markers = [
    "integration: requires a running Docker daemon",
    # Schemathesis over ASGI. Deselected by default for the same reason
    # `integration` is — it is slow — and for one worse reason that is
    # specific to it: its ASGI transport leaves anyio memory object
    # streams unclosed, and `filterwarnings = ["error"]` below turns the
    # resulting ResourceWarning into a PytestUnraisableExceptionWarning.
    # That warning fires whenever the garbage collector reaches the
    # stream, so pytest blames whichever test happens to be running then.
    # Verified: with tests/contract/ in the default selection, the whole
    # suite failed on tests/api/test_errors.py — a test that passes on its
    # own and has nothing to do with contracts. `just test-contract` runs
    # this tier on its own, where the filter in tests/contract/conftest.py
    # contains the damage.
    "contract: schemathesis conformance against the committed contract",
]
```

- [ ] **Step 4: Write the contract tier's conftest**

Create `tests/contract/__init__.py` (empty) and `tests/contract/conftest.py`:

```python
"""Applies the `contract` marker, and contains one third-party warning.

Every module in this directory gets the marker automatically, so no test
below has to remember it — forgetting it would put a conformance test back
into the default selection, which is the exact failure this tier exists to
avoid.
"""

from __future__ import annotations

import pytest

# Scoped to this directory ON PURPOSE, never to pyproject.toml's global
# `filterwarnings`. The leak is in Schemathesis's ASGI transport, not in
# our code — both middlewares in api/middleware.py are plain ASGI
# callables rather than BaseHTTPMiddleware subclasses, so the usual
# Starlette explanation does not apply. Filtering it globally would
# silence a genuine resource leak anywhere else in the service, which is
# a real class of bug in an async application holding a connection pool.
pytestmark = [
    pytest.mark.contract,
    pytest.mark.filterwarnings("ignore::ResourceWarning"),
    pytest.mark.filterwarnings(
        "ignore::pytest.PytestUnraisableExceptionWarning"
    ),
]
```

- [ ] **Step 5: Add the `just` recipe**

```just
# The contract tier. Separate from `just test` because Schemathesis's ASGI
# transport leaks anyio streams under filterwarnings=error and takes the
# blame out on unrelated tests — see the `contract` marker's comment in
# pyproject.toml.
test-contract:
    uv run pytest -m contract
```

And extend `test-all` so nothing is quietly left out of the "everything" recipe:

```just
# Everything: unit, api, integration and contract.
test-all:
    uv run pytest -m ''
```

- [ ] **Step 6: Verify the default selection is unchanged**

Run: `just test`
Expected: `220 passed, 23 deselected` — the same numbers as before this task. Adding six dependencies must not change a single existing result.

Run: `just test-contract`
Expected: `no tests ran` — the directory exists and collects nothing yet.

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service/pyproject.toml examples/reference-service/uv.lock \
        examples/reference-service/justfile examples/reference-service/tests/contract
git commit -m "build(reference-service): add the contract and mutation testing toolchain"
```

---

## Task 2: The committed contract and its drift gate

**Files:**
- Create: `examples/reference-service/openapi.json`
- Create: `examples/reference-service/tests/contract/test_drift.py`
- Modify: `examples/reference-service/justfile`

**Interfaces:**
- Consumes: the `contract` marker from Task 1.
- Produces: `render_openapi() -> str` and `CONTRACT_PATH` in `tests/contract/test_drift.py`, imported by `just openapi` and by Task 6's release recipe.

- [ ] **Step 1: Write the failing test**

`tests/contract/test_drift.py`:

```python
"""The committed contract must match the code, byte for byte.

Bytes, not parsed structures. A parsed comparison can only say "these
differ"; a byte comparison makes the difference show up in the pull
request as an ordinary diff of openapi.json, which is the entire point of
committing it (spec 8.2, gate 1).
"""

from __future__ import annotations

import json
from pathlib import Path

from reference_service.main import create_app

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "openapi.json"


def render_openapi() -> str:
    """The one place that decides how the contract is serialised.

    `sort_keys=True` so the file has a stable order independent of how
    FastAPI happens to build the dict; `ensure_ascii=False` so a non-ASCII
    description stays readable in the diff rather than becoming escape
    sequences; a trailing newline because every other text file here has
    one and pre-commit's end-of-file-fixer would add it anyway.

    Verified byte-stable across two separate processes — see the plan's
    Verified Fact 2 — which is what makes a byte comparison legitimate.
    """
    document = create_app().openapi()
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_the_committed_contract_matches_the_code() -> None:
    assert CONTRACT_PATH.exists(), (
        f"{CONTRACT_PATH.name} is missing. Run `just openapi` and commit it."
    )
    assert CONTRACT_PATH.read_text(encoding="utf-8") == render_openapi(), (
        "openapi.json is out of date. Run `just openapi` and commit the result "
        "— and read the diff before you do: it is the API change you just made, "
        "stated in full."
    )
```

- [ ] **Step 2: Run it and watch it fail for the right reason**

Run: `cd examples/reference-service && uv run pytest -m contract`
Expected: FAIL — `openapi.json is missing. Run just openapi and commit it.`

- [ ] **Step 3: Add the `just openapi` recipe**

It reuses the gate's own `render_openapi`, so there is exactly one definition of how the contract is serialised. A second one in shell would be one more thing to keep in step, the same reasoning `just schema-snapshot` already follows for the database schema.

```just
# Regenerate the committed contract from the code, then commit the result.
# Read the diff before you do: it is your API change, in full.
openapi:
    uv run python -c "from tests.contract.test_drift import CONTRACT_PATH, render_openapi; CONTRACT_PATH.write_text(render_openapi(), encoding='utf-8')"
```

- [ ] **Step 4: Generate the contract and re-run**

Run: `just openapi && uv run pytest -m contract`
Expected: PASS, and `openapi.json` is about 25 KB with `"openapi": "3.1.0"`.

- [ ] **Step 5: Prove the gate actually catches drift**

This is worth doing by hand once. A gate nobody has seen fail is a gate nobody knows works.

```bash
python3 - <<'PY'
from pathlib import Path
p = Path("src/reference_service/api/v1/router.py")
p.write_text(p.read_text().replace('tags=["orders"]', 'tags=["ordering"]'))
PY
uv run pytest -m contract
```

Expected: FAIL — `openapi.json is out of date`. Then revert the edit and confirm it passes again:

```bash
git checkout src/reference_service/api/v1/router.py && uv run pytest -m contract
```

- [ ] **Step 6: Commit**

```bash
git add examples/reference-service/openapi.json \
        examples/reference-service/tests/contract/test_drift.py \
        examples/reference-service/justfile
git commit -m "feat(reference-service): commit the openapi contract and gate it against drift"
```

---

## Task 3: Problem Details for framework errors

Found by running Schemathesis while writing this plan (Verified Fact 8). M0 promises RFC 9457 for errors; three common responses do not honour it. This lands before the conformance gate so the gate arrives green rather than red.

**Files:**
- Modify: `examples/reference-service/src/reference_service/api/errors.py`
- Modify: `examples/reference-service/src/reference_service/main.py`
- Test: `examples/reference-service/tests/api/test_errors.py`

**Interfaces:**
- Consumes: `ProblemDetail`, `_problem_response`, `PROBLEM_TYPE_BASE`, `problem_response` — all already in `api/errors.py`.
- Produces: 400, 404 and 405 entries in `DEFAULT_PROBLEM_RESPONSES`; every response the service can emit is now `application/problem+json`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_errors.py`:

```python
@pytest.mark.parametrize(
    ("method", "path", "body", "expected_status"),
    [
        ("PUT", "/api/v1/orders", None, 405),
        ("GET", "/api/v1/nope", None, 404),
        # Undecodable bytes, NOT merely malformed JSON. A body of
        # b"{not json" is valid UTF-8 and reaches request validation, which
        # already answers a correct 422 Problem Details. These bytes fail
        # earlier, inside FastAPI's body reading, which raises an
        # HTTPException(400) — and before this task nothing handled it.
        ("POST", "/api/v1/orders", b"\xff\x11", 400),
    ],
)
def test_framework_errors_are_problem_details(
    client: TestClient,
    method: str,
    path: str,
    body: bytes | None,
    expected_status: int,
) -> None:
    response = client.request(method, path, content=body)

    assert response.status_code == expected_status
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["status"] == expected_status
    assert problem["title"]
    assert problem["instance"] == path
    # The shape clients are promised. `detail` is optional in RFC 9457;
    # `type`, `title` and `status` are not.
    assert set(problem) >= {"type", "title", "status"}


def test_a_405_still_carries_the_allow_header(client: TestClient) -> None:
    """RFC 9110 requires it, and a hand-written handler is where it is lost."""
    response = client.put("/api/v1/orders", json={})

    assert response.status_code == 405
    assert response.headers["allow"] == "POST"
```

- [ ] **Step 2: Run them and watch all three fail**

Run: `uv run pytest tests/api/test_errors.py -k framework_errors -v`
Expected: three failures, each on the content-type assertion, reporting `application/json`.

- [ ] **Step 3: Register the handler**

In `api/errors.py`, add the import:

```python
from starlette.exceptions import HTTPException as StarletteHTTPException
```

and register this handler inside `register_error_handlers`, beside the others:

```python
    @app.exception_handler(StarletteHTTPException)
    async def _http_exception(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Problem Details for errors raised by the framework itself.

        Starlette answers routing and body-reading failures by raising
        HTTPException, and it handles that type before the catch-all
        `Exception` handler below can ever see it. Without this handler its
        default takes over and returns `{"detail": "..."}` as
        `application/json` — so a service that documents RFC 9457
        everywhere silently returns a different shape for three of its most
        common responses: 405 on a wrong method, 404 on an unknown path,
        and 400 when a request body is not decodable as UTF-8. Found by
        Schemathesis, which reported the 400 as an undocumented status code.

        `StarletteHTTPException`, not `fastapi.HTTPException`: FastAPI's is
        a subclass, and the routing and body-reading failures raise the
        Starlette one. Registering the subclass would miss exactly the
        cases this exists for.

        `exc.detail` is safe to echo. For these framework errors it is a
        fixed string chosen by Starlette ("Not Found", "Method Not
        Allowed"), never assembled from request content — contrast the
        deliberate silence about exception messages in ReadinessRegistry.
        """
        return _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/http_error",
                title=str(exc.detail),
                status=exc.status_code,
                instance=request.url.path,
            ),
            # Load-bearing, and easy to leave out. Starlette's own 405
            # sets `Allow: POST`, which RFC 9110 REQUIRES on a 405, and it
            # carries it on `exc.headers`. A handler built only from
            # `detail` and `status_code` drops it. Verified: without this
            # argument every operation failed Schemathesis's
            # `unsupported_method` check with "TRACE returned 405 without
            # required Allow header".
            headers=exc.headers,
        )
```

This needs a one-line widening of the existing helper, which takes no headers today:

```python
def _problem_response(
    problem: ProblemDetail, headers: dict[str, str] | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(exclude_none=True),
        media_type=PROBLEM_MEDIA_TYPE,
        headers=headers,
    )
```

- [ ] **Step 4: Document the three responses in the contract**

Still in `api/errors.py`, extend `DEFAULT_PROBLEM_RESPONSES`:

```python
DEFAULT_PROBLEM_RESPONSES: dict[int | str, dict[str, Any]] = {
    # 400 is reachable on EVERY route, not only ones with a body: it is
    # what FastAPI raises when it cannot read the request at all.
    status.HTTP_400_BAD_REQUEST: problem_response("Malformed request"),
    status.HTTP_404_NOT_FOUND: problem_response("No such resource"),
    status.HTTP_405_METHOD_NOT_ALLOWED: problem_response("Method not allowed"),
    status.HTTP_422_UNPROCESSABLE_CONTENT: problem_response(
        "Request validation failed"
    ),
    status.HTTP_500_INTERNAL_SERVER_ERROR: problem_response("Internal server error"),
}
```

Note what this does to the per-route 404 on `get_order` in `api/v1/router.py`: it stays. The global entry describes "you asked for a path this service does not serve"; the route-level one describes "this order does not exist", which is a different thing with a different `type`. Leave both, and leave the comment above the route-level one alone.

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/api/test_errors.py -v`
Expected: PASS, including every test that existed before.

- [ ] **Step 6: Regenerate the contract**

The `responses=` change alters the document.

Run: `just openapi && uv run pytest -m contract`
Expected: PASS. The diff on `openapi.json` shows three new response entries on every operation. Read it — that is the point of the gate.

- [ ] **Step 7: Commit**

```bash
git add -A examples/reference-service
git commit -m "fix(api): return problem details for framework-raised http errors"
```

---

## Task 4: An accurate `unit_amount` schema and a bounded order total

Two defects, both found by Schemathesis while this plan was written, both about the same value. Verified Facts 5, 6 and 7.

**Files:**
- Modify: `examples/reference-service/src/reference_service/api/v1/schemas.py`
- Modify: `examples/reference-service/src/reference_service/services/order.py`
- Test: `examples/reference-service/tests/api/test_orders.py`, `examples/reference-service/tests/unit/test_order_service.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `MAX_MONEY: Decimal` and `UnitAmount` in `api/v1/schemas.py`, both used by Task 12's payment work.

- [ ] **Step 1: Write the failing tests**

Append to `tests/api/test_orders.py`:

```python
def test_a_number_outside_moneys_range_is_rejected_at_the_edge(
    client: TestClient,
) -> None:
    """The published contract used to permit this and the app used to refuse it.

    Pydantic renders a constrained Decimal as anyOf[number, string] and
    puts `max_digits`/`decimal_places` on the STRING branch only, so the
    number branch said "any number >= 0". Schemathesis generated 1.06e308
    against that contract and got a 422 — a schema-compliant request the
    API rejected. The assertion here is unchanged behaviour; what changes
    is that the contract now says so.
    """
    response = client.post(
        "/api/v1/orders",
        json={
            "customer_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "lines": [
                {
                    "sku": "widget",
                    "quantity": 1,
                    "unit_amount": 1.0605661518203426e308,
                    "currency": "EUR",
                }
            ],
        },
    )

    assert response.status_code == 422


def test_an_order_whose_total_overflows_money_is_a_422_not_a_500(
    client: TestClient,
) -> None:
    """Two individually valid fields whose PRODUCT no Money can hold.

    quantity and unit_amount each carry a bound mirroring their storage
    column, and each is satisfied here. Their product is not: it exceeds
    NUMERIC(14, 2). Before this task, Money construction failed inside
    PlaceOrder, was wrapped as ServiceDefectError and returned 500 — a
    server error for ordinary, schema-valid client input.
    """
    response = client.post(
        "/api/v1/orders",
        json={
            "customer_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
            "lines": [
                {
                    "sku": "widget",
                    "quantity": 2_147_483_646,
                    "unit_amount": "272486.81",
                    "currency": "EUR",
                }
            ],
        },
    )

    assert response.status_code == 422
    assert response.headers["content-type"] == "application/problem+json"
```

And in `tests/unit/test_order_service.py`, the same rule at the command level, because a command must stand on its own for a non-HTTP caller — the reasoning already applied to `lines_must_share_one_currency`:

```python
def test_a_command_whose_total_overflows_money_is_rejected() -> None:
    with pytest.raises(PydanticValidationError, match="exceeds the maximum"):
        PlaceOrderCommand(
            customer_id=uuid4(),
            lines=[
                PlaceOrderLine(
                    sku="widget",
                    quantity=2_147_483_646,
                    unit_amount=Decimal("272486.81"),
                    currency="EUR",
                )
            ],
        )
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/api/test_orders.py tests/unit/test_order_service.py -k "overflow or outside_moneys" -v`
Expected: the first test FAILS only if the schema already changed (it passes today — keep it, it is the regression lock for the contract change in Step 3); the second and third FAIL, the API one with `assert 500 == 422`.

- [ ] **Step 3: Publish an accurate schema for `unit_amount`**

In `api/v1/schemas.py`, add the import and replace the field:

```python
from pydantic import BaseModel, Field, StringConstraints, WithJsonSchema, model_validator
```

```python
# NUMERIC(14, 2) in migrations/000001: twelve integer digits and two
# decimal places. One name for it, because three files need the same
# number and a second literal is a second thing to forget.
MAX_MONEY = Decimal("999999999999.99")

# The schema is written out rather than inferred, and that is the point.
#
# Pydantic renders a constrained Decimal as a two-branch anyOf, and the
# inferred version is wrong in both branches. The NUMBER branch gets only
# `minimum`: `max_digits` and `decimal_places` have no JSON Schema
# equivalent and are simply dropped, so the contract said any number >= 0
# was acceptable. The STRING branch gets a regex whose first alternative,
# `\d{0,12}`, has no closing `$` — and JSON Schema's `pattern` is
# explicitly a PARTIAL match, so "070" followed by arbitrary junk
# satisfies it. Both gaps were found by Schemathesis generating values the
# contract permitted and the model refused.
#
# Keeping this in step with the Field() constraints above it is exactly
# what the conformance gate does, on every run, by generating from this
# schema and asserting the model accepts the result. That is why it is
# safe to state it by hand here and nowhere else.
UnitAmount = Annotated[
    Decimal,
    Field(ge=0, le=MAX_MONEY, max_digits=14, decimal_places=2),
    WithJsonSchema(
        {
            "anyOf": [
                {
                    "type": "number",
                    "minimum": 0,
                    "maximum": 999999999999.99,
                    "multipleOf": 0.01,
                },
                {
                    "type": "string",
                    "pattern": r"^(0|[1-9][0-9]{0,11})(\.[0-9]{1,2})?$",
                },
            ],
            "title": "Unit Amount",
        }
    ),
]
```

Then `OrderLineIn.unit_amount` becomes simply:

```python
    unit_amount: UnitAmount
```

Keep the existing comment above it explaining that the bounds mirror `domain.order.Money.amount`; extend it with a pointer to `UnitAmount`'s docstring above.

- [ ] **Step 4: Bound the total**

Add to `PlaceOrderRequest`, beside `lines_must_share_one_currency`:

```python
    @model_validator(mode="after")
    def total_must_fit_in_money(self) -> Self:
        # A relationship between two fields of two different lines, so no
        # per-field constraint can express it — the same reason
        # lines_must_share_one_currency above exists. quantity and
        # unit_amount each satisfy their own bound while their PRODUCT
        # exceeds what NUMERIC(14, 2) can hold; Money then refuses to be
        # constructed inside PlaceOrder, which wrapped it as a
        # ServiceDefectError and returned 500 for ordinary client input.
        total = sum(
            (line.unit_amount * line.quantity for line in self.lines), Decimal(0)
        )
        if total > MAX_MONEY:
            raise ValueError(
                f"order total {total} exceeds the maximum representable "
                f"amount {MAX_MONEY}"
            )
        return self
```

And the mirror in `services/order.py`'s `PlaceOrderCommand`, with `MAX_ORDER_TOTAL = Decimal("999999999999.99")` declared there — the service layer must not import from `api`, so the constant is repeated rather than shared, exactly as the field constraints already are:

```python
    @model_validator(mode="after")
    def total_must_fit_in_money(self) -> Self:
        # Mirrors api/v1/schemas.py's validator of the same name, for the
        # reason the rest of this module's constraints mirror that
        # module's: a command must stand on its own for a non-HTTP caller.
        total = sum(
            (line.unit_amount * line.quantity for line in self.lines), Decimal(0)
        )
        if total > MAX_ORDER_TOTAL:
            raise ValueError(
                f"order total {total} exceeds the maximum representable "
                f"amount {MAX_ORDER_TOTAL}"
            )
        return self
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest`
Expected: PASS, all of them. Nothing that passed before may change.

- [ ] **Step 6: Regenerate the contract**

Run: `just openapi && uv run pytest -m contract`
Expected: PASS. The diff on `openapi.json` shows `unit_amount` gaining `maximum` and `multipleOf` on the number branch and a fully anchored pattern on the string branch.

- [ ] **Step 7: Commit**

```bash
git add -A examples/reference-service
git commit -m "fix(api): publish the real bounds for unit_amount and reject overflowing totals"
```

---

## Task 5: The conformance gate

**Files:**
- Create: `examples/reference-service/tests/contract/test_conformance.py`
- Create: `examples/reference-service/schemathesis.toml`

**Interfaces:**
- Consumes: the `contract` marker (Task 1), `openapi.json` (Task 2), and the fixes from Tasks 3 and 4 — without which this tier lands red.
- Produces: nothing other tasks import.

- [ ] **Step 1: Write the test**

```python
"""Schemathesis generates requests from the contract and checks the app.

Over ASGI, in-process: no server, no socket, no network. The schema is
read from the live app rather than from the committed openapi.json on
purpose — test_drift.py already proves those two are identical, and
reading the app means a failure here is never explained away as "the file
is stale".
"""

from __future__ import annotations

import schemathesis

from reference_service.main import create_app

app = create_app()
schema = schemathesis.openapi.from_asgi("/openapi.json", app)


@schema.parametrize()
def test_api_conforms_to_its_own_contract(case: schemathesis.Case) -> None:
    case.call_and_validate()
```

`@schema.parametrize()` produces one test per operation, so a failure names it: `test_api_conforms_to_its_own_contract[POST /api/v1/orders]`.

- [ ] **Step 2: Run it**

Run: `just test-contract`
Expected: one failure, on `POST /api/v1/orders`, reporting `API rejected schema-compliant request` with a 422. That is genuine: two rules on that operation are relationships *between* fields, which JSON Schema cannot express, so no contract can describe them and Schemathesis will always generate data that violates them.

- [ ] **Step 3: Record the exception, rather than disabling the check**

Create `schemathesis.toml` at the project root:

```toml
# Documented conformance exceptions. Spec 8.2 asks for exactly this: a
# reviewed list, not a disabled check. Every entry needs a reason that
# survives being read by someone who was not here.

[[operations]]
include-name = "POST /api/v1/orders"

# Two rules on this operation are relationships BETWEEN fields, and JSON
# Schema has no way to state either:
#
#   1. every line must share one currency
#   2. the sum of quantity x unit_amount must fit in NUMERIC(14, 2)
#
# So a generator working from the contract will always eventually produce
# a schema-valid request that breaks one of them, and 422 is the correct
# answer. Adding 422 here says "this operation has cross-field rules",
# which is true and specific.
#
# What is NOT relaxed: `not_a_server_error` stays on, so the 500 this
# operation used to return for an overflowing total would still fail the
# gate. That is the check that matters, and it is untouched.
checks.positive_data_acceptance.expected-statuses = ["2xx", "422"]
```

- [ ] **Step 4: Run it again**

Run: `just test-contract`
Expected: PASS, five operations.

- [ ] **Step 5: Confirm the tier is still deselected by default**

Run: `just test`
Expected: the same pass count as before this task, with the contract tests deselected. If any test outside `tests/contract/` fails here, re-read Verified Fact 4 — the marker or the conftest is not doing its job.

- [ ] **Step 6: Commit**

```bash
git add examples/reference-service/tests/contract/test_conformance.py \
        examples/reference-service/schemathesis.toml
git commit -m "test(reference-service): add schemathesis conformance over asgi"
```

---

## Task 6: The breaking-change gate and the version cross-check

The third contract gate. `oasdiff` says whether the API broke; the version says what the release claims. This fails the build when they disagree (spec 10.2).

**Files:**
- Create: `examples/reference-service/openapi.baseline.json`
- Create: `examples/reference-service/scripts/__init__.py`
- Create: `examples/reference-service/scripts/check_contract_compatibility.py`
- Create: `examples/reference-service/tests/unit/test_contract_compatibility.py`
- Modify: `examples/reference-service/justfile`

**Interfaces:**
- Consumes: `openapi.json` (Task 2).
- Produces: `Version`, `bump_is_sufficient`, `breaking_changes`, `main` in `scripts/check_contract_compatibility.py`; `just contract-gates` and `just contract-release`.

How the version reaches the contract, since the whole gate rests on it: `pyproject.toml`'s `version` becomes the installed distribution's metadata, which `src/reference_service/__init__.py` reads with `importlib.metadata.version()` into `__version__`, which `create_app` passes to `FastAPI(version=...)`, which lands in `openapi.json` as `info.version`. Verified that a plain `uv run` rebuilds the package after a version edit, so `just openapi` picks up a bump with no separate sync step.

- [ ] **Step 1: Write the failing unit test**

`tests/unit/test_contract_compatibility.py`. It tests the decision logic only — no Docker, so it belongs in the unit tier:

```python
"""The compatibility gate's own rules, without Docker.

`breaking_changes` shells out to oasdiff and is exercised by
`just contract-gates`; what is worth unit-testing is the rule that decides
whether a version bump admits a breaking change, because getting it wrong
in the lenient direction silently disables the whole gate.
"""

from __future__ import annotations

import pytest

from scripts.check_contract_compatibility import Version, bump_is_sufficient


@pytest.mark.parametrize(
    ("baseline", "current", "sufficient"),
    [
        # Below 1.0.0 the MINOR number carries breaking changes.
        ("0.1.0", "0.2.0", True),
        ("0.1.0", "1.0.0", True),
        ("0.1.0", "0.1.1", False),
        ("0.1.0", "0.1.0", False),
        # At and above 1.0.0 it is the major.
        ("1.4.2", "2.0.0", True),
        ("1.4.2", "1.5.0", False),
        ("1.4.2", "1.4.3", False),
    ],
)
def test_which_bumps_admit_a_breaking_change(
    baseline: str, current: str, sufficient: bool
) -> None:
    assert (
        bump_is_sufficient(Version.parse(baseline), Version.parse(current))
        is sufficient
    )


def test_a_non_semantic_version_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="not a semantic version"):
        Version.parse("1.2")
```

- [ ] **Step 2: Run it and watch it fail**

Run: `uv run pytest tests/unit/test_contract_compatibility.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts'`.

(The import works once the package exists: `tests/` and `tests/unit/` both have `__init__.py`, so pytest inserts the project root on `sys.path`. Verified.)

- [ ] **Step 3: Write the script**

Create `scripts/__init__.py` (empty) and `scripts/check_contract_compatibility.py`:

```python
"""Fail the build when a breaking API change ships without a version bump.

`oasdiff` says whether the API broke. `pyproject.toml`'s version says what
the release claims. These can disagree — someone removes a response field
and leaves the version alone — and when they do, a client pinned to a
compatible range breaks in production. This is the gate that stops it
(spec 10.2).

M5 replaces the version comparison here with the Conventional Commits
range check, once tags and Commitizen exist. The oasdiff half stays.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

OASDIFF_IMAGE = "tufin/oasdiff:v1.31.0"

# oasdiff's own severity scale: 3 is `error`, its word for breaking; 2 is
# `warning` and 1 is `info`, neither of which blocks.
BREAKING_LEVEL = 3

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE = PROJECT_ROOT / "openapi.baseline.json"
CURRENT = PROJECT_ROOT / "openapi.json"


class Version(tuple[int, int, int]):
    """A semantic version, compared as a tuple."""

    @classmethod
    def parse(cls, raw: str) -> Version:
        parts = raw.split(".")
        if len(parts) != 3 or not all(part.isdigit() for part in parts):
            raise ValueError(f"not a semantic version: {raw!r}")
        return cls(int(part) for part in parts)


def bump_is_sufficient(baseline: Version, current: Version) -> bool:
    """Does the version change admit a breaking API change?

    Below 1.0.0 semver puts no compatibility promise on the major number,
    and the convention every tool follows is that the MINOR number carries
    breaking changes: 0.1.0 -> 0.2.0. At and above 1.0.0 it is the major.
    Getting this wrong in the lenient direction would let every pre-1.0
    break through unnoticed, which is most of this project's life so far.
    """
    if baseline[0] == 0:
        return current[:2] > baseline[:2]
    return current[0] > baseline[0]


def read_version(document: Path) -> Version:
    return Version.parse(json.loads(document.read_text())["info"]["version"])


def breaking_changes(baseline: Path, current: Path) -> list[dict[str, object]]:
    """Run oasdiff in its pinned image and return only the breaking findings.

    The image rather than a local binary: oasdiff is a Go program, and
    requiring a Go toolchain to check a Python service's contract is a
    cost every contributor would pay forever.
    """
    completed = subprocess.run(
        [
            "docker", "run", "--rm",
            "-v", f"{baseline.parent}:/w",
            OASDIFF_IMAGE,
            "breaking", f"/w/{baseline.name}", f"/w/{current.name}",
            "-f", "json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    # oasdiff exits 1 when it FINDS breaking changes, which is not an
    # error. Anything above 1 is: a missing image, an unreadable file, a
    # malformed document. Distinguishing them is what stops a broken
    # docker install from quietly reading as "no breaking changes" — the
    # single most dangerous way for this gate to fail.
    if completed.returncode > 1:
        raise RuntimeError(
            f"oasdiff failed with exit {completed.returncode}: {completed.stderr}"
        )
    findings = json.loads(completed.stdout or "[]")
    return [f for f in findings if f.get("level") == BREAKING_LEVEL]


def _render(version: Version) -> str:
    return ".".join(str(part) for part in version)


def main() -> int:
    baseline_version = read_version(BASELINE)
    current_version = read_version(CURRENT)
    findings = breaking_changes(BASELINE, CURRENT)

    if not findings:
        print(f"No breaking API changes against {_render(baseline_version)}.")
        return 0

    if bump_is_sufficient(baseline_version, current_version):
        print(
            f"{len(findings)} breaking change(s), and the version was bumped "
            f"{_render(baseline_version)} -> {_render(current_version)}. Allowed."
        )
        return 0

    print(
        f"BREAKING API CHANGE with no matching version bump.\n"
        f"  baseline: {_render(baseline_version)}\n"
        f"  current:  {_render(current_version)}\n",
        file=sys.stderr,
    )
    for finding in findings:
        print(
            f"  [{finding['id']}] {finding['operation']} {finding['path']}\n"
            f"      {finding['text']}",
            file=sys.stderr,
        )
    print(
        "\nEither undo the change, or bump the version in pyproject.toml and "
        "regenerate the contract with `just openapi`.",
        file=sys.stderr,
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Run the unit test**

Run: `uv run pytest tests/unit/test_contract_compatibility.py -v`
Expected: PASS, eight cases.

- [ ] **Step 5: Create the baseline and the recipes**

```bash
cp openapi.json openapi.baseline.json
```

```just
# The two contract gates that need Docker or the committed baseline.
# `test-contract` (Schemathesis) and the drift gate run without either.
contract-gates:
    uv run pytest -m contract
    uv run python scripts/check_contract_compatibility.py

# Promote the current contract to the baseline. Run this as part of
# CUTTING a release, never to make `contract-gates` stop complaining:
# silencing it that way is precisely the silent breaking change the gate
# exists to catch (spec 10.2).
contract-release:
    cp openapi.json openapi.baseline.json
```

Add `contract-gates` to `check-all`:

```just
check-all: check test-integration gates o11y-gates contract-gates
```

- [ ] **Step 6: Prove the gate fails, then passes**

Verified while writing this plan, and worth reproducing once:

```bash
# Breaking change, no bump.
python3 -c "
import json; from pathlib import Path
s = json.loads(Path('openapi.json').read_text())
del s['components']['schemas']['OrderResponse']['properties']['total']
Path('openapi.json').write_text(json.dumps(s, indent=2, sort_keys=True) + '\n')"
uv run python scripts/check_contract_compatibility.py; echo "exit=$?"
```

Expected: `exit=1`, naming both `response-required-property-removed` findings.

```bash
# Same change, version bumped.
python3 -c "
import json; from pathlib import Path
s = json.loads(Path('openapi.json').read_text()); s['info']['version'] = '0.2.0'
Path('openapi.json').write_text(json.dumps(s, indent=2, sort_keys=True) + '\n')"
uv run python scripts/check_contract_compatibility.py; echo "exit=$?"
```

Expected: `exit=0`, `2 breaking change(s), and the version was bumped 0.1.0 -> 0.2.0. Allowed.`

Then restore: `just openapi` and confirm `uv run python scripts/check_contract_compatibility.py` prints `No breaking API changes against 0.1.0.`

- [ ] **Step 7: Commit**

```bash
git add -A examples/reference-service
git commit -m "feat(reference-service): gate breaking api changes against the version"
```

---

## Task 7: The circuit breaker

Pure state machine. No HTTP, no I/O, no sleeping — an injected clock instead, so its tests run in microseconds and never flake.

**Files:**
- Create: `examples/reference-service/src/reference_service/infrastructure/http/__init__.py`
- Create: `examples/reference-service/src/reference_service/infrastructure/http/breaker.py`
- Create: `examples/reference-service/tests/unit/test_breaker.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `BreakerState`, `CircuitOpenError`, and `CircuitBreaker(*, failure_threshold: int, reset_after_seconds: float, clock: Callable[[], float] = time.monotonic)` with `state: BreakerState` and `async call(operation: Callable[[], Awaitable[T]]) -> T`. Task 10 uses `call`.

- [ ] **Step 1: Write the failing tests**

```python
"""The breaker's state machine, against a clock we control.

Every test here would otherwise need to sleep through the reset window,
which is the reason breaker tests are usually slow and flaky. The clock is
a constructor argument precisely so they are neither.
"""

from __future__ import annotations

import pytest

from reference_service.infrastructure.http.breaker import (
    BreakerState,
    CircuitBreaker,
    CircuitOpenError,
)


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def advance(self, seconds: float) -> None:
        self.now += seconds


class Boom(Exception):
    pass


def make_breaker(clock: FakeClock) -> CircuitBreaker:
    return CircuitBreaker(failure_threshold=3, reset_after_seconds=30.0, clock=clock)


async def succeed() -> str:
    return "ok"


async def fail() -> str:
    raise Boom


async def test_a_new_breaker_is_closed_and_passes_calls_through() -> None:
    breaker = make_breaker(FakeClock())

    assert breaker.state is BreakerState.CLOSED
    assert await breaker.call(succeed) == "ok"


async def test_it_opens_only_after_the_threshold_is_reached() -> None:
    breaker = make_breaker(FakeClock())

    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail)
    assert breaker.state is BreakerState.CLOSED, "two failures is not three"

    with pytest.raises(Boom):
        await breaker.call(fail)
    assert breaker.state is BreakerState.OPEN


async def test_the_failure_count_is_consecutive_not_cumulative() -> None:
    """A success resets the count. Otherwise a service failing 1% of the
    time trips the breaker after a few hundred healthy requests."""
    breaker = make_breaker(FakeClock())

    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail)
    await breaker.call(succeed)
    for _ in range(2):
        with pytest.raises(Boom):
            await breaker.call(fail)

    assert breaker.state is BreakerState.CLOSED


async def test_an_open_breaker_refuses_without_calling() -> None:
    clock = FakeClock()
    breaker = make_breaker(clock)
    calls = 0

    async def count() -> str:
        nonlocal calls
        calls += 1
        raise Boom

    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(count)
    assert calls == 3

    with pytest.raises(CircuitOpenError):
        await breaker.call(count)
    assert calls == 3, "an open breaker must not reach the dependency at all"


async def test_it_half_opens_once_the_reset_window_has_passed() -> None:
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail)

    clock.advance(29.9)
    assert breaker.state is BreakerState.OPEN

    clock.advance(0.1)
    assert breaker.state is BreakerState.HALF_OPEN


async def test_a_successful_probe_closes_the_breaker() -> None:
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail)
    clock.advance(30.0)

    assert await breaker.call(succeed) == "ok"
    assert breaker.state is BreakerState.CLOSED


async def test_a_failed_probe_reopens_immediately() -> None:
    """One failure, not another full threshold. The dependency has already
    proved it is unwell; making it fail three more times to say so again
    just sends three more doomed requests into it."""
    clock = FakeClock()
    breaker = make_breaker(clock)
    for _ in range(3):
        with pytest.raises(Boom):
            await breaker.call(fail)
    clock.advance(30.0)

    with pytest.raises(Boom):
        await breaker.call(fail)

    assert breaker.state is BreakerState.OPEN
    clock.advance(29.9)
    assert breaker.state is BreakerState.OPEN, "the window restarts from the probe"


async def test_a_threshold_below_one_is_refused() -> None:
    with pytest.raises(ValueError, match="failure_threshold"):
        CircuitBreaker(failure_threshold=0, reset_after_seconds=1.0)
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/unit/test_breaker.py -v`
Expected: collection error — `No module named 'reference_service.infrastructure.http'`.

- [ ] **Step 3: Write the breaker**

Create `infrastructure/http/__init__.py` (empty) and `infrastructure/http/breaker.py`:

```python
"""A circuit breaker for one outbound dependency.

Written rather than depended on. The two asyncio implementations on PyPI
were last released in 2021 and 2022; the one maintained package,
pybreaker, offers Tornado coroutines rather than `await`. Eighty lines
that this service's own tests cover is the smaller long-term cost.

What it is: after N consecutive failures the breaker OPENS and refuses
calls outright for a cool-down window, instead of letting every request
queue behind a dependency that is already down. Once the window passes it
goes HALF-OPEN and admits a single probe: if that succeeds the breaker
closes, if it fails the window starts again. Without it, one slow
dependency consumes every connection and worker this service has, and a
partial outage becomes a total one.

Deliberately not thread-safe, and it does not need to be: this service
runs one event loop per process, and every mutation below happens between
`await` points, so no other coroutine can observe a half-updated state.
"""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from enum import StrEnum
from typing import TypeVar

T = TypeVar("T")


class BreakerState(StrEnum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitOpenError(Exception):
    """The breaker refused the call without attempting it.

    Distinct from any error the dependency itself raises, because it means
    something different to the caller: the dependency was not asked. The
    adapter maps it onto the same "unavailable" outcome as a timeout,
    which is honest — from the caller's side both mean "no answer" — but
    keeping the type separate is what lets a log line say which happened.
    """


class CircuitBreaker:
    def __init__(
        self,
        *,
        failure_threshold: int,
        reset_after_seconds: float,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if failure_threshold < 1:
            raise ValueError(f"failure_threshold must be >= 1, got {failure_threshold}")
        if reset_after_seconds <= 0:
            raise ValueError(
                f"reset_after_seconds must be > 0, got {reset_after_seconds}"
            )
        self._failure_threshold = failure_threshold
        self._reset_after_seconds = reset_after_seconds
        # `time.monotonic` by default, never `time.time`: a wall clock can
        # step backwards when the host syncs, which would leave an open
        # breaker refusing calls until the clock caught up again.
        self._clock = clock
        self._consecutive_failures = 0
        self._opened_at: float | None = None
        self._probe_in_flight = False

    @property
    def state(self) -> BreakerState:
        """Derived, never stored.

        Storing HALF_OPEN would mean something has to notice the window
        expiring and write it — a timer, or a check on every call. Deriving
        it from the clock means the transition simply happens.
        """
        if self._opened_at is None:
            return BreakerState.CLOSED
        if self._clock() - self._opened_at >= self._reset_after_seconds:
            return BreakerState.HALF_OPEN
        return BreakerState.OPEN

    async def call(self, operation: Callable[[], Awaitable[T]]) -> T:
        """Run `operation`, or refuse it if the circuit is open.

        Every exception counts as a failure, so the CALLER decides what
        counts as one by choosing what to raise. This matters for
        payments: a declined card is a successful call with a negative
        answer, and the adapter therefore returns the response from here
        and interprets it outside — a decline must never trip the breaker.
        """
        state = self.state
        if state is BreakerState.OPEN:
            opened_at = self._opened_at or 0.0
            remaining = self._reset_after_seconds - (self._clock() - opened_at)
            raise CircuitOpenError(f"circuit open; retrying in {remaining:.1f}s")

        is_probe = state is BreakerState.HALF_OPEN
        if is_probe:
            if self._probe_in_flight:
                # One probe at a time. Without this, every request that
                # arrives during the half-open moment is sent at a
                # dependency that has not yet proved it recovered — the
                # thundering herd the breaker exists to prevent, delivered
                # precisely when the dependency is most fragile.
                raise CircuitOpenError("circuit half-open; a probe is already running")
            self._probe_in_flight = True

        try:
            result = await operation()
        except Exception:
            self._record_failure(is_probe=is_probe)
            raise
        else:
            self._record_success()
            return result
        finally:
            if is_probe:
                self._probe_in_flight = False

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._opened_at = None

    def _record_failure(self, *, is_probe: bool) -> None:
        self._consecutive_failures += 1
        # A failed probe reopens on its own: the dependency has already
        # shown it is unwell, and making it fail another full threshold to
        # say so again just sends more doomed requests into it.
        if is_probe or self._consecutive_failures >= self._failure_threshold:
            self._opened_at = self._clock()
```

- [ ] **Step 4: Run the tests**

Run: `uv run pytest tests/unit/test_breaker.py -v`
Expected: PASS, eight tests, in well under a second — no test sleeps.

- [ ] **Step 5: Commit**

```bash
git add examples/reference-service/src/reference_service/infrastructure/http \
        examples/reference-service/tests/unit/test_breaker.py
git commit -m "feat(reference-service): add a circuit breaker for outbound calls"
```

---

## Task 8: Settings and the shared client

**Files:**
- Modify: `examples/reference-service/src/reference_service/settings.py`
- Create: `examples/reference-service/src/reference_service/infrastructure/http/client.py`
- Create: `examples/reference-service/tests/unit/test_http_client.py`
- Modify: `examples/reference-service/.env.example`

**Interfaces:**
- Consumes: nothing.
- Produces: `HttpClientSettings`, `PaymentSettings`, `Settings.payment`; `build_http_client(settings: HttpClientSettings, *, base_url: str, headers: Mapping[str, str] | None = None) -> httpx.AsyncClient`; `is_retryable(exc: Exception) -> bool`; `RETRYABLE_STATUS: frozenset[int]`.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_http_client.py`:

```python
"""The client's two policies: timeouts, and what may be retried."""

from __future__ import annotations

import httpx
import pytest

from reference_service.infrastructure.http.client import (
    build_http_client,
    is_retryable,
)
from reference_service.settings import HttpClientSettings


async def test_every_timeout_phase_is_set() -> None:
    """httpx's default is five seconds on every phase, but a client
    constructed with `timeout=None` anywhere waits forever, and that is
    the single most common way one slow dependency freezes a whole
    service (spec 12, item 5). Assert all four explicitly."""
    client = build_http_client(HttpClientSettings(), base_url="http://gateway")

    timeout = client.timeout
    assert timeout.connect is not None
    assert timeout.read is not None
    assert timeout.write is not None
    assert timeout.pool is not None
    await client.aclose()


async def test_the_timeouts_come_from_settings() -> None:
    settings = HttpClientSettings(
        connect_timeout_seconds=0.5,
        read_timeout_seconds=1.5,
        write_timeout_seconds=2.5,
        pool_timeout_seconds=3.5,
    )

    client = build_http_client(settings, base_url="http://gateway")

    assert client.timeout.connect == 0.5
    assert client.timeout.read == 1.5
    assert client.timeout.write == 2.5
    assert client.timeout.pool == 3.5
    await client.aclose()


def _status_error(code: int) -> httpx.HTTPStatusError:
    request = httpx.Request("POST", "http://gateway/authorisations")
    return httpx.HTTPStatusError(
        f"{code}", request=request, response=httpx.Response(code, request=request)
    )


@pytest.mark.parametrize(
    ("error", "retryable", "why"),
    [
        (
            httpx.ConnectError("refused", request=None),
            True,
            "the request provably never arrived",
        ),
        (
            httpx.ConnectTimeout("timed out", request=None),
            True,
            "likewise: no connection, so nothing was submitted",
        ),
        (
            httpx.ReadTimeout("timed out", request=None),
            False,
            "the gateway may have taken the payment and been slow to say so",
        ),
        (_status_error(429), True, "the gateway asked us to come back"),
        (_status_error(503), True, "the gateway did not process it"),
        (_status_error(500), False, "ambiguous: it may have processed it"),
        (_status_error(402), False, "a decline is an answer, not a failure"),
        (_status_error(400), False, "our request is wrong; repeating it will not help"),
    ],
)
def test_what_may_be_retried(error: Exception, retryable: bool, why: str) -> None:
    assert is_retryable(error) is retryable, why
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/unit/test_http_client.py -v`
Expected: collection error — `cannot import name 'build_http_client'`.

- [ ] **Step 3: Add the settings**

In `settings.py`, above `Settings`:

```python
class HttpClientSettings(BaseModel):
    # See LogSettings.model_config for why each sub-model needs its own
    # frozen=True rather than inheriting it.
    model_config = ConfigDict(frozen=True)

    # Four phases, four separate deadlines, none of them optional. httpx
    # accepts None for "wait forever" on any of them, and a client built
    # that way is indistinguishable from a working one until the day the
    # dependency stops answering.
    connect_timeout_seconds: float = Field(default=2.0, gt=0)
    read_timeout_seconds: float = Field(default=5.0, gt=0)
    write_timeout_seconds: float = Field(default=5.0, gt=0)
    # How long a request may wait for a free connection from the pool. It
    # is the one people forget: with the pool exhausted, requests queue
    # here rather than at the socket, and an unbounded wait turns a slow
    # dependency into a stalled service just as effectively.
    pool_timeout_seconds: float = Field(default=1.0, gt=0)

    max_connections: int = Field(default=20, ge=1)
    max_keepalive_connections: int = Field(default=10, ge=0)


class PaymentSettings(BaseModel):
    model_config = ConfigDict(frozen=True)

    base_url: HttpUrl
    # SecretStr so it cannot reach a log or a traceback by being
    # interpolated somewhere careless — its repr is "**********".
    api_key: SecretStr | None = None
    http: HttpClientSettings = Field(default_factory=HttpClientSettings)

    # Attempts, not retries: 3 means one call and two further tries.
    retry_attempts: int = Field(default=3, ge=1)
    retry_initial_wait_seconds: float = Field(default=0.1, gt=0)
    retry_max_wait_seconds: float = Field(default=2.0, gt=0)

    breaker_failure_threshold: int = Field(default=5, ge=1)
    breaker_reset_after_seconds: float = Field(default=30.0, gt=0)
```

Add the imports `HttpUrl` and `SecretStr` from pydantic, and the field on `Settings`, beside `database` and for the same reason:

```python
    # Optional on purpose: None selects the in-memory gateway, which is
    # what keeps `just dev` working with no payment provider anywhere —
    # the same arrangement `database` above has with the in-memory
    # repository.
    payment: PaymentSettings | None = None
```

Document it in `.env.example`:

```bash
# The payment provider. Leave unset to use the in-memory gateway, which
# authorises everything — that is the default and needs no upstream.
# `just up` sets this to the local stub in compose.yaml.
# APP_PAYMENT__BASE_URL=http://localhost:9099
# APP_PAYMENT__API_KEY=
# Four separate deadlines, in seconds. None may be zero or unset.
# APP_PAYMENT__HTTP__CONNECT_TIMEOUT_SECONDS=2.0
# APP_PAYMENT__HTTP__READ_TIMEOUT_SECONDS=5.0
# Consecutive failures before the circuit opens, and how long it stays
# open before admitting one probe.
# APP_PAYMENT__BREAKER_FAILURE_THRESHOLD=5
# APP_PAYMENT__BREAKER_RESET_AFTER_SECONDS=30.0
```

- [ ] **Step 4: Write the client**

`infrastructure/http/client.py`:

```python
"""The shared outbound HTTP client and its retry policy.

One client per process, built in the composition root and closed at
shutdown. Not one per request: a fresh client per call throws away the
connection pool, so every outbound request pays a new TCP and TLS
handshake, and nothing bounds how many sockets the service opens.
"""

from __future__ import annotations

from collections.abc import Mapping

import httpx

from reference_service.settings import HttpClientSettings

# Statuses where retrying is safe AND might help.
#
# 429 is the gateway asking us to come back. 502, 503 and 504 all say the
# request was not processed by the thing behind the gateway. 500 is
# deliberately ABSENT: it is ambiguous — the gateway may have taken the
# payment and then failed while telling us — and retrying an ambiguous
# failure on a non-idempotent POST is how a customer gets charged twice.
RETRYABLE_STATUS = frozenset({429, 502, 503, 504})


def is_retryable(exc: Exception) -> bool:
    """What may be retried, and — more to the point — what may not.

    The rule is "can this have been delivered?", not "did this fail?".

    A ConnectError or ConnectTimeout proves the request never reached the
    gateway, so a second attempt cannot authorise twice. A ReadTimeout
    proves nothing of the sort: the gateway may have taken the payment and
    simply been slow to say so, and retrying that is a double charge.
    Making read timeouts safe needs an idempotency key the gateway
    honours, which is M9 — until then this stays narrow on purpose.
    """
    if isinstance(exc, httpx.ConnectError | httpx.ConnectTimeout):
        return True
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in RETRYABLE_STATUS
    return False


def build_http_client(
    settings: HttpClientSettings,
    *,
    base_url: str,
    headers: Mapping[str, str] | None = None,
) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        base_url=base_url,
        headers=dict(headers or {}),
        # Every phase named explicitly. `httpx.Timeout(5.0)` would set all
        # four, but writing them out is what makes a reviewer notice if
        # one is ever dropped.
        timeout=httpx.Timeout(
            connect=settings.connect_timeout_seconds,
            read=settings.read_timeout_seconds,
            write=settings.write_timeout_seconds,
            pool=settings.pool_timeout_seconds,
        ),
        limits=httpx.Limits(
            max_connections=settings.max_connections,
            max_keepalive_connections=settings.max_keepalive_connections,
        ),
    )
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_http_client.py -v`
Expected: PASS, ten cases.

- [ ] **Step 6: Commit**

```bash
git add -A examples/reference-service
git commit -m "feat(reference-service): add the shared outbound http client and its settings"
```

---

## Task 9: The payment port

The domain names the operation. It does not know HTTP exists.

**Files:**
- Create: `examples/reference-service/src/reference_service/domain/payments.py`
- Modify: `examples/reference-service/src/reference_service/domain/errors.py`
- Modify: `examples/reference-service/src/reference_service/infrastructure/errors.py`
- Modify: `examples/reference-service/.importlinter`
- Test: `examples/reference-service/tests/unit/test_layer_purity.py` (no change needed; it must keep passing)

**Interfaces:**
- Consumes: `OrderId`, `Money` from `domain/order.py`.
- Produces: `AuthorisationId`, `Authorisation`, `PaymentGateway` (Protocol) in `domain/payments.py`; `PaymentDeclinedError` in `domain/errors.py`; `PaymentUnavailableError` in `infrastructure/errors.py`.

- [ ] **Step 1: Extend the import contracts first**

In `.importlinter`, add `httpx` and `stamina` to `forbidden_modules` in **both** the `domain-independence` and `services-independence` contracts, after `opentelemetry`:

```ini
    opentelemetry
    httpx
    stamina
```

Run: `just imports`
Expected: PASS — nothing imports them yet. This is the gate going in before the code it guards, which is the only ordering that proves it was ever off.

- [ ] **Step 2: Write the failing test**

Add to `tests/unit/test_order.py` (the domain's own test module):

```python
def test_an_authorisation_is_a_frozen_value_object() -> None:
    authorisation = Authorisation(id=AuthorisationId("auth_123"))

    with pytest.raises(PydanticValidationError):
        authorisation.id = AuthorisationId("auth_456")  # type: ignore[misc]


def test_the_payment_gateway_port_is_structural() -> None:
    """Anything with the right shape satisfies it — no base class, no
    import of ours in the implementer. That is what makes the domain able
    to name the operation without knowing who performs it."""

    class Stub:
        async def authorise(
            self, *, order_id: OrderId, total: Money
        ) -> Authorisation:
            return Authorisation(id=AuthorisationId("auth_123"))

    gateway: PaymentGateway = Stub()
    assert gateway is not None
```

- [ ] **Step 3: Add `AuthorisationId` to the aggregate's module**

In `domain/order.py`, beside the existing `NewType`s:

```python
AuthorisationId = NewType("AuthorisationId", str)
```

It lives here rather than in `payments.py` because `Order` carries one in
Task 12, and `payments.py` already imports from `order.py` — defining it
there and importing it back would be a cycle.

- [ ] **Step 4: Write the port**

`domain/payments.py`:

```python
"""The payment port: what the domain needs, not how it is done.

Imports Pydantic and the standard library, exactly as the rest of this
layer does. `httpx` lives on the far side of this file, in
infrastructure/http/payment_gateway.py — the domain names the operation
and never learns that it travels over HTTP.

Two errors can come out of an implementation, and they belong in
different places on purpose:

  - PaymentDeclinedError (domain/errors.py) — the gateway answered, and
    the answer was no. A statement about the caller's payment instrument,
    so a business rule, so 4xx.
  - PaymentUnavailableError (infrastructure/errors.py) — the gateway did
    not answer at all, or the circuit was open. A statement about our
    dependency, not the caller, so 5xx.

The second lives in infrastructure for the same reason
CorruptPersistedDataError does: it is raised by the adapter, and
infrastructure must not import services.
"""

from __future__ import annotations

from typing import Protocol

from pydantic import BaseModel, ConfigDict

from reference_service.domain.order import AuthorisationId, Money, OrderId


class Authorisation(BaseModel):
    """Proof that a payment was authorised. A value object: no identity of
    its own beyond the reference the provider gave us."""

    model_config = ConfigDict(frozen=True)

    id: AuthorisationId


class PaymentGateway(Protocol):
    """Authorise a payment, or say why not.

    Raises `PaymentDeclinedError` when the provider says no, and
    `PaymentUnavailableError` when there is no answer to be had. Returning
    a "failed" Authorisation instead would let a caller forget to check
    it; raising cannot be ignored by accident.
    """

    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation: ...
```

- [ ] **Step 5: Add the two errors**

In `domain/errors.py`:

```python
class PaymentDeclinedError(DomainError):
    """The provider answered, and the answer was no.

    A business outcome, not a failure: the call succeeded. It must never
    be retried (that re-submits a payment) and must never trip the circuit
    breaker (the dependency is healthy — it just said no).
    """

    code = "payment_declined"
    title = "Payment declined"

    def __init__(self, order_id: OrderId, reason: str) -> None:
        self.order_id = order_id
        self.reason = reason
        super().__init__(f"payment for order {order_id} was declined: {reason}")
```

In `infrastructure/errors.py`:

```python
class PaymentUnavailableError(Exception):
    """The payment provider could not be reached, or the circuit is open.

    Not a DomainError, and deliberately so: the caller did nothing wrong,
    and the request may well succeed if repeated later. Unlike its
    siblings in this module it DOES get a registered handler in
    api/errors.py, mapping it to 503 with a Retry-After — a 500 would tell
    a client "this is broken, do not come back", which is the wrong advice
    for a dependency that is merely down right now.
    """
```

- [ ] **Step 6: Run the gates**

Run: `just imports && uv run pytest tests/unit/test_layer_purity.py tests/unit/test_order.py -v`
Expected: PASS. The purity test is the one that matters here: the domain gained a file and still imports nothing but Pydantic.

- [ ] **Step 7: Commit**

```bash
git add -A examples/reference-service
git commit -m "feat(domain): add the payment gateway port and its two failure modes"
```

---

## Task 10: The payment gateway adapter

Where retry, breaker and HTTP meet. The nesting here is the whole point — see Verified Fact 18 for the measured behaviour this task must reproduce.

**Files:**
- Create: `examples/reference-service/src/reference_service/infrastructure/http/payment_gateway.py`
- Create: `examples/reference-service/src/reference_service/infrastructure/memory/payment_gateway.py`
- Create: `examples/reference-service/tests/unit/test_payment_gateway.py`

**Interfaces:**
- Consumes: `CircuitBreaker`, `CircuitOpenError` (Task 7); `is_retryable`, `build_http_client` (Task 8); `PaymentGateway`, `Authorisation`, `AuthorisationId` (Task 9); `PaymentDeclinedError`, `PaymentUnavailableError` (Task 9).
- Produces: `HttpPaymentGateway(client, *, breaker, attempts, wait_initial_seconds, wait_max_seconds)` and `InMemoryPaymentGateway()`, both satisfying the `PaymentGateway` protocol.

- [ ] **Step 1: Write the failing tests**

`tests/unit/test_payment_gateway.py`. `httpx.MockTransport` drives the adapter with no network and no cassette — cassettes come in Task 11 and cover the real wire format; these cover the policy:

```python
"""The adapter's decisions: what is an answer, what is a failure, and
which of those the breaker is allowed to count."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import httpx
import pytest
import stamina

from reference_service.domain.errors import PaymentDeclinedError
from reference_service.domain.order import Money, OrderId
from reference_service.infrastructure.errors import PaymentUnavailableError
from reference_service.infrastructure.http.breaker import CircuitBreaker
from reference_service.infrastructure.http.payment_gateway import HttpPaymentGateway

TOTAL = Money(amount=Decimal("42.00"), currency="EUR")


@pytest.fixture(autouse=True)
def _no_backoff() -> None:
    """Keep the configured attempt count, drop the waiting.

    NOT a plain `set_testing(True)`: that sets attempts to 1, which would
    make `test_a_retryable_failure_is_one_logical_failure` below pass
    while proving nothing. `cap=True` keeps the smaller configured value.
    """
    with stamina.set_testing(True, attempts=100, cap=True):
        yield


def build_gateway(
    handler: object, *, breaker: CircuitBreaker | None = None
) -> tuple[HttpPaymentGateway, httpx.AsyncClient]:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(handler),  # type: ignore[arg-type]
        base_url="http://gateway",
    )
    gateway = HttpPaymentGateway(
        client,
        breaker=breaker
        or CircuitBreaker(failure_threshold=2, reset_after_seconds=30.0),
        attempts=3,
        wait_initial_seconds=0.01,
        wait_max_seconds=0.02,
    )
    return gateway, client


async def test_an_authorised_payment_returns_its_reference() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": "auth_abc123", "status": "authorised"})

    gateway, client = build_gateway(handler)
    try:
        authorisation = await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert authorisation.id == "auth_abc123"


async def test_a_decline_is_an_answer_not_a_failure() -> None:
    """One request, no retry, and the breaker stays closed. Retrying a
    decline re-submits a payment; counting it as a failure would open the
    circuit against a gateway that is working perfectly."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(402, json={"reason": "insufficient_funds"})

    breaker = CircuitBreaker(failure_threshold=2, reset_after_seconds=30.0)
    gateway, client = build_gateway(handler, breaker=breaker)
    try:
        with pytest.raises(PaymentDeclinedError, match="insufficient_funds"):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert calls == 1
    assert breaker.state.value == "closed"


async def test_a_retryable_failure_is_retried_and_counts_once() -> None:
    """Three upstream requests, ONE logical failure. The breaker counts
    logical calls; nested the other way round it would open three times
    faster than its threshold says."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={})

    breaker = CircuitBreaker(failure_threshold=2, reset_after_seconds=30.0)
    gateway, client = build_gateway(handler, breaker=breaker)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert calls == 3
    assert breaker.state.value == "closed", "one logical failure, threshold is two"


async def test_an_open_circuit_reports_unavailable_without_calling() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503, json={})

    breaker = CircuitBreaker(failure_threshold=1, reset_after_seconds=30.0)
    gateway, client = build_gateway(handler, breaker=breaker)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
        calls_after_first = calls

        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert calls == calls_after_first, "an open circuit must not reach the gateway"


async def test_a_connect_failure_is_retried_then_reported_unavailable() -> None:
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ConnectError("connection refused", request=request)

    gateway, client = build_gateway(handler)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert calls == 3


async def test_a_read_timeout_is_not_retried() -> None:
    """The gateway may have taken the payment and been slow to say so.
    Retrying that is a double charge — see is_retryable's docstring."""
    calls = 0

    def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        raise httpx.ReadTimeout("too slow", request=request)

    gateway, client = build_gateway(handler)
    try:
        with pytest.raises(PaymentUnavailableError):
            await gateway.authorise(order_id=OrderId(uuid4()), total=TOTAL)
    finally:
        await client.aclose()

    assert calls == 1


async def test_the_request_carries_an_idempotency_key_and_the_amount() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"id": "auth_abc123", "status": "authorised"})

    order_id = OrderId(uuid4())
    gateway, client = build_gateway(handler)
    try:
        await gateway.authorise(order_id=order_id, total=TOTAL)
    finally:
        await client.aclose()

    request = seen[0]
    assert request.headers["idempotency-key"] == str(order_id)
    # A string, never a float. 42.00 as JSON number round-trips through a
    # binary double and can arrive as 42.000000000000004; money is sent as
    # text for the same reason MoneyOut renders it as text.
    assert b'"amount":"42.00"' in request.content.replace(b" ", b"")
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/unit/test_payment_gateway.py -v`
Expected: collection error — no `payment_gateway` module.

- [ ] **Step 3: Write the adapter**

`infrastructure/http/payment_gateway.py`:

```python
"""The HTTP implementation of the payment port.

Three layers, and their order is the design:

    breaker( retry( one HTTP request ) )

The breaker is OUTSIDE. Retries are attempts at one logical call, so
three retries against a dead gateway must register as one failure. Nested
the other way, the breaker would open at a third of its configured
threshold and nobody would understand why.

And a declined payment is neither: it is a successful call with a
negative answer. It never retries and never counts towards the breaker,
which is why `_send` returns 402 as a value rather than raising.
"""

from __future__ import annotations

import httpx
import stamina
import structlog

from reference_service.domain.errors import PaymentDeclinedError
from reference_service.domain.order import Money, OrderId
from reference_service.domain.payments import Authorisation, AuthorisationId
from reference_service.infrastructure.errors import PaymentUnavailableError
from reference_service.infrastructure.http.breaker import (
    CircuitBreaker,
    CircuitOpenError,
)
from reference_service.infrastructure.http.client import is_retryable

# Statuses that are ANSWERS rather than failures: the gateway considered
# the request and replied. Everything else is a failure the breaker and
# the retry policy get to see.
_ANSWER_STATUSES = frozenset({200, 201, 402})

_AUTHORISATIONS_PATH = "/authorisations"

_logger = structlog.get_logger(__name__)


class HttpPaymentGateway:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        breaker: CircuitBreaker,
        attempts: int,
        wait_initial_seconds: float,
        wait_max_seconds: float,
    ) -> None:
        self._client = client
        self._breaker = breaker
        # Built once. A RetryingCaller rather than the @stamina.retry
        # decorator because the numbers come from settings at runtime, and
        # a decorator would have to close over them at import time.
        self._retrying = stamina.AsyncRetryingCaller(
            attempts=attempts,
            wait_initial=wait_initial_seconds,
            wait_max=wait_max_seconds,
        )

    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        try:
            response = await self._breaker.call(
                lambda: self._retrying(is_retryable, self._send, order_id, total)
            )
        except CircuitOpenError as exc:
            # Not reaching the gateway at all still means "no answer" to
            # the caller, so it becomes the same error — but it is logged
            # distinctly, because "we refused to try" and "it did not
            # answer" need different responses from an operator.
            _logger.warning("payment.circuit_open", order_id=str(order_id))
            raise PaymentUnavailableError("payment provider circuit is open") from exc
        except (httpx.HTTPError, httpx.InvalidURL) as exc:
            _logger.warning(
                "payment.unreachable",
                order_id=str(order_id),
                error_type=type(exc).__name__,
            )
            raise PaymentUnavailableError(
                f"payment provider did not answer: {type(exc).__name__}"
            ) from exc

        if response.status_code == httpx.codes.PAYMENT_REQUIRED:
            reason = response.json().get("reason", "unknown")
            raise PaymentDeclinedError(order_id, reason)

        return Authorisation(id=AuthorisationId(response.json()["id"]))

    async def _send(self, order_id: OrderId, total: Money) -> httpx.Response:
        response = await self._client.post(
            _AUTHORISATIONS_PATH,
            json={
                "order_id": str(order_id),
                # Text, never a JSON number. 42.00 as a double can come
                # back as 42.000000000000004, and a payment amount is the
                # last place to accept that — the same reason MoneyOut
                # renders amounts as strings.
                "amount": str(total.amount),
                "currency": total.currency,
            },
            headers={
                # The order id is generated once, before the first
                # attempt, so every retry of this call carries the same
                # key. A gateway that honours it will not authorise twice.
                # We still do not retry read timeouts (see is_retryable):
                # this makes the connect-phase retries safe even against a
                # gateway that only sometimes honours the key.
                "Idempotency-Key": str(order_id)
            },
        )
        if response.status_code in _ANSWER_STATUSES:
            return response
        raise httpx.HTTPStatusError(
            f"payment gateway returned {response.status_code}",
            request=response.request,
            response=response,
        )
```

- [ ] **Step 4: Write the in-memory gateway**

`infrastructure/memory/payment_gateway.py`, beside the existing in-memory repository:

```python
"""A payment gateway that authorises everything.

The counterpart to InMemoryOrderRepository, and there for the same
reason: with no APP_PAYMENT__BASE_URL set, `just dev` starts a service
that works end to end with no upstream anywhere. It is also what the api
tests use, which keeps them free of HTTP mocking entirely.
"""

from __future__ import annotations

from uuid import uuid4

from reference_service.domain.order import Money, OrderId
from reference_service.domain.payments import Authorisation, AuthorisationId


class InMemoryPaymentGateway:
    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        return Authorisation(id=AuthorisationId(f"auth_{uuid4().hex}"))
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_payment_gateway.py -v`
Expected: PASS, seven tests. The counts asserted in them are the ones measured in Verified Fact 18; if any differs, the nesting is wrong — check that the breaker is the outer layer.

- [ ] **Step 6: Commit**

```bash
git add -A examples/reference-service
git commit -m "feat(reference-service): add the http payment gateway adapter"
```

---

## Task 11: The stub upstream and the cassettes

**Files:**
- Create: `examples/reference-service/ops/payment-stub/mappings/authorise.json`
- Create: `examples/reference-service/ops/payment-stub/mappings/decline.json`
- Create: `examples/reference-service/tests/recorded/__init__.py`, `conftest.py`, `test_payment_gateway_recorded.py`
- Create: `examples/reference-service/tests/cassettes/` (populated by recording)
- Modify: `examples/reference-service/compose.yaml`, `justfile`

**Interfaces:**
- Consumes: `HttpPaymentGateway`, `build_http_client`, `CircuitBreaker`.
- Produces: committed cassettes; `just test-record`.

**Read this before starting.** Cassettes exist to keep tests fast and offline, and to notice when a real upstream changes underneath you. The stub delivers the first and **cannot** deliver the second: it is version-controlled, so it never changes unless someone changes it. That is a genuine limitation of demonstrating this pattern in a reference service with no payment provider, and Task 15 says so in the documentation rather than implying a guarantee that is not there. What the cassettes do prove here is real: the adapter parses the wire format correctly, and no test reaches the network.

- [ ] **Step 1: Write the stub's mappings**

WireMock, because the stub is then two declarative JSON files rather than a second application to build and maintain. Verified against `wiremock/wiremock:3.13.2`.

`ops/payment-stub/mappings/authorise.json`:

```json
{
  "priority": 2,
  "request": {
    "method": "POST",
    "urlPath": "/authorisations",
    "bodyPatterns": [{ "matchesJsonPath": "$.order_id" }]
  },
  "response": {
    "status": 201,
    "headers": { "Content-Type": "application/json" },
    "jsonBody": { "id": "auth_stub_0001", "status": "authorised" }
  }
}
```

`ops/payment-stub/mappings/decline.json` — a declined amount, so the decline path can be recorded too. `priority: 1` wins over the catch-all above:

```json
{
  "priority": 1,
  "request": {
    "method": "POST",
    "urlPath": "/authorisations",
    "bodyPatterns": [{ "matchesJsonPath": "$.[?(@.amount == '999.99')]" }]
  },
  "response": {
    "status": 402,
    "headers": { "Content-Type": "application/json" },
    "jsonBody": { "reason": "insufficient_funds" }
  }
}
```

- [ ] **Step 2: Add the stub to compose**

```yaml
  payment-stub:
    image: wiremock/wiremock:3.13.2
    ports:
      - "9099:8080"
    volumes:
      - ./ops/payment-stub/mappings:/home/wiremock/mappings:ro
    healthcheck:
      test: ["CMD", "curl", "-fsS", "http://localhost:8080/__admin/health"]
      interval: 5s
      timeout: 3s
      retries: 5
```

and point the service at it, beside the other `APP_` variables in the `app` service's environment:

```yaml
      APP_PAYMENT__BASE_URL: http://payment-stub:8080
```

- [ ] **Step 3: Write the recorded tests**

`tests/recorded/conftest.py`:

```python
"""Cassette settings for every recorded test.

These tests run in the DEFAULT selection on purpose: replaying a cassette
needs no Docker and no network, so they are as fast and as portable as a
unit test. Only re-recording needs the stub, and that is `just test-record`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

PAYMENT_STUB_URL = "http://localhost:9099"


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    """Put recordings under tests/cassettes/, as spec 8.1 lays out, rather
    than beside the test module where pytest-recording puts them."""
    module = Path(request.node.path).stem
    return str(Path(__file__).resolve().parents[1] / "cassettes" / module)


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    return {
        # Credentials must never land in a committed file. The list is
        # explicit rather than clever: a header not named here IS recorded,
        # so adding an authenticated upstream means adding its header here.
        "filter_headers": [
            "authorization",
            "cookie",
            "set-cookie",
            "idempotency-key",
        ],
        # Match on the body too. Without it, the authorised and declined
        # recordings — same method, same URL — are indistinguishable and
        # the first one always answers.
        "match_on": ["method", "scheme", "host", "port", "path", "query", "body"],
    }
```

`tests/recorded/test_payment_gateway_recorded.py`:

```python
"""The adapter against recorded responses from the stub upstream.

`record_mode` is `none` by default in pytest-recording, so a request with
no matching cassette FAILS rather than quietly reaching the network.
Verified: it raises vcr.errors.CannotOverwriteExistingCassetteException.
"""

from __future__ import annotations

from decimal import Decimal
from uuid import UUID

import pytest

from reference_service.domain.errors import PaymentDeclinedError
from reference_service.domain.order import Money, OrderId
from reference_service.infrastructure.http.breaker import CircuitBreaker
from reference_service.infrastructure.http.client import build_http_client
from reference_service.infrastructure.http.payment_gateway import HttpPaymentGateway
from reference_service.settings import HttpClientSettings
from tests.recorded.conftest import PAYMENT_STUB_URL

# Fixed, not random: the cassette is matched on the request body, and the
# order id is in it. A uuid4() here would match nothing on replay.
ORDER_ID = OrderId(UUID("3fa85f64-5717-4562-b3fc-2c963f66afa6"))


def build_gateway() -> tuple[HttpPaymentGateway, object]:
    client = build_http_client(HttpClientSettings(), base_url=PAYMENT_STUB_URL)
    gateway = HttpPaymentGateway(
        client,
        breaker=CircuitBreaker(failure_threshold=5, reset_after_seconds=30.0),
        attempts=3,
        wait_initial_seconds=0.1,
        wait_max_seconds=1.0,
    )
    return gateway, client


@pytest.mark.vcr
async def test_an_authorisation_is_parsed_from_the_real_wire_format() -> None:
    gateway, client = build_gateway()
    try:
        authorisation = await gateway.authorise(
            order_id=ORDER_ID,
            total=Money(amount=Decimal("42.00"), currency="EUR"),
        )
    finally:
        await client.aclose()  # type: ignore[attr-defined]

    assert authorisation.id == "auth_stub_0001"


@pytest.mark.vcr
async def test_a_declined_payment_is_parsed_from_the_real_wire_format() -> None:
    gateway, client = build_gateway()
    try:
        with pytest.raises(PaymentDeclinedError, match="insufficient_funds"):
            await gateway.authorise(
                order_id=ORDER_ID,
                total=Money(amount=Decimal("999.99"), currency="EUR"),
            )
    finally:
        await client.aclose()  # type: ignore[attr-defined]
```

- [ ] **Step 4: Confirm the tests fail with no cassette**

Run: `uv run pytest tests/recorded -v`
Expected: FAIL with `CannotOverwriteExistingCassetteException`. This is the safety property, seen working: with no recording, the test refuses rather than reaching out.

- [ ] **Step 5: Add the recording recipe and record**

```just
# Re-record the outbound cassettes against the local payment stub.
# Commit the result, and READ it first: a cassette is a committed copy of
# somebody else's response, so anything secret in it becomes public with
# the repository. vcr_config's filter_headers strips the credential
# headers we know about; a new upstream means a new entry there.
test-record:
    docker compose up -d payment-stub
    uv run pytest tests/recorded --record-mode=once
    docker compose stop payment-stub
```

Run: `just test-record`
Expected: PASS, and two YAML files appear under `tests/cassettes/test_payment_gateway_recorded/`.

- [ ] **Step 6: Read the cassettes before committing them**

```bash
grep -ri "authorization\|api.key\|idempotency" examples/reference-service/tests/cassettes/ || echo "no credential headers recorded"
```

Expected: `no credential headers recorded`.

- [ ] **Step 7: Replay offline**

```bash
docker compose down
uv run pytest tests/recorded -v
```

Expected: PASS with nothing running. That is the property worth having.

- [ ] **Step 8: Commit**

```bash
git add -A examples/reference-service
git commit -m "test(reference-service): record the payment gateway against a stub upstream"
```

---

## Task 12: Authorise before saving

The wiring. Everything before this task is inert; this is where the order flow changes.

**Files:**
- Create: `examples/reference-service/migrations/000003_add_order_authorisation.up.sql` / `.down.sql`
- Modify: `domain/order.py`, `services/order.py`, `container.py`, `api/errors.py`, `api/v1/router.py`, `infrastructure/db/models.py`, `infrastructure/db/mappers.py`
- Test: `tests/unit/test_order_service.py`, `tests/api/test_orders.py`, `tests/fakes.py`

**Interfaces:**
- Consumes: everything from Tasks 7 to 11.
- Produces: `PlaceOrder(orders, payments)`; `Order.authorisation_id: AuthorisationId | None`.

**One thing this task deliberately does not solve.** Between a successful authorisation and a successful `orders.save`, the process can die. The money is authorised and no order exists. Fixing that properly needs either an outbox or a reconciliation job, both of which are their own design round — message queues are excluded from the whole project (spec section 2). The window is narrow and the failure is visible (an authorisation with no order), so M3 records it in the runbook rather than pretending it is closed. Do not add a `try/except` that "cleans up" by voiding the authorisation: that call can fail too, and now there are two windows instead of one.

- [ ] **Step 1: Write the failing tests**

In `tests/fakes.py`, add the two fakes the service tests need:

```python
class FakePaymentGateway:
    """Authorises everything, and remembers what it was asked."""

    def __init__(self) -> None:
        self.calls: list[tuple[OrderId, Money]] = []

    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        self.calls.append((order_id, total))
        return Authorisation(id=AuthorisationId("auth_fake_0001"))


class DecliningPaymentGateway:
    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        raise PaymentDeclinedError(order_id, "insufficient_funds")


class UnavailablePaymentGateway:
    async def authorise(self, *, order_id: OrderId, total: Money) -> Authorisation:
        raise PaymentUnavailableError("payment provider did not answer")
```

In `tests/unit/test_order_service.py`:

```python
async def test_an_order_is_authorised_before_it_is_saved() -> None:
    """Order matters. Saving first would persist orders nobody paid for
    every time the gateway declines."""
    orders = FakeOrderRepository()
    payments = FakePaymentGateway()

    order = await PlaceOrder(orders, payments)(a_command())

    assert payments.calls, "the gateway was never asked"
    _, total = payments.calls[0]
    assert total == order.total, "the authorised amount must be the order total"
    assert order.authorisation_id == "auth_fake_0001"
    assert orders.saved == [order]


async def test_a_declined_payment_saves_nothing() -> None:
    orders = FakeOrderRepository()

    with pytest.raises(PaymentDeclinedError):
        await PlaceOrder(orders, DecliningPaymentGateway())(a_command())

    assert orders.saved == []


async def test_an_unavailable_gateway_saves_nothing() -> None:
    orders = FakeOrderRepository()

    with pytest.raises(PaymentUnavailableError):
        await PlaceOrder(orders, UnavailablePaymentGateway())(a_command())

    assert orders.saved == []
```

In `tests/api/test_orders.py`. The two fixtures use `app.dependency_overrides`, which is the mechanism `api/deps.py`'s own docstring points at — cleaner than reaching into `app.state.container`, and it needs no knowledge of how the container was built:

```python
@pytest.fixture
def client_with_declining_gateway(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_payments] = DecliningPaymentGateway
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def client_with_unavailable_gateway(settings: Settings) -> Iterator[TestClient]:
    app = create_app(settings)
    app.dependency_overrides[get_payments] = UnavailablePaymentGateway
    with TestClient(app) as test_client:
        yield test_client


def test_a_declined_payment_is_a_402_problem_details(
    client_with_declining_gateway: TestClient,
) -> None:
    response = client_with_declining_gateway.post("/api/v1/orders", json=a_payload())

    assert response.status_code == 402
    assert response.headers["content-type"] == "application/problem+json"
    problem = response.json()
    assert problem["type"].endswith("/payment_declined")
    # The provider's reason reaches the client: it is the one thing that
    # tells them whether retrying could ever work.
    assert "insufficient_funds" in problem["detail"]


def test_an_unavailable_gateway_is_a_503_with_retry_after(
    client_with_unavailable_gateway: TestClient,
) -> None:
    response = client_with_unavailable_gateway.post("/api/v1/orders", json=a_payload())

    assert response.status_code == 503
    assert response.headers["content-type"] == "application/problem+json"
    # A 503 without Retry-After tells a client nothing about when to come
    # back, so every client invents its own answer and they all pick "now".
    assert response.headers["retry-after"] == "30"
    # And it must NOT leak which provider, at what URL, refused us.
    assert "http" not in response.json().get("detail", "").lower()
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/unit/test_order_service.py tests/api/test_orders.py -v`
Expected: failures — `PlaceOrder` takes one argument, `Order` has no `authorisation_id`.

- [ ] **Step 3: Add the field to the domain**

In `domain/order.py`, on `Order`:

```python
    # Set once the payment provider has authorised the total, and never
    # after. `None` is not "unpaid": it is an order placed while no
    # payment provider was configured at all, which is the in-memory
    # gateway's case and the default `just dev` experience.
    authorisation_id: AuthorisationId | None = None
```

`AuthorisationId` is already declared in this module (Task 9, Step 3), so no new import is needed — which is exactly why it was put there rather than in `payments.py`.

- [ ] **Step 4: Write the migration**

`migrations/000003_add_order_authorisation.up.sql`:

```sql
-- Nullable with no default and no backfill. Rows written before this
-- migration were placed with no payment provider configured, and
-- inventing an authorisation reference for them would be a lie recorded
-- in the database forever. NULL says exactly what is true: unknown.
ALTER TABLE orders
ADD COLUMN authorisation_id TEXT;
```

`.down.sql`:

```sql
ALTER TABLE orders
DROP COLUMN authorisation_id;
```

Create the pair with `just migrate-new add_order_authorisation` so the numbering is sequential, then fill both files in.

- [ ] **Step 5: Carry it through the persistence layer**

Add `authorisation_id: Mapped[str | None] = mapped_column(Text, nullable=True)` to the `orders` model, and map it in both directions in `infrastructure/db/mappers.py`.

- [ ] **Step 6: Change `PlaceOrder`**

```python
class PlaceOrder:
    def __init__(self, orders: OrderRepository, payments: PaymentGateway) -> None:
        self._orders = orders
        self._payments = payments

    async def __call__(self, command: PlaceOrderCommand) -> Order:
        # ... existing assembly of `lines` and the total, unchanged ...

        # Authorise BEFORE saving. The other order — save, then authorise —
        # persists an order for every declined card and leaves someone to
        # clean them up later.
        #
        # Neither error is caught here. PaymentDeclinedError is a
        # DomainError and api/errors.py turns it into a 402;
        # PaymentUnavailableError has its own handler and becomes a 503.
        # Wrapping either in ServiceDefectError would relabel a working
        # gateway's "no" as a bug in this service.
        authorisation = await self._payments.authorise(
            order_id=order_id, total=total
        )

        order = Order(
            id=order_id,
            customer_id=CustomerId(command.customer_id),
            lines=lines,
            total=total,
            authorisation_id=authorisation.id,
        )
        # The window: if this raises, the payment is authorised and no
        # order exists. Deliberately not "cleaned up" here — see the note
        # at the head of this task.
        await self._orders.save(order)
        return order
```

Note that `order_id` must now be generated *before* the authorisation call, so the same id can be the idempotency key. Hoist `order_id = OrderId(uuid4())` above the `try` that builds the lines.

- [ ] **Step 7: Hand the gateway to the use case**

`PlaceOrder` now takes two arguments, and `api/deps.py` is what constructs it. Add the dependency beside the existing one:

```python
def get_payments(container: ContainerDep) -> PaymentGateway:
    return container.payments


PaymentsDep = Annotated[PaymentGateway, Depends(get_payments)]


def get_place_order(orders: OrdersDep, payments: PaymentsDep) -> PlaceOrder:
    return PlaceOrder(orders, payments)
```

`get_payments` is also the override point the two new test fixtures use, which is why it is a separate dependency rather than something `get_place_order` reads off the container itself.

- [ ] **Step 8: Map the two errors to statuses**

In `api/errors.py`, add `PaymentDeclinedError: status.HTTP_402_PAYMENT_REQUIRED` to `_STATUS_BY_ERROR`, and register a handler for the infrastructure error:

```python
    @app.exception_handler(PaymentUnavailableError)
    async def _payment_unavailable(
        request: Request, exc: PaymentUnavailableError
    ) -> JSONResponse:
        """503, not 500. The caller did nothing wrong and the same request
        may well succeed later — which is exactly what 503 means and 500
        does not.

        `detail` is a fixed string, never `str(exc)`: the exception
        carries the provider's name and sometimes its URL, and this
        response is public. The full exception goes to the log instead,
        the same division ReadinessRegistry already makes.
        """
        _logger.warning("request.payment_unavailable", exc_info=exc)
        return _problem_response(
            ProblemDetail(
                type=f"{PROBLEM_TYPE_BASE}/payment_unavailable",
                title="Payment provider unavailable",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail="The payment provider could not be reached. Try again.",
                instance=request.url.path,
            ),
            headers={"Retry-After": str(RETRY_AFTER_SECONDS)},
        )
```

with `RETRY_AFTER_SECONDS = 30` declared at module level beside the other constants, and a comment noting it matches `breaker_reset_after_seconds`'s default — telling a client to return before the circuit could possibly have closed just wastes both sides' time.

Document both on the route in `api/v1/router.py`:

```python
    responses={
        status.HTTP_402_PAYMENT_REQUIRED: problem_response("Payment declined"),
        status.HTTP_503_SERVICE_UNAVAILABLE: problem_response(
            "Payment provider unavailable"
        ),
    },
```

- [ ] **Step 9: Wire the container**

In `container.py`, add `payments: PaymentGateway` to `Container` and `http_client: httpx.AsyncClient | None = None`, then in `build_container`:

```python
    if settings.payment is None:
        payments: PaymentGateway = InMemoryPaymentGateway()
        http_client = None
    else:
        http_client = build_http_client(
            settings.payment.http,
            base_url=str(settings.payment.base_url),
            headers=(
                {"Authorization": f"Bearer {settings.payment.api_key.get_secret_value()}"}
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
```

and close it in `close_container`, beside the engine disposal:

```python
    if container.http_client is not None:
        await container.http_client.aclose()
```

Do **not** register a readiness check that calls the payment provider. `/readyz` removing this pod from load balancing because someone else's API is slow turns their outage into ours, and the breaker already handles the case properly.

- [ ] **Step 10: Run everything**

Run: `just check`
Expected: PASS. Then `just test-contract` — the contract changed (two new documented responses), so regenerate: `just openapi`.

Run: `just gates` (needs Docker) — the five schema gates must accept migration 000003 unchanged, including the manifest. Run `just migrate-manifest` after creating the migration pair, as the recipe's comment instructs.

- [ ] **Step 11: Commit**

```bash
git add -A examples/reference-service
git commit -m "feat(reference-service): authorise payment before an order is accepted"
```

---

## Task 13: Outbound tracing

Closes the first row of the M2 plan's "deliberately does not include" table: there was nothing to instrument then, because the client did not exist.

**Files:**
- Modify: `examples/reference-service/src/reference_service/observability/otel.py`
- Modify: `examples/reference-service/src/reference_service/main.py`
- Test: `examples/reference-service/tests/unit/test_otel.py`

**Interfaces:**
- Consumes: `OtelRuntime`, `_opt_in_to_stable_semconv` (M2); the client from Task 8.
- Produces: `instrument_http_client(client: httpx.AsyncClient, runtime: OtelRuntime) -> None`.

- [ ] **Step 1: Write the failing test**

```python
async def test_an_instrumented_client_produces_a_client_span() -> None:
    runtime, exporter = a_runtime_with_an_in_memory_exporter()
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(201, json={})),
        base_url="http://gateway",
    )
    instrument_http_client(client, runtime)

    try:
        await client.post("/authorisations", json={})
    finally:
        await client.aclose()

    runtime.tracer_provider.force_flush()
    spans = exporter.get_finished_spans()
    assert [span.kind for span in spans] == [SpanKind.CLIENT]
    assert spans[0].attributes["http.request.method"] == "POST"
    # The STABLE convention, matching every other span this service emits
    # — see the M2 plan's Verified Fact 2. `http.method` here would mean
    # outbound spans could not be queried alongside inbound ones.
    assert "http.method" not in spans[0].attributes


def test_no_client_is_instrumented_when_telemetry_is_off() -> None:
    """With APP_OTEL__ENABLED false, configure_otel returns None and
    main.py must not reach for instrumentation at all — the M2 rule that
    the disabled path constructs no SDK object."""
    app = create_app(Settings(otel=OtelSettings(enabled=False)))

    assert app.state.otel is None
```

- [ ] **Step 2: Run them and watch them fail**

Run: `uv run pytest tests/unit/test_otel.py -k http_client -v`
Expected: FAIL — `cannot import name 'instrument_http_client'`.

- [ ] **Step 3: Write the helper**

In `observability/otel.py`, beside `instrument_database`:

```python
def instrument_http_client(client: httpx.AsyncClient, runtime: OtelRuntime) -> None:
    """Add a CLIENT span per outbound request to one client.

    `instrument_client`, not the global `instrument()`: this attaches to
    the single instance the composition root built, so a service running
    with APP_OTEL__ENABLED false has nothing patched anywhere. The global
    form would monkey-patch httpx itself, which is both wider than we
    need and impossible to undo cleanly in tests.

    `_opt_in_to_stable_semconv()` first, for the reason spelled out in the
    M2 plan: the opt-in is read on the FIRST instrument*() call in a
    process and cached forever, so every instrumentor must be preceded by
    it or the first one to run decides for all of them.
    """
    _opt_in_to_stable_semconv()
    HTTPXClientInstrumentor.instrument_client(
        client, tracer_provider=runtime.tracer_provider
    )
```

- [ ] **Step 4: Call it from the lifespan**

In `main.py`, inside the `if otel_runtime is not None:` block in `lifespan`, beside `instrument_database`:

```python
            if container.http_client is not None:
                # Only when a real payment provider is configured. The
                # in-memory gateway makes no HTTP request, so there is no
                # client and nothing to instrument.
                instrument_http_client(container.http_client, otel_runtime)
```

- [ ] **Step 5: Run the tests**

Run: `uv run pytest tests/unit/test_otel.py -v && just test`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add -A examples/reference-service
git commit -m "feat(observability): trace outbound payment requests"
```

---

## Task 14: Mutation testing

Read Verified Facts 11 and 12 before starting. Three of mutmut's behaviours will otherwise cost an hour each.

**Files:**
- Modify: `examples/reference-service/pyproject.toml`, `.gitignore`, `justfile`

**Interfaces:**
- Consumes: the whole test suite.
- Produces: `just mutants`, `just mutants-changed`.

- [ ] **Step 1: Configure mutmut**

```toml
[tool.mutmut]
# The whole package, then narrowed below. Pointing source_paths straight
# at domain/ and services/ instead would leave the package unimportable
# inside mutmut's copy, because api/ and main.py would be missing.
source_paths = ["src/reference_service"]

# Mutate business logic only. Mutating adapters produces a long tail of
# survivors about error paths nobody asserts on, and a signal nobody
# trusts is worse than no signal (spec 8.1).
only_mutate = [
    "src/reference_service/domain/*",
    "src/reference_service/services/*",
]

# mutmut runs the suite inside a `mutants/` COPY of the project, and that
# copy contains source_paths, tests/ and a fixed list of lock files —
# nothing else. Without these two, M2's tests/unit/test_dashboards.py
# fails with "mutants/ops/grafana/dashboards not found" and M1's
# test_migration_files.py cannot find the files it hashes.
also_copy = ["ops", "migrations"]

# Behaviour tests only, and this list is the important line in this file.
#
# It excludes the file-shape gates ON PURPOSE, and not merely because they
# are slow: mutmut injects `from mutmut import ...` into every module it
# mutates, so M0's tests/unit/test_layer_purity.py — which asserts that
# domain/ imports nothing but pydantic and the standard library — FAILS
# inside the copy, reporting mutmut itself as a third-party import. The
# alternative, adding mutmut to that gate's allow-list, would weaken a
# real M0 gate in ordinary runs to satisfy a tool. A gate that checks the
# SHAPE of the tree can never kill a mutant in the first place, so
# excluding it costs nothing.
pytest_add_cli_args_test_selection = [
    "tests/unit/test_order.py",
    "tests/unit/test_order_service.py",
    "tests/unit/test_domain_errors.py",
    "tests/unit/test_memory_repository.py",
    "tests/api/test_orders.py",
]
```

Add `mutants/` to `.gitignore`.

- [ ] **Step 2: Run it and record the baseline**

Run: `cd examples/reference-service && uv run mutmut run`
Expected: a summary of the form `N/N  🎉 killed  🙁 survived`. Measured while writing this plan, before M3's own code was added: **58 mutants, 51 killed, 7 survived, 4.2 seconds**.

Run: `uv run mutmut results` and `uv run mutmut show <id>` on each survivor.

- [ ] **Step 3: Judge each survivor, and write down the judgement**

Every survivor in the baseline was an error-*message* mutation:

```diff
-        raise ValueError("cannot total an empty list of lines")
+        raise ValueError(None)
```

Do not chase these. A test that pins an exception's prose breaks whenever someone rewords it, which is the failure mode M0's structlog guidance already warns about — assert on the event, not the wording. Kill a survivor when it reveals a *behaviour* nobody checks; leave it when the only way to kill it is to assert on text.

Survivors from M3's own code are a different matter. If a mutation to `PlaceOrder`'s authorise-then-save ordering survives, that is a real gap: write the test.

- [ ] **Step 4: Record the threshold**

Spec 8.1 asks for a tracked survival threshold. Add it to `pyproject.toml` beside the rest of the mutmut configuration, as a comment plus the number the recipe reads:

```toml
# The floor, as a percentage of mutants killed. 85 rather than the 87.9
# measured at the baseline: the seven survivors there are all
# error-MESSAGE mutations (`raise ValueError("...")` -> `raise
# ValueError(None)`), and pinning the threshold to the exact current
# number would mean the next such survivor fails the build and pressures
# whoever hits it into asserting on prose. Raise this when the score
# improves for a real reason; never lower it to make a build pass.
mutation_threshold_percent = 85
```

`[tool.mutmut]` ignores keys it does not know, so this is read by the gate below and by nothing else.

- [ ] **Step 5: Add the recipes**

```just
# Mutation testing over domain/ and services/. Slow relative to `just
# test`, so it is NOT part of `just check`: run it when you have changed
# business logic, and read the survivors rather than the percentage.
#
# What it measures that coverage does not: coverage says a line RAN, this
# says a test would have NOTICED if the line were wrong.
mutants:
    uv run mutmut run
    uv run mutmut results

# The same, restricted to files changed against main — what a pull
# request actually needs.
mutants-changed:
    #!/usr/bin/env bash
    set -euo pipefail
    changed=$(git diff --name-only origin/main...HEAD \
        -- 'src/reference_service/domain/*' 'src/reference_service/services/*')
    if [ -z "$changed" ]; then
        echo "No domain or services files changed; nothing to mutate."
        exit 0
    fi
    echo "Mutating: $changed"
    uv run mutmut run $changed
    uv run mutmut results
```

And the gate itself, which reads mutmut's own JSON summary rather than scraping its printed output (Verified Fact 19):

```just
# Fail if the mutation score falls below the recorded floor. Separate
# from `mutants` so a developer can look at survivors without the run
# failing on them.
mutants-gate: mutants
    #!/usr/bin/env bash
    set -euo pipefail
    uv run mutmut export-cicd-stats
    uv run python -c "
import json, tomllib
from pathlib import Path
stats = json.loads(Path('mutants/mutmut-cicd-stats.json').read_text())
floor = tomllib.loads(Path('pyproject.toml').read_text())['tool']['mutmut'][
    'mutation_threshold_percent'
]
score = 100 * stats['killed'] / stats['total'] if stats['total'] else 100
print(f\"mutation score {score:.1f}% ({stats['killed']}/{stats['total']} killed), floor {floor}%\")
raise SystemExit(0 if score >= floor else 1)
"
```

- [ ] **Step 6: Verify all three recipes**

Run: `just mutants`
Expected: completes and prints results.

Run: `just mutants-gate`
Expected: `mutation score 87.9% (51/58 killed), floor 85%` and exit 0. Then temporarily set the floor to 99, re-run, and confirm it exits 1 — a threshold nobody has seen fail is not a threshold.

Run: `just mutants-changed`
Expected: either a mutation run over the changed files, or the "nothing to mutate" message. Both are correct outcomes; check you can produce each.

- [ ] **Step 7: Commit**

```bash
git add -A examples/reference-service
git commit -m "test(reference-service): configure mutation testing over domain and services"
```

---

## Task 15: Documentation and the roadmap

**Files:**
- Modify: `docs/roadmap.md`
- Modify: `examples/reference-service/README.md`
- Create: `docs/guides/outbound-http.md` (or extend the nearest existing page — check `mkdocs.yml` first)
- Modify: `mkdocs.yml` if a page is added

**Interfaces:**
- Consumes: everything.
- Produces: a site that describes what is now true.

- [ ] **Step 1: Update the roadmap**

Change M3's **State** to **Done** and the intro line to "M0, M1, M2 and M3 are done." Leave the "What exists at the end" column as it is if it still describes reality; if the milestone landed differently from the plan, the *table* is what changes, not the memory of what was planned.

- [ ] **Step 2: Write the contract section**

The three gates, what each catches, and the one command per gate. Include the workflow a contributor actually follows, because this is the part people get wrong:

1. Change a route or a schema.
2. `just openapi`.
3. **Read the diff.** It is your API change, stated completely.
4. `just contract-gates`.
5. If it reports a breaking change, either undo it or bump the version.

- [ ] **Step 3: Write the outbound HTTP section**

Cover the timeout policy, the retry rule and *why it is narrow*, the breaker's three states, and the idempotency key. The retry rule is the part worth writing carefully: readers will assume "retry on failure" and the whole point is that this code does not.

- [ ] **Step 4: Be honest about the cassettes**

State plainly that the recorded upstream is a local stub, so the cassettes prove the adapter parses the wire format and keep the tests offline — and that they cannot detect a real provider changing, because nothing here changes on its own. Point at the weekly re-record job as M5 work. A reader who believes cassettes are guarding them against upstream drift, when they are not, is worse off than one who was told the truth.

- [ ] **Step 5: Record the authorise-then-save window**

One short section: what the gap is, what it looks like when it happens (an authorisation with no order), and why M3 does not close it. Link it from the runbook if one exists by then; otherwise it lives here until M5 builds the runbook.

- [ ] **Step 6: Check the docs build**

Run: `just docs-build` from the repository root.
Expected: PASS with `--strict` — a dead internal reference is a failure here, not a warning.

- [ ] **Step 7: Commit**

```bash
git add -A
git commit -m "docs: describe the contract gates, the outbound client and m3's limits"
```

---

## Finishing

- [ ] **Run every gate, in the order CI will run them at M5**

```bash
cd examples/reference-service
just check          # lint, typecheck, imports, unit + api tests, pre-commit
just test-contract  # schemathesis
just contract-gates # schemathesis + oasdiff + the version cross-check
just test-integration
just gates          # the five schema gates
just o11y-gates     # promtool
just mutants-gate   # mutation score against the recorded floor
```

Every one must pass. Report the actual output; a plan that ends with "should pass" has not been executed.

- [ ] **Open the pull request**

Create the GitHub issue for M3 first if one does not exist, and link the pull request to it. Title it as a Conventional Commit — it becomes the squash-merge commit message on `main`:

```
feat(reference-service): govern the api contract and add the outbound payment client
```

The description should lead with the four defects the conformance gate found in existing code, because that is the most useful thing a reviewer can know about this milestone:

1. Framework `HTTPException`s bypassed RFC 9457 (400, 404, 405).
2. The published `unit_amount` schema was more permissive than the model, in both branches.
3. Two individually valid line fields could produce a total that returned 500.
4. A hand-written fix to the 405 path dropped the `Allow` header, and the same gate caught it in the same run.
