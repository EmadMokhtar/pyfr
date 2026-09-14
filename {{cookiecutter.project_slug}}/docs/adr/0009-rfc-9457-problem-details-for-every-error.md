---
last_reviewed: 2026-09-10
---

# 0009. Return RFC 9457 Problem Details for every error

**Status:** Accepted
**Date:** 2026-08-28

## Context

M0's walking skeleton needs an error shape before it has more than one
route, because retrofitting a consistent error contract onto an API that
already has clients is far more disruptive than choosing one at the
start.

## Decision

We return `application/problem+json` per RFC 9457 for every error the
service produces, with no exception. `api/errors.py` registers one
handler per error family — domain errors, an unavailable payment
provider, unavailable storage, the framework's own routing and
body-reading failures, and request validation — and every one of them is
rendered through the same `ProblemDetail` model, at the same media type.
Validation failures are included, not exempted: `RequestValidationError`,
the exception FastAPI raises for a request body that fails its schema, is
caught and translated into a `ProblemDetail` rather than left to
FastAPI's default `{"detail": [...]}` shape.

## Alternatives considered

- **FastAPI's default `{"detail": …}` shape.** Rejected: it is
  undocumented as a contract — nothing pins its structure — and it
  genuinely varies in shape between a validation error, whose `detail` is
  a list of per-field error objects, and a raised `HTTPException`, whose
  `detail` is a single string. A client written against one shape breaks
  silently against the other.
- **A bespoke error envelope.** Rejected: RFC 9457 is a registered IETF
  standard with existing client and tooling support. Inventing a local
  shape solves nothing a standard does not already solve, and costs every
  future integrator a lookup into a format nobody else uses.

## Consequences

Clients can rely on exactly one error shape across every status code the
service returns, and `type` gives each error kind a stable identifier —
`.../order_not_found`, `.../validation_error` — that survives a later
rewording of the human-readable `title` or `detail`.

The cost is a translation layer sitting over FastAPI's own exception
handling: seven handlers in `api/errors.py`, each responsible for turning
one exception family into the same shape, including a second handler for
a raw `pydantic.ValidationError` that reaches the boundary from below
rather than from a request body. The layer also enforces a discipline
that has to be maintained deliberately: the domain layer never
constructs an HTTP status code, decides one status per domain error only
in `status_for`, and the day a domain error needs a new status is a day
that function changes, not a day a domain module reaches for `fastapi`.

Full reasoning: [spec section 4.2](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
