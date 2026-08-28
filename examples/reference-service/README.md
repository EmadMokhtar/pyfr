# Reference Service

The PyFr reference service: the walking skeleton every generated project
starts from. It runs, it is tested, and it has no database, cache or object
storage — those arrive in later milestones.

## Requirements

- [uv](https://docs.astral.sh/uv/) — the only Python tool you need
- Docker, for `just up`
- [just](https://github.com/casey/just) — the command runner

## Five-minute start

```bash
uv sync                    # or: just install
uv run pre-commit install  # one-time: wires up the lint and commit-msg hooks
just dev                   # http://localhost:8000/docs
```

## Commands

| Command | What it does |
|---|---|
| `just install` | Sync dependencies from the lock file |
| `just dev` | Run with auto-reload on port 8000 |
| `just test` | Run the test suite |
| `just lint` | ruff check and format check |
| `just fmt` | Fix lint issues and format |
| `just typecheck` | mypy — strict on domain and services |
| `just imports` | Verify the layer dependency rule |
| `just check` | All of the above; run this before pushing |
| `just up` / `just down` | Start / stop the container stack |

## Endpoints

| Path | Purpose |
|---|---|
| `GET /healthz` | Liveness. Never checks a dependency. |
| `GET /readyz` | Readiness. Checks dependencies with short timeouts. |
| `GET /startupz` | Whether startup has finished. |
| `POST /api/v1/orders` | Place an order. |
| `GET /api/v1/orders/{order_id}` | Fetch an order. |
| `GET /docs` | Interactive API documentation. |

## Layout

```
src/reference_service/
  domain/          entities and repository ports; imports only pydantic
  services/        application services; one file per aggregate
  infrastructure/  adapters; the only code that knows a storage technology
  api/             the only code that knows HTTP
```

The arrows point inward: `infrastructure` and `api` import `domain`, never
the reverse. `just imports` fails the build if that stops being true.

## Configuration

Every variable is prefixed `APP_`; nested settings use `__`. Copy
`.env.example` to `.env` to start.

| Variable | Default | Meaning |
|---|---|---|
| `APP_ENVIRONMENT` | `local` | `local` gives colourised console logs; anything else gives JSON |
| `APP_SERVICE_NAME` | `reference-service` | Used as the OpenAPI title and the `service.name` log field |
| `APP_HTTP_PORT` | `8000` | Port to serve on — read by `just dev` and the container's `CMD` |
| `APP_LOG__LEVEL` | `info` | Root log level |
| `APP_LOG__LEVELS` | `{}` | Per-logger overrides, as JSON |
| `APP_OTEL__ENABLED` | `false` | Reserved for M2's OpenTelemetry exporter |
| `APP_OTEL__LOGS_ENABLED` | `false` | Reserved for M2; would double log ingest if enabled alongside a platform log agent |
| `APP_OTEL__ENDPOINT` | unset | Reserved for M2; the OTLP collector endpoint the exporter would send to |

Invalid configuration stops the process at startup with exit code 78 and a
readable message, rather than causing a 500 response later.

## Graceful shutdown and the orchestrator's kill deadline

The container's `CMD` passes uvicorn `--timeout-graceful-shutdown 30`: on
SIGTERM, uvicorn stops accepting new connections but lets in-flight
requests finish for up to 30 seconds before it exits. That number is only
a promise if the orchestrator's own kill deadline is set comfortably
above it — otherwise requests still running when the deadline hits are
killed, not drained, no matter what uvicorn was told. `compose.yaml` sets
`stop_grace_period: 40s` for exactly this reason: Docker Compose's own
default is 10 seconds, well under uvicorn's 30. A Kubernetes deployment
has the identical mismatch and needs the identical fix —
`terminationGracePeriodSeconds` on the pod spec, set the same way, above
uvicorn's `--timeout-graceful-shutdown`. It is easy to miss because
Kubernetes' own default (30s) happens to equal uvicorn's deadline here
exactly, leaving no margin at all.

## Testing note: `caplog` does not work here

`configure_logging` calls `logging.getLogger().handlers.clear()`, which
also removes the handler pytest's own logging plugin installs. Any test
that calls `create_app` (directly, or via the `client` fixture) therefore
gets nothing in `caplog`, even with `caplog.at_level(...)`. Assert on
captured stdout instead — `capsys.readouterr().out`, parsed with
`json.loads` per line — as every test in `tests/api/` and
`tests/unit/test_logging.py` already does.
