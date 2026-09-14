---
last_reviewed: 2026-09-14
---

# Decision records

Each page here records one decision: what was decided, when, why, and what
it cost. They are short on purpose. The full reasoning lives in the
[design specification](https://github.com/EmadMokhtar/pyfr/tree/main/docs/superpowers),
and each record links to the section that argues its case.

The records were written while PyFr's reference service — the service this
project was generated from — was being built, and records 1 to 12 were
backfilled after the work they describe. The "Decided" column names the
PyFr milestone (M0, M1, …) that made each decision — PyFr's
[roadmap](https://emadmokhtar.github.io/pyfr/roadmap/) says what each
milestone built — and a record is dated to that milestone rather than to
the day it was written.

## Why they are never edited

An accepted record is history. It says what was decided on a date, given
what was known then. Changing your mind means writing a **new** record and
marking the old one superseded — never rewriting the old one, which
destroys the only account of why the software is the way it is.

For the same reason, records are exempt from the review-date warning that
covers every other page on this site. A decision does not go stale.

## Adding one

Copy [`template.md`](template.md), take the next number, and add it to the
nav in `mkdocs.yml`. Write it when the decision is made, while the
alternatives are still fresh — a record written six months later is a
reconstruction, and it shows.

## The records

Three decisions belong to PyFr, the template this project was generated
from, and are recorded on its site: cookiecutter over Copier and cruft
(0002), uv over pip and Poetry (0003), and the template is the source of
truth (0017).

| | Record | Decided |
|---|---|---|
| 0001 | [The four-layer dependency rule](0001-four-layer-dependency-rule.md) | M0 |
| 0002 | [cookiecutter over Copier and cruft](https://emadmokhtar.github.io/pyfr/adr/0002-cookiecutter-over-copier-and-cruft/) | M0 |
| 0003 | [uv, not pip or Poetry](https://emadmokhtar.github.io/pyfr/adr/0003-uv-over-pip-and-poetry/) | M0 |
| 0004 | [golang-migrate owns the schema](0004-golang-migrate-owns-the-schema.md) | M1 |
| 0005 | [In-memory adapters are a supported configuration](0005-in-memory-adapters-are-a-supported-configuration.md) | M0 |
| 0006 | [The cache is fail-open, always](0006-the-cache-is-fail-open-always.md) | M4 |
| 0007 | [Emit OpenTelemetry and stop there](0007-emit-opentelemetry-and-stop.md) | M2 |
| 0008 | [Standard output is the source of truth for logs](0008-standard-output-is-the-source-of-truth-for-logs.md) | M2 |
| 0009 | [RFC 9457 Problem Details for every error](0009-rfc-9457-problem-details-for-every-error.md) | M0 |
| 0010 | [The OpenAPI document is committed and drift-gated](0010-the-openapi-document-is-committed-and-drift-gated.md) | M3 |
| 0011 | [`/readyz` reports optional dependencies without gating](0011-readyz-reports-optional-dependencies-without-gating.md) | M4 |
| 0012 | [mypy is strict on the inner layers only](0012-mypy-is-strict-on-the-inner-layers-only.md) | M0 |
| 0013 | [Redact by key name, in the shared processor chain](0013-redaction-is-a-processor-in-the-shared-chain.md) | M6 |
| 0014 | [Dependabot, and one pin per tool](0014-dependabot-and-one-pin-per-tool.md) | M6 |
| 0015 | [Images are published on release, under the repository's version](0015-images-are-published-on-release-under-the-repository-version.md) | M6 |
| 0016 | [Image scanning fails on fixed findings, and exemptions expire](0016-image-scanning-fails-on-fixed-findings-and-exemptions-expire.md) | M6 |
| 0017 | [The template is the source of truth, and a golden diff proves it](https://emadmokhtar.github.io/pyfr/adr/0017-the-template-is-the-source-of-truth/) | M7 |
