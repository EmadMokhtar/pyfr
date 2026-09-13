---
last_reviewed: 2026-09-11
---

# 0010. Commit the OpenAPI document and gate it on drift

**Status:** Accepted
**Date:** 2026-09-09

## Context

M3 deepens the contract testing around the service's API.
FastAPI can generate an OpenAPI document from the code at any time, on
request, which means a change to the API can happen without the
document ever being looked at by a reviewer — the document is always
technically correct and can still hide exactly the change that matters.

## Decision

We generate `openapi.json` from the code, commit it, and run a drift
gate in CI that regenerates the document and fails the build on any
difference from the committed copy. A second committed file,
`openapi.baseline.json`, holds the last released contract, and `oasdiff`
compares the current specification against it to classify every change
as breaking or not, feeding the Conventional Commits cross-check described
in spec section 10.2: a breaking change ships only when a commit in the
range under test marks itself breaking (`feat!:`, `feat(api)!:`, or a
`BREAKING CHANGE:` footer), and fails the build otherwise.

## Alternatives considered

- **Generating it at build time only, never committing it.** Rejected:
  an API change then has no diff to review at all — the contract changes
  invisibly inside a pull request that, read on its own, looks like an
  internal refactor of a route handler.
- **Writing it by hand.** Rejected: a hand-maintained specification
  drifts from the code it is supposed to describe almost immediately,
  and nothing would notice when it did.

## Consequences

Every API change now appears in a pull request as a reviewable diff to
`openapi.json`, and a breaking change is caught by `oasdiff` against the
baseline rather than discovered by a client whose integration silently
stops working.

The cost is a regeneration step, `just openapi`, that a developer has to
remember to run after changing a route or a schema — and people forget
it. The drift gate is what catches that forgetting, loudly, in CI rather
than quietly in production: a forgotten regeneration fails the build with
a diff, not a merged pull request whose committed contract already
disagrees with the code that shipped.

Full reasoning: [spec section 8.2](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
