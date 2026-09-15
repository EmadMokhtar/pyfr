---
last_reviewed: 2026-09-14
---

# {{ cookiecutter.project_name }}

{{ cookiecutter.description }}

This site documents the service: how to run it ([Getting started](getting-started.md)),
what to do when it misbehaves ([Runbook](runbook.md)), how to change it
(Guides), what it exposes (Reference), and why it is built the way it is
(Decisions, Explanation).

The service was generated from [PyFr](https://github.com/EmadMokhtar/pyfr),
a cookiecutter template for production-ready Python microservices; PyFr's
own site describes the template.

## What you get

Everything below runs today, and every item has a page:

- **An HTTP API** with an application factory and a lifespan, interactive
  documentation at `/docs`, and [RFC 9457 Problem
  Details](reference/errors.md) for every error — RFC 9457 is the internet
  standard shape for a JSON error body. The endpoints are in [HTTP
  API](reference/http-api.md); the committed OpenAPI document and its
  drift gate in [The API contract](reference/contract.md).
- **Four layers** — domain, services, infrastructure, api — with the
  dependency rule [enforced by a build check](explanation/layers.md), not
  by code review. [Architecture](explanation/architecture.md) is the
  overview.
- **Configuration validated at startup.** A bad value stops the process
  with a readable message instead of causing an error an hour later. Every
  variable is in [Configuration](reference/configuration.md).
- **Structured logging** — one JSON object per line on standard output,
  with correlation identifiers and redaction — in [Logging](reference/logging.md).
- **OpenTelemetry** traces, metrics and logs, a local Grafana stack, three
  dashboards and service level objective alerts — in
  [Observability](reference/observability.md).
- **Three health endpoints** answering three different questions, with
  readiness in two tiers: a required dependency gates `/readyz`, an
  optional one is reported without gating. [HTTP API](reference/http-api.md#get-readyz-readiness)
  has the shape; [Observability](reference/observability.md#readiness-reports-optional-dependencies-and-gates-on-none)
  has the reasoning.
- **Graceful shutdown**, so a rolling deployment does not drop live
  requests — and the deadline trap to avoid, in
  [Run in a container](guides/run-in-a-container.md#the-shutdown-deadline-trap).
{%- if cookiecutter.database == "postgres" %}
- **Two hardened container images** — the service, and a migrations image
  that applies the schema before the service starts — non-root, no build
  tools, no shell utilities in the final layer, built for `amd64` and
  `arm64`, scanned before every release. [Run in a
  container](guides/run-in-a-container.md) and [Supply
  chain](reference/supply-chain.md).
{%- else %}
- **A hardened container image**: non-root, no build tools, no shell
  utilities in the final layer, built for `amd64` and `arm64`, scanned
  before every release. [Run in a container](guides/run-in-a-container.md)
  and [Supply chain](reference/supply-chain.md).
{%- endif %}
- **Its own workflows**, running from the first push: `ci.yml`,
  `nightly.yml`, `release.yml`, `docs.yml` and `template-update.yml`, with
  a Dependabot schedule. [Contributing](contributing.md) has the checks
  they run; [Supply chain](reference/supply-chain.md#what-is-checked-where)
  the security ones; the `README.md`'s *Continuous integration and
  releases* section lists all five and the repository settings they need.
- **An outbound HTTP client** with retries and a circuit breaker, and
  recorded cassettes for its tests — in [Outbound HTTP calls](guides/outbound-http.md).

## Where to go next

| If you want to | Read |
| --- | --- |
| Run the service and place an order | [Getting started](getting-started.md) |
| Fix it at three in the morning | [Runbook](runbook.md) |
| Add your own endpoint through all four layers | [Add an endpoint](guides/add-an-endpoint.md) |
| Store data in something the service does not ship | [Add a backend](guides/add-a-backend.md) |
| Look up a `just` command | [Commands](reference/commands.md) |
| Look up an environment variable | [Configuration](reference/configuration.md) |
| Look up an endpoint or an error shape | [HTTP API](reference/http-api.md) · [Errors](reference/errors.md) |
| Understand how the pieces fit | [Architecture](explanation/architecture.md) |
| Work on the service | [Contributing](contributing.md) |
| Look up a term used on this site | [Glossary](glossary.md) |
