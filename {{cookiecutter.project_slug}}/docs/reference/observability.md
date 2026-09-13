---
last_reviewed: 2026-09-12
covers:
  - src/{{ cookiecutter.package_name }}/observability/
  - ops/
---

# Observability

The service emits OpenTelemetry traces and metrics, and structured logs that
link back to them. A local Grafana stack runs behind a compose profile so you
can see your own request end to end on a laptop.

## What ships, and what does not

The template ships **instrumentation, dashboards and rules**. It does not ship
a production observability platform, because teams already have one. The
service's only commitment is to emit OpenTelemetry data to whatever
`APP_OTEL__ENDPOINT` points at.

The local stack exists for two reasons: so a developer can see their own
traces without wiring anything up, and so the dashboards are verified as
actually working rather than assumed to.

## What is traced, and what is not

HTTP requests and outbound calls to the payment provider produce spans.
{%- if cookiecutter.database == "postgres" %}
So do SQL statements.
{%- endif %}
{%- if cookiecutter.cache == "redis" %}
So do **Redis commands**.
{%- endif %}
{%- if cookiecutter.object_storage == "s3" %}
`GET /orders/{id}/receipt`'s calls to object storage do **not** — say this
plainly, because a reader who assumes otherwise will go looking for an S3
span that does not exist.
{%- endif %}
{%- if cookiecutter.object_storage == "s3" %}

The gap is not an oversight. `opentelemetry-instrumentation-botocore` was
added, pointed at a real MinIO container, and measured: `ListBuckets`,
`CreateBucket`, `PutObject` and `GetObject` all succeeded and all produced
**zero spans**, even though the instrumentor reported itself installed.
`aioboto3` runs on `aiobotocore`, which replaces the parts of `botocore`'s
client machinery the instrumentor patches (`botocore.client.BaseClient.
_make_api_call`) with async equivalents the instrumentor's hooks never see —
`AioBaseClient` shadows the method being patched. Shipping that dependency
anyway would be worse than not shipping it: a trace search or a dashboard
built against it would read as "S3 calls are always fast" instead of "S3
calls are not observed", and the first of those is actively misleading. The
dependency was removed rather than left in place doing nothing.
{%- if cookiecutter.cache == "redis" %}
See
`instrument_redis` in `src/{{ cookiecutter.package_name }}/observability/otel.py` for the
full reasoning kept beside the code it explains.
{%- endif %}
{%- endif %}

## Turning it on

```bash
just o11y
```

That starts the database, the API and one `grafana/otel-lgtm` container
holding Grafana, Prometheus, Tempo, Loki and an OpenTelemetry collector. Open
<http://localhost:3000> — anonymous access is enabled, so there is no login —
and look in the **PyFr** folder.

Telemetry is **off by default**, and the default costs nothing: with
`APP_OTEL__ENABLED` false the process builds no providers, imports no
exporter, opens no socket and starts no background task.

## Readiness reports optional dependencies, and gates on none

`/readyz` carries two tiers: `checks`, which decides its status code, and
`dependencies`, which is reported and never does.
{%- if cookiecutter.database == "postgres" %}
The database is the only entry in `checks`.
{%- endif %}
{%- if cookiecutter.cache == "redis" %}
The cache is informational only.
{%- endif %}
{%- if cookiecutter.object_storage == "s3" %}
The object store is informational only.
{%- endif %}
`dependencies` says whether each configured one is reachable, but none of
them can turn a 200 into a 503.
{%- if cookiecutter.cache == "redis" %}

The reasoning is worth having here rather than only in the HTTP reference,
because it is an observability decision as much as an API one: Redis is
shared across every pod and this cache fails open, so gating on it would make
every pod report itself unready in the same second — turning a degradation
the service is built to survive into a total, self-inflicted outage.
{%- endif %}
{%- if cookiecutter.object_storage == "s3" %}

Losing the object store breaks one endpoint, so pulling all traffic off a pod
to protect that one slice would cost more than it saves.
{%- endif %}

