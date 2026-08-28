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
uv sync            # or: just install
just dev           # http://localhost:8000/docs
```

## Commands

| Command | What it does |
|---|---|
| `just install` | Sync dependencies from the lock file |
| `just dev` | Run with auto-reload on port 8000 |
| `just test` | Run the test suite |
| `just lint` | ruff check and format check |
| `just fmt` | Fix lint issues and format |
| `just typecheck` | mypy — strict on domain and application |
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
  application/     one use case per business operation
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

Invalid configuration stops the process at startup with exit code 78 and a
readable message, rather than causing a 500 response later.
