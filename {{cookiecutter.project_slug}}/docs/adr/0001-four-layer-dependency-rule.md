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
`services` imports `domain` and nothing above it. `api` and
`infrastructure` both sit above `services` and `domain`, and are meant
never to import each other's internals.

Two of the three boundaries are enforced, not requested. `import-linter`
declares two contracts in `.importlinter`: `domain-independence` forbids
`domain` from importing `services`, `api`, `infrastructure`, the
container, the app factory, or any web or database framework package, and
`services-independence` forbids `services` from importing `api`,
`infrastructure`, the container, the app factory, or those same
frameworks. `just imports` runs both contracts as a build failure, and
`test_layer_purity.py` checks `domain` and `services` again from a
different angle — an allowlist of Pydantic and the standard library
rather than a blocklist, so a third-party import nobody thought to name
still fails.

The third boundary — `api` never reaching into `infrastructure`'s
internals, or the reverse — is a convention. No contract names either
module as a source, so nothing in `just imports` or CI would catch a
route handler importing an adapter directly, or an adapter importing an
`api` schema. It holds today because nobody has had reason to cross it,
not because anything is gated.

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

The `api`/`infrastructure` boundary is not gated. `.importlinter` has no
contract naming either module as a source, so nothing stops a route
handler from importing an adapter directly, or an adapter from importing
an `api` schema. The two boundaries this record does enforce are the ones
under the most pressure — `domain` reaching for a database driver,
`services` reaching for an HTTP framework — but the api/infrastructure
line can erode exactly as the Context section describes, one defensible
import at a time, and nothing here would catch it. Whether that is worth
a third `import-linter` contract is a decision for its own change; this
record does not make it, and does not pretend the gap is already closed.

Full reasoning: [spec section 4.3](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
