---
last_reviewed: 2026-09-10
---

# 0006. Make the cache fail open, always

**Status:** Accepted
**Date:** 2026-09-10

## Context

M4 adds Redis as an optional cache in front of the order repository.
Redis is a shared instance, not one-per-pod, so its failure mode is
different from PostgreSQL's: PostgreSQL going down means the service has
genuinely lost its data, but Redis going down means the service has lost
a shortcut to data it can still reach another way.

## Decision

We make every Redis failure fail open. `CachedOrderRepository` catches
`Exception` broadly around every read, write and invalidation call to
Redis — connection failures, timeouts, and a payload that fails to
parse as a valid `Order` are all logged at `warning` and swallowed, and
the wrapped repository answers instead. There is no setting that changes
this: `CacheSettings` carries a DSN and a TTL and nothing that selects a
different failure behaviour.

## Alternatives considered

- **Fail closed.** Rejected: it converts a latency degradation the
  service is deliberately built to survive — Redis is down, PostgreSQL
  answers a little slower — into a total outage, for a dependency whose
  entire job was to make things faster, never to make them possible.
- **A configurable mode.** Rejected: the failing mode would be the one
  selected by whoever had not thought carefully about the difference,
  under exactly the conditions — a production incident, a rushed config
  change — where the wrong setting does the most damage. A flag whose
  wrong value takes production down is not a feature worth shipping.

## Consequences

A Redis outage costs latency, not availability: every read falls through
to PostgreSQL, every response is still correct, and `/readyz` reports the
cache under `dependencies` without letting its failure affect the status
code or the pod's place in load balancing (see 0011).

The cost is that a persistently broken cache is quiet. The service keeps
serving normally while every read silently misses, with nothing failing
loudly enough to page anyone — a `warning`-level log line per failed
call is the only signal, and at any real request volume that becomes
background noise rather than an alert. The cache hit rate has to be a
dashboard panel and an alert of its own, because a health check built to
survive a broken cache is, by construction, not going to be the thing
that notices one.

Full reasoning: [spec section 12](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
