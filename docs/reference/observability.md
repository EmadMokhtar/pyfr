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

## The three dashboards

| Dashboard | Identifier | The question it answers |
| --- | --- | --- |
| Service health | `pyfr-service-health` | Is the service serving? Request rate, error rate and latency percentiles by route, plus the saturation signals — database pool usage and event loop lag. |
| SLI and SLO | `pyfr-slo` | Are we meeting the objective, and how fast is the budget being spent? |
| Runtime | `pyfr-runtime` | Is the process itself healthy? Memory, threads, file descriptors, processor time and garbage collection. |

Saturation sits beside rate and errors deliberately. A connection pool at its
ceiling is a queue, and a queue is latency that has not been served yet — it
moves minutes before the error rate does.

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

Every number lives in `src/reference_service/observability/slo.py`.

Changing the latency threshold means changing it in **two** places that must
agree: the histogram bucket boundary in that module, and the `le=` matcher in
`ops/prometheus/rules/slo.yml`. This is not optional bookkeeping. Prometheus
can only count requests faster than a bucket boundary that exists, so a
threshold with no matching boundary makes the latency indicator not merely
inaccurate but uncomputable — and silently, because an empty PromQL result is
not an error.

`just test` fails until the two agree. `just o11y-gates` additionally runs the
rules through `promtool` unit tests.

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
