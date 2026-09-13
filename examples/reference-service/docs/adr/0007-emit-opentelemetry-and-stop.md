---
last_reviewed: 2026-09-10
---

# 0007. Emit OpenTelemetry and stop there

**Status:** Accepted
**Date:** 2026-09-02

## Context

M2 adds observability to the service. Every organisation
generating a service from PyFr already sends telemetry somewhere —
Datadog, an in-house Grafana stack, a managed vendor — so the template
has to decide how much of an observability platform, if any, it ships
alongside the service itself.

## Decision

We emit standard OTLP (OpenTelemetry Protocol — the wire format for
traces, metrics and logs) traces, metrics and, optionally, logs, and
bundle no observability platform of our own. The compose stack's
`grafana/otel-lgtm` image — Grafana, Prometheus, Tempo, Loki and a
collector in one container — is a local development convenience behind
a compose profile, verifying that the instrumentation and the shipped
dashboards actually work; it is never a deployment target.

## Alternatives considered

- **Bundling an observability platform.** Rejected: teams adopting PyFr
  already have somewhere telemetry goes. A second platform arriving with
  the template is not a gift — it is a second thing to operate, secure
  and eventually decommission.
- **Vendor-specific SDKs.** Rejected: instrumenting directly against one
  vendor's SDK makes the telemetry unportable, which is the one problem
  OpenTelemetry exists to solve. A service instrumented that way can only
  ever be pointed at the vendor it was written for.

## Consequences

The generated service's telemetry works with whatever the adopting team
already runs, because OTLP is the interface, not a specific backend.
Telemetry also costs nothing when unwanted: `OtelSettings.enabled`
defaults to `false`, and with it off the process builds no providers,
opens no socket and starts no background task — a service that wants
none of this pays nothing for carrying the capability.

The cost is that PyFr cannot promise a working dashboard out of the box
beyond the local `o11y` compose profile. The three provisioned
dashboards and the burn-rate alerting rules are real and tested, but they
are Grafana-shaped: a team on a different platform gets correctly-shaped
OpenTelemetry data and has to build their own panels and rules against
it, not a working import.

Full reasoning: [spec section 7.1](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
