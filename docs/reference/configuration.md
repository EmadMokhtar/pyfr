# Configuration

Configuration comes from environment variables. Every variable is prefixed
`APP_`, and nested settings use a double underscore: `APP_LOG__LEVEL` fills
`settings.log.level`. One flat environment therefore produces a structured
object.

For local work, copy the example file and edit it:

```bash
cp .env.example .env
```

`.env` is never committed. `.env.example` is the documented default.

## Variables

| Variable | Type | Default | Meaning |
| --- | --- | --- | --- |
| `APP_ENVIRONMENT` | `local` \| `staging` \| `production` | `local` | `local` prints colourised, human-readable logs. Anything else prints one JSON object per line. |
| `APP_SERVICE_NAME` | string | `reference-service` | The OpenAPI document's title, and the `service.name` field on every log record. |
| `APP_HTTP_PORT` | integer, 1–65535 | `8000` | The port to serve on. Read by `just dev`, by the container's start command, and by the image's health check. |
| `APP_LOG__LEVEL` | `debug` \| `info` \| `warning` \| `error` \| `critical` | `info` | The root log level. |
| `APP_LOG__LEVELS` | JSON object | `{}` | Per-logger overrides, as JSON. Silencing a chatty library is configuration, not a code change. |
| `APP_OTEL__ENABLED` | boolean | `false` | Reserved for M2's OpenTelemetry support. Does nothing yet. |
| `APP_OTEL__LOGS_ENABLED` | boolean | `false` | Reserved for M2. See the warning below. |
| `APP_OTEL__ENDPOINT` | string | unset | Reserved for M2. The collector address telemetry would be sent to. |

`APP_LOG__LEVELS` takes a JSON object, quoted so the shell does not split it:

```bash
APP_LOG__LEVELS='{"httpx": "warning", "uvicorn.error": "warning"}'
```

!!! danger "`APP_OTEL__LOGS_ENABLED` doubles your log bill"

    Standard output is the source of truth for logs. Most platforms already
    run an agent that reads a container's standard output and forwards it.
    Turning on log export as well sends every record twice — once through
    the agent, once over the network — doubling both ingest volume and cost.

    It is off by default and should stay off in production. It exists for
    local work, where trace-to-log correlation in Grafana is worth having and
    there is no agent.

## Bad configuration stops the process

Settings are built once at startup and validated then. A missing or malformed
value prints a readable message to standard error and exits with code **78**:

```
Invalid configuration:
1 validation error for Settings
http_port
  Input should be less than or equal to 65535 [type=less_than_equal, input_value=99999, ...]
```

78 is `EX_CONFIG` from `sysexits.h`, the conventional Unix exit code for a
configuration error. An orchestrator can tell "this was misconfigured" apart
from "this crashed".

The alternative — accepting a bad value and failing later — turns a typo into
a 500 response an hour after deployment, at which point nobody connects the
two. Failing at startup means a bad deployment never receives traffic.

This is why `APP_LOG__LEVEL` is a fixed set of five values rather than a
plain string. `APP_LOG__LEVEL=verbose` as a plain string would pass validation
and then raise `ValueError: Unknown level: 'VERBOSE'` deep inside logging
setup — a crash, in place of the readable exit-78 message every other bad
value produces.

## Settings are frozen, with one gap

`Settings` and its sub-models are frozen: assigning to a field after startup
raises rather than silently changing behaviour under a running server.

One gap remains, and it is documented rather than hidden. `APP_LOG__LEVELS`
holds an ordinary Python dictionary. Freezing refuses to *replace* the
dictionary, but the dictionary object itself is still mutable, so
`settings.log.levels["x"] = "debug"` succeeds. Nothing in the code does this.
It is recorded here because a claim that settings are simply "frozen" would
promise more than the code delivers.

## One more gap worth knowing

Unknown keys in a `.env` **file** are rejected. An unknown variable set
directly in the process environment — `APP_SOMETHING_UNKNOWN=1` — is silently
ignored.

The two sources are treated differently by the settings library, and there is
no option that closes the environment-variable half. So a typo in a deployment
manifest will not be caught: the variable is ignored and the default is used.
Prefer changing `.env.example` and keeping deployment variables reviewed.
