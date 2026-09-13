---
last_reviewed: 2026-09-12
---

# PyFr

A cookiecutter template for production-ready Python microservices.

You answer a short list of prompts and receive a repository that runs, is
tested, is observable, and is documented. The target is a working service in
ten minutes, in place of the two to four weeks teams spend assembling the
same components by hand.

A **cookiecutter template** is a project skeleton with fill-in-the-blank
placeholders. The [cookiecutter](https://cookiecutter.readthedocs.io/) tool
asks you questions, substitutes your answers into the skeleton, and writes a
new repository to disk.

!!! warning "Status: M0–M6 done, M7 in progress, M8 to go"

    **The template is not finished yet.** `{{cookiecutter.project_slug}}/`
    is the template body, and it is already the source of truth: the
    *reference service* —
    [`examples/reference-service/`](https://github.com/EmadMokhtar/pyfr/tree/main/examples/reference-service)
    — is rendered from it and never edited by hand. Backend prompts and
    pruning, a generated project's own workflows and documentation site,
    and the full-suite tests are still to come.

    PyFr is built in three phases. Phase A (milestones M0 to M6) built that
    service as ordinary Python, with no template placeholders anywhere. Phase
    B (M7) is converting it into the template, in five pull requests.
    Phase C keeps the two in step forever after. The reason is stated
    plainly in the design: never debug Jinja and Python at the same time.
    (Jinja is the placeholder language cookiecutter uses.)

    M0 through M6 are done, and M7 is in progress. **PyFr becomes a usable
    template at the end of M7.** See the [roadmap](roadmap.md) for what each
    milestone delivers.

    Until then you can read the reference service, run it, and copy from it.
    Everything on this site describes code that exists and runs today.

## What you own

Generated code belongs entirely to the team that generated it. Nothing is
published to a package index, and a generated service imports no PyFr
package. There is no framework to upgrade and no library that can break you.

That choice has an obvious cost — a fix in PyFr does not reach services
already generated — and M8 removes it: a generated project pulls later
template versions into itself through a normal git merge. Teams keep full
ownership *and* receive fixes. The reasoning is in
[Why a template, not a framework](explanation/why-a-template.md).

## What a generated service contains

Everything below already runs in the reference service, today:

- **FastAPI** with an application factory and a lifespan, so tests build the
  app themselves instead of importing a module-level global.
- **Four layers** — domain, services, infrastructure, api — with the
  dependency rule [enforced by a build check](https://emadmokhtar.github.io/pyfr/reference-service/explanation/layers/), not by
  code review.
- **Configuration** validated at startup. A bad value stops the process with
  a readable message instead of causing an error an hour later.
- **Structured logging**: one JSON object per line, on standard output, with
  every third-party library's records passing through the same chain.
- **Three health endpoints** answering three different questions —
  see [HTTP API](https://emadmokhtar.github.io/pyfr/reference-service/reference/http-api/).
- **RFC 9457 Problem Details** error responses. RFC 9457 is the internet
  standard shape for a JSON error body.
- **Correlation identifiers**: one identifier binds every log line a single
  request produced.
- **Graceful shutdown**, so a rolling deployment does not drop live requests.
- **A hardened container image**: non-root user, no build tools, no shell
  utilities in the final layer.

## Where to go next

| If you want to | Read |
| --- | --- |
| Run the reference service and place an order | [Getting started](https://emadmokhtar.github.io/pyfr/reference-service/getting-started/) |
| Add your own endpoint through all four layers | [Add an endpoint](https://emadmokhtar.github.io/pyfr/reference-service/guides/add-an-endpoint/) |
| Store data in something PyFr does not ship | [Add a backend](https://emadmokhtar.github.io/pyfr/reference-service/guides/add-a-backend/) |
| Look up a `just` command | [Commands](https://emadmokhtar.github.io/pyfr/reference-service/reference/commands/) |
| Look up an environment variable | [Configuration](https://emadmokhtar.github.io/pyfr/reference-service/reference/configuration/) |
| Look up an endpoint or an error shape | [HTTP API](https://emadmokhtar.github.io/pyfr/reference-service/reference/http-api/) · [Errors](https://emadmokhtar.github.io/pyfr/reference-service/reference/errors/) |
| Understand how the pieces fit | [Architecture](https://emadmokhtar.github.io/pyfr/reference-service/explanation/architecture/) |
| Know what ships when | [Roadmap](roadmap.md) |
| Work on PyFr itself | [Contributing](contributing.md) |
| Look up a term used on this site | [Glossary](glossary.md) |
