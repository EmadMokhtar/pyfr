---
last_reviewed: 2026-09-10
---

# 0001. Enforce a four-layer dependency rule

**Status:** Accepted
**Date:** 2026-08-28

## Context

A service accumulates coupling quietly. A domain object imports a FastAPI
type "just for a status code", a use case imports SQLAlchemy "just for a
session", and eighteen months later the business rules cannot be tested
without a database and an HTTP client.

Nothing about this is caught by a code review that is looking at one pull
request at a time, because each individual import is defensible.

## Decision

Four layers — `domain`, `services`, `api`, `infrastructure` — with
dependencies pointing inward only. `domain` imports nothing but Pydantic.
`services` imports `domain`. `api` and `infrastructure` may import both,
and never each other's internals.

The rule is enforced by `import-linter` in `.importlinter`, run by
`just imports` and by CI. It is a build failure, not a convention.

## Alternatives considered

- **A convention documented in a contributing guide.** Rejected: this is
  the arrangement that produced the problem. A rule that depends on
  everyone remembering it under deadline is not a rule.
- **Three layers, folding `api` and `infrastructure` together.** Rejected:
  they have genuinely different reasons to change — one follows the HTTP
  contract, the other follows whatever the database and the provider do —
  and merging them removes the boundary that keeps a driver detail out of
  a request handler.
- **A separate package per layer.** Rejected as premature. It buys the
  same enforcement `import-linter` already gives, at the cost of four
  build configurations and a versioning problem between them.

## Consequences

The domain layer is testable with no Docker, no network and no fixtures,
which is why `just test` runs in seconds and needs no daemon.

The cost is real and lands on newcomers. Placing a piece of code requires
knowing which layer owns it, and the answer is occasionally genuinely
unclear — mapping between a domain object and a response schema is the
recurring one. `just imports` fails the build rather than letting the
question be deferred, which is the point, but it is friction.

It also forces a mapping layer that a smaller service would not need:
`domain.Order` cannot be returned from a route, so an `api` schema and a
mapper exist for it. That is duplication, accepted deliberately, so that a
change to the HTTP contract cannot silently change the domain model.

Full reasoning: [spec section 4.3](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