See [the full readiness reference](http-api.md#get-readyz-readiness) for the
response shapes.

## The three dashboards

| Dashboard | Identifier | The question it answers |
| --- | --- | --- |
{%- if cookiecutter.cache == "redis" %}
| Service health | `pyfr-service-health` | Is the service serving? Request rate, error rate and latency percentiles by route, plus the saturation signals — database pool usage and event loop lag — and Redis command latency. |
{%- else %}
| Service health | `pyfr-service-health` | Is the service serving? Request rate, error rate and latency percentiles by route, plus the saturation signals — database pool usage and event loop lag. |
{%- endif %}
| SLI and SLO | `pyfr-slo` | Are we meeting the objective, and how fast is the budget being spent? |
| Runtime | `pyfr-runtime` | Is the process itself healthy? Memory, threads, file descriptors, processor time and garbage collection. |

Saturation sits beside rate and errors deliberately. A connection pool at its
ceiling is a queue, and a queue is latency that has not been served yet — it
moves minutes before the error rate does.
{%- if cookiecutter.cache == "redis" %}

### The Redis panel shows latency, not pool usage

The service health dashboard's Redis panel is titled "Redis command latency
(p50/p99)", not "Redis pool usage" — and that title is accurate to what it
draws, not what was originally asked for.

The plan called for a Redis pool saturation panel, matching the database
connection pool panel beside it. Building it required first checking that
the metric exists, and it does not:
`opentelemetry-instrumentation-redis` emits **spans, no metrics at all** —
confirmed against a live stack by generating real cache traffic and querying
Prometheus's own label-values endpoint for anything named `redis` or `pool`.
Nothing came back.

A panel querying a metric that is not there would not error — it would
render empty, and an empty saturation panel reads as "zero saturation", which
is a false "everything is fine" rather than an honest "not observed". That
failure mode is worse than the panel not existing.

What the panel draws instead: the `grafana/otel-lgtm` image runs a
span-metrics connector by default, which turns every span into a latency
histogram. Redis command spans are named after the raw command —
`GET`, `SET`, `DEL`, the three `CachedOrderRepository` issues — so the panel
queries `traces_spanmetrics_latency`, filtered to those three span
names. It is a real, useful signal — the span is how you notice a "fast"
cache read that is actually costing 40 milliseconds, which is exactly the
kind of problem a fail-open cache hides from every other signal, because the
request still succeeds and no error rate moves. It answers "is Redis slow",
not "is the Redis pool full", and the panel title says so rather than
implying otherwise.
{%- endif %}

## How the three signals join up

A slow trace in Tempo, the log lines that request produced, and the metrics
counting it are all reachable from one another:

- Every log record emitted inside a span carries `trace_id` and `span_id`.
  Grafana's Loki data source is preconfigured to turn `trace_id` into a link
  straight to the trace.
- Every metric carries `job`, which is the service name, plus
  `service_version` and the deployment environment.
- The access log records `http.route` — the route *template*
  `/api/v1/orders/{order_id}`, never the raw path — which is the same label
  the metrics use, so one filter works across both.

`correlation_id` and `trace_id` are different things and both are worth
having. See [Logging](logging.md).

## The objectives

Two indicators, both measured over a rolling 30 days:

- **Availability** — the fraction of requests not returning a 5xx. Target
  99.9%.
- **Latency** — the fraction of requests completing within 300 milliseconds.
  Target 99.9%.

Health endpoints are excluded from both. An orchestrator probes them every
couple of seconds forever; counted, a service serving ten real requests a
minute beside eighteen hundred probes would report a healthy objective while
failing every request a user actually makes.

### Error budget and burn rate

An **error budget** is the amount of failure the objective permits: at 99.9%
over 30 days, one request in a thousand may fail.

A **burn rate** is how fast that budget is being spent. A burn rate of 1
spends the whole month's budget in exactly a month. A burn rate of 14.4
spends it in about two days.

Alerting on burn rate rather than on a fixed error threshold is what avoids
both failure modes of a simple alert: paging constantly during harmless blips,
or staying silent through a slow bleed.

### Why each alert uses two windows

Every alert requires a **long** window and a **short** window to be over the
threshold at the same time.

- The long window is the signal: something is genuinely wrong, not a blip.
- The short window is the reset: it falls back quickly once the problem stops,
  so the alert clears instead of smouldering for hours after recovery.

Neither window alone gives both properties, which is the entire reason there
are two.

| Alert | Burn rate | Windows | Severity |
| --- | --- | --- | --- |
| Fast burn | 14.4 | 1h and 5m | page |
| Slow burn | 6 | 6h and 30m | page |
| Budget bleed | 1 | 3d and 6h | ticket |

Both indicators get all three.

## Changing the objectives

Every number lives in `src/{{ cookiecutter.package_name }}/observability/slo.py`.

Changing the latency threshold means changing it in **two** places that must
agree: the histogram boundary in that module, and the `le=` matcher in
`ops/prometheus/rules/slo.yml`. This is not optional bookkeeping. Prometheus
can only count requests faster than a boundary that exists, so a
threshold with no matching boundary makes the latency indicator not merely
inaccurate but uncomputable — and silently, because an empty PromQL result is
not an error.

`just test` fails until the two agree. `just o11y-gates` additionally runs the
rules through `promtool` unit tests.

The objective is not a cookiecutter prompt. M7 considered one and dropped
it: the numbers are threaded through `slo.py`, the rules, their `promtool`
tests and the SLO dashboard, and templating that arithmetic would have
been the most fragile Jinja in the tree. A generated project starts at
99.9 % and 300 ms and edits them here.

Two places the tests do not reach: `ops/prometheus/slo_test.yml`, whose
synthetic series and alert summaries `just o11y-gates` asserts, and the
two threshold values in `ops/grafana/dashboards/slo.json`, which nothing
checks — change both by hand when the target moves.

## Sampling in production

`APP_OTEL__SAMPLE_RATIO` sets the fraction of **new** traces recorded.
Sampling is parent-based, so a request that arrives already carrying a sampled
parent is always recorded whatever the ratio says — a trace crossing several
services is never half-recorded. Recording every span costs real money at
volume; 100% locally and something lower in production is the normal shape.

!!! danger "`APP_OTEL__LOGS_ENABLED` doubles your log bill"

    Standard output is the source of truth for logs. It survives a collector
    outage and captures crashes and any failure happening before the SDK has
    initialised — which is exactly the output you need when a service will not
    start.

    OTLP log export is added **on top of** standard output, never instead of
    it. Turning it on in production alongside a platform log agent means every
    line is ingested twice: double the volume, double the bill.

    It exists so that locally you see log lines beside the matching trace in
    Grafana without wiring up a log scraper. `just o11y` turns it on for you.
