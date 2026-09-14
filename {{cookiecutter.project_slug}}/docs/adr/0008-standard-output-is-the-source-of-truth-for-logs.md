---
last_reviewed: 2026-09-10
---

# 0008. Treat standard output as the source of truth for logs

**Status:** Accepted
**Date:** 2026-09-02

## Context

M2's observability work has already settled traces and metrics onto
OTLP (0007). Logs are the odd one out: a collector sits between the
process and wherever logs end up, and a service that only writes to the
collector has nothing to say about a failure that happens before the
collector is reachable.

## Decision

We write logs to standard output as one JSON object per line, in every
environment, always. OTLP log export exists — `OtelSettings.logs_enabled`
— but it is off by default and explicitly *in addition to* stdout, never
instead of it: the compose `o11y` profile turns it on locally for
trace-to-log correlation in Grafana, and nothing else should.

## Alternatives considered

- **OTLP-only.** Rejected: it loses exactly the output an operator needs
  most — a crash, or anything failing before the OpenTelemetry SDK has
  initialised, since there is no exporter yet to carry it. It also
  disappears entirely during a collector outage, which is precisely when
  logs matter most.
- **Files.** Rejected: a container writing log files inside itself is a
  disk-space incident waiting to happen, and it adds a rotation policy to
  maintain for no benefit stdout does not already give for free.

## Consequences

Logs survive a collector outage, because stdout does not depend on the
collector being reachable, and they capture the startup failures that
happen before any exporter exists to carry them elsewhere.

The cost is a real one to get wrong: turning OTLP log export on in
production alongside a platform log agent that is already reading the
container's stdout ingests every line twice, doubling both log volume
and whatever the logging platform bills by volume. This is why
`logs_enabled`'s field description states the risk directly and why the
setting defaults to `false` — the safe configuration is also the
default one, so doubling ingestion requires a deliberate, documented
opt-in rather than an accidental one.

Full reasoning: [spec section 7.6](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
