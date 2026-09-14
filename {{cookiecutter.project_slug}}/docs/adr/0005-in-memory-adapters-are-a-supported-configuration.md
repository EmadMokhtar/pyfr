---
last_reviewed: 2026-09-10
---

# 0005. Treat in-memory adapters as a supported configuration

**Status:** Accepted
**Date:** 2026-08-28

## Context

M0's walking skeleton has to serve a working API before M1 adds
PostgreSQL, M4 adds Redis and object storage, and before any payment
provider is configured. Something has to decide what the service does
when a dependency it could use is simply not configured.

## Decision

We treat every optional dependency's absence as a selection, not a
failure. `container.py`'s `build_container` reads `settings.database`,
`settings.payment`, `settings.cache` and `settings.storage`, each of
which is `None` unless its environment variables are set, and for each
one builds the in-memory adapter when its settings are absent: no
database configured means `InMemoryOrderRepository`; no payment provider
means `InMemoryPaymentGateway`, which authorises everything; no storage
configured means the default `InMemoryReceiptStore`. The cache is the one
exception in shape, not in spirit — it is a decorator rather than a
standalone adapter, so its absence simply means nothing wraps the
repository that was already selected. `APP_DATABASE__DSN` left unset
therefore means an in-memory repository at startup, not a crash.

## Alternatives considered

- **Requiring every dependency.** Rejected: `just dev` would need four
  containers running before the service could answer a single request,
  and a walking skeleton with no database is a real product in its own
  right — an aggregator, a webhook receiver, something with no state of
  its own to persist.
- **Test-only fakes.** Rejected: a fake that is not itself a supported
  production path is a fake that drifts from the adapter it stands in
  for. Nothing would notice the drift until the day someone tried to run
  the service without the infrastructure the fake was pretending to
  stand in for.

## Consequences

The service starts with no infrastructure at all, which makes the first
five minutes after `git clone` work without a single container running,
and keeps unit tests container-free — they exercise the same adapters a
production service without that dependency would use, not a parallel
test double.

The cost is two code paths per port, both of which must keep behaving
identically to the port's contract, doubling the surface a change to
that contract has to be checked against. There is also a real production
risk: someone ships a service with the in-memory repository selected by
leaving a variable unset, and every write since the last restart is gone
the moment the process recycles. `build_container` does not prevent
that — it cannot, from inside the composition root, know what an
operator meant to configure — and today nothing announces the choice
either: `build_container` and `main.py`'s lifespan emit no log line
naming which adapter was selected for which port. The only place that
information surfaces at all is `/readyz`'s response body, whose `checks`
and `dependencies` keys are populated only for the ports that were
actually wired — a signal an operator has to know to look for, not one
the service volunteers at startup. That gap is worth closing; this
record does not close it, and does not pretend a safety net exists here
that the code does not have.

Full reasoning: [spec section 5.1](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
