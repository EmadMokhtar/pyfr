---
last_reviewed: 2026-09-11
covers:
  - src/{{ cookiecutter.package_name }}/observability/
---

# Logging

One JSON object per line, on standard output. Every record — the service's
own and every third-party library's — passes through the same processing
chain, so there is exactly one log format to parse.

Standard output is the source of truth. It survives a telemetry collector
outage, and it captures crashes and any failure that happens before other
telemetry has started. A platform log agent reads it and forwards it.

## Two renderings

`APP_ENVIRONMENT` decides the format.

`local` gives colourised, aligned, human-readable lines:

```
2026-09-01T14:00:52.697Z [info     ] Application startup complete. [uvicorn.error] service.name=reference-service service.version=0.1.0 deployment.environment=local
```

Anything else gives one JSON object per line:

```json
{"http.request.method":"POST","http.route":"/api/v1/orders","http.response.status_code":201,"duration_ms":2.787,"event":"http.access","correlation_id":"9f05f3abb60643b886eaa4b1f867a252","service.name":"reference-service","service.version":"0.1.0","deployment.environment":"production","logger":"reference_service.access","level":"info","timestamp":"2026-09-01T13:59:33.614725Z"}
```

## Fields on every record

| Field | Meaning |
| --- | --- |
| `event` | The event name. A stable identifier, not a sentence — `http.access`, not "Request finished in 3ms". |
| `timestamp` | ISO 8601, in UTC. |
| `level` | `debug`, `info`, `warning`, `error`, or `critical`. |
| `logger` | Which logger emitted the record. |
| `service.name` | From `APP_SERVICE_NAME`. Without it you cannot separate one service's records in a shared backend. |
| `service.version` | The package version. Tells you which release produced a line during a rollout. |
| `deployment.environment` | From `APP_ENVIRONMENT`. |
| `trace_id` | The active trace, as 32 hexadecimal digits. Present only on records emitted inside a span, which is why a startup line does not carry one. Links a log line to its trace in Tempo. |
| `span_id` | The active span, as 16 hexadecimal digits. Same condition. |
| `correlation_id` | Present on every record emitted during a request. |

The three `service.*` and `deployment.*` names follow OpenTelemetry's
semantic conventions — agreed standard names for telemetry fields, so a
dashboard written for one service works for another.

## Correlation identifiers

Every request gets one identifier. It is bound for the duration of the
request, so every log line that request produces carries it, including lines
from libraries that know nothing about it.

The middleware reads the `X-Request-ID` request header and uses that value if
present, or generates one if not. Either way the value is echoed in the
`X-Request-ID` response header.

That is what makes a support report actionable. Someone reports a failure and
quotes the header value; you filter the logs by `correlation_id` and see every
line that request produced, including the traceback.

Send your own to follow one logical operation across several services:

```bash
curl -H 'X-Request-ID: my-trace-42' http://localhost:8000/api/v1/orders/...
```

## The access log

One structured record per request, emitted by the service rather than by
uvicorn. uvicorn's own access log is plain text and is switched off
(`--no-access-log`).

```json
{
  "event": "http.access",
  "http.request.method": "POST",
  "http.route": "/api/v1/orders",
  "http.response.status_code": 201,
  "duration_ms": 2.787,
  "correlation_id": "9f05f3abb60643b886eaa4b1f867a252"
}
```

### `http.route`, not the raw path

The field records the route **template** — `/api/v1/orders/{order_id}` — not
the path that was requested — `/api/v1/orders/cac0acf8-...`.

The reason is **cardinality**: how many distinct values a field can take. The
raw path produces one distinct value per order id, without limit. That is the
usual way a log or metrics backend is overwhelmed, and it makes the field
useless for grouping — you cannot ask "how slow is fetching an order?" if
every request is its own unique path.

The template has one value per route. It groups, and it is bounded.

When nothing matches a route — usually a bot probing URLs that do not exist —
the field records the literal `<unmatched>` rather than the raw path, for the
same reason.

!!! note "One known limitation"

    If a router is ever mounted under a *parameterised* prefix, such as
    `/tenants/{tenant_id}`, that prefix is recorded as-is rather than as a
    template, so that segment is not bounded. Every prefix in the reference
    service today is a fixed string.

### Health endpoints are excluded

`/healthz`, `/readyz` and `/startupz` produce no access-log record. An
orchestrator probes them every few seconds forever; logging that would bury
real traffic in noise and cost money to store.

## Per-logger levels

Silencing a chatty library is configuration, not a code change:

```bash
APP_LOG__LEVELS='{"httpx": "warning"}'
```

The keys are logger names, which appear in the `logger` field of the records
you want to quieten.

## Redaction

A field is masked by name, at any depth of nested objects and lists, ignoring
case and treating `-` and `_` alike. The masked value becomes the literal
string `[REDACTED]`.

The redactor runs last in the shared processor chain (`_shared_processors` in
`observability/logging.py`), so it sees the fully assembled record —
including values middleware bound into context earlier in the request. That
same chain is also the `foreign_pre_chain` that formats standard-library
records, so a third-party library's log line is masked by the same rule.
The OTLP export leg masks a record's `extra=` attributes with the same rule,
through a filter on that handler. That beats redacting at each call site:
the one call site where someone forgets is the one that matters.

The default field names are `access_token`, `api_key`, `apikey`,
`authorization`, `card_number`, `cookie`, `cvv`, `passwd`, `password`,
`refresh_token`, `secret`, `secret_access_key`, `secret_key`, `set_cookie`,
and `token`. `APP_LOG__REDACT_FIELDS` **replaces** this list rather than
adding to it — see [Configuration](configuration.md#variables).

```python
log.info("user.login", user="ann", password="hunter2")
```

produces (other fields every record carries are omitted here for clarity):

```json
{"event": "user.login", "user": "ann", "password": "[REDACTED]"}
```

Matching is by key name only. A secret interpolated into the message string,
as in `log.info(f"token {token}")`, is not something a key-name rule can
see — nothing reads message text. `SecretStr` and the startup path's
`include_input=False` close the other two ways a secret could reach one of
our own records as a value. Put secrets in fields, never in the event string.

See [ADR 0013](../adr/0013-redaction-is-a-processor-in-the-shared-chain.md).

## Exceptions are one record

An exception becomes a single structured field containing the whole stack,
rather than thirty unrelated lines that a backend then shows out of order.
The record carries the correlation identifier, so a 500 response can be traced
directly to its traceback.

## Testing note: `caplog` does not work

Logging setup clears the root logger's handlers, which also removes the one
pytest's logging plugin installs. Any test that builds the application gets
nothing in `caplog`, even with `caplog.at_level(...)`.

Assert on captured standard output instead — `capsys.readouterr().out`, parsed
with `json.loads` one line at a time. Every logging test in the reference
service already does this; copy one of them.
