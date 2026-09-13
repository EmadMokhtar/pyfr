---
last_reviewed: 2026-09-10
---

# 0011. Let `/readyz` report optional dependencies without gating on them

**Status:** Accepted
**Date:** 2026-09-10

## Context

By M4, `/readyz` has three dependencies it could check: PostgreSQL,
Redis and the S3-compatible object store. All three can fail
independently, and Redis in particular is a single shared instance
behind every pod, not one per pod the way the database connection pool
is — so a naive readiness check that fails on any dependency treats a
shared cache's outage the same as the loss of the pod's own database
connection.

## Decision

We split readiness into two tiers, implemented in `container.py`'s
`ReadinessRegistry`. The database is the only dependency registered as
**gating**: `build_container` registers a `database` check only when
`settings.database` is configured, and if it fails, `/readyz` returns 503
and the instance leaves load balancing. The cache and the object store
are registered as **informational**: their checks run under the same
timeout and are reported under the response's `dependencies` field, but
`ReadinessReport.healthy` is computed only from the `gating` dict, so
neither one can affect the status code, confirmed directly in
`api/health.py`'s `readiness` handler, which sets 503 only when
`report.healthy` is false.

## Alternatives considered

- **Gating on every dependency.** Rejected: Redis is shared across every
  pod, so gating on it makes every instance unready in the same second
  the moment it degrades, converting a survivable degradation — the
  cache is fail-open by design (0006) — into a total outage the cache
  was never supposed to be able to cause.
- **Reporting nothing about the optional dependencies.** Rejected: an
  operator then cannot tell a fully healthy instance from one silently
  missing every cache read or unable to reach object storage, and the
  first sign of trouble becomes a support ticket rather than a dashboard
  panel.

## Consequences

An optional dependency's outage becomes visible — in the response body,
and from there in whatever scrapes it — without being fatal to the pod
serving it. The database keeps the one property `/readyz` exists to
provide: a pod that cannot reach its actual data store leaves rotation.

The cost is that "ready" now means something more specific than the
single word suggests. The endpoint's own module docstring in
`api/health.py` spells out which tier each dependency belongs to for
exactly this reason — a subtlety easy to lose the next time a dependency
is added, since the natural instinct is to register every new check the
same way as the first one, and only the database is supposed to answer
`True` to "does losing this make the pod unready".

The specification itself, in the section cited below, describes
`/readyz` as checking "database, cache and storage" and removing the pod
from load balancing "when they fail" — read literally, gating on all
three. This record deliberately narrows that to the database alone:
Redis and the object store are shared across every pod rather than
one-per-pod, so gating on either would make every instance unready in
the same second it degraded, converting an individually survivable
degradation — the cache is fail-open by design (0006) — into a total
outage neither dependency was ever supposed to be able to cause. The
specification has no dedicated section on readiness tiering, so section
12 is still the closest citation despite that wording gap.

Full reasoning: [spec section 12](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
