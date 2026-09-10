---
last_reviewed: 2026-09-10
covers:
  - examples/reference-service/ops/prometheus/rules/
  - examples/reference-service/justfile
---

# Runbook

Four procedures, for four things that go wrong. Each says what you will
see, how to confirm it, and what to do.

**Before anything else:** capture the correlation identifier from the
failing request. Every log line carries it, and filtering on it hands you
the `trace_id` from the same lines — [correlation identifiers and trace
identifiers are different things](reference/logging.md#correlation-identifiers),
and having both is what turns "the API is slow" into one traceable
request instead of a guess.

All `just` commands below run from `examples/reference-service/`.

## A migration is dirty

**Symptom.** The `migrate` container exits non-zero. `app` depends on it
completing successfully (`compose.yaml`), so the deployment stops there —
nothing rolls forward with a schema in an unknown state.

**Confirm.**

```bash
just migrate-version
```

Prints the current version and whether the database is marked dirty.

**Act.**

1. Read the failed migration's `.up.sql` against the real schema and work
   out whether it partially applied. Look at the tables and columns it
   touches, not the migration's intent.
2. **If it did not apply at all:**

   ```bash
   just migrate-force <previous-version>
   just migrate
   ```

3. **If it did partially apply:** do not force past it. The forward fix
   is a new migration that finishes or reverses the partial change by
   hand — never an edit to the migration that already ran.

!!! danger "Do not"
    Do not edit a migration that has run anywhere — dev, staging or
    production. Do not run `migrate-force` before you have established,
    by looking at the real schema, what actually reached the database.

    `migrate force` runs no SQL. It only overwrites the version recorded
    in `schema_migrations` and clears the dirty flag — it is a claim
    about the state of the schema, and a wrong claim is worse than the
    dirty flag it replaces. See [ADR 0004](adr/0004-golang-migrate-owns-the-schema.md)
    for why golang-migrate owns the schema at all.

## A dependency is down

The symptom differs by dependency, which is the point of this section:
only one of the four leaves the load balancer.

| Dependency | Symptom |
| --- | --- |
| PostgreSQL | `/readyz` returns 503 and the instance leaves load balancing. It is the only gating dependency — [ADR 0011](adr/0011-readyz-reports-optional-dependencies-without-gating.md). |
| Redis (cache) | Requests still succeed. Cache hit rate falls to zero and latency rises. This is by design — [ADR 0006](adr/0006-the-cache-is-fail-open-always.md). |
| S3 / MinIO (receipts) | Only `GET /api/v1/orders/{order_id}/receipt` fails. No order-placing request is affected. |
| Payment gateway | The circuit breaker opens after `APP_PAYMENT__BREAKER_FAILURE_THRESHOLD` consecutive failures (default 5). Order placement then fails fast with a 503 instead of hanging. |

**Confirm.**

```bash
curl -s localhost:8000/readyz | jq
```

`checks` is the gating result (database only). `dependencies` reports the
cache and object store without gating on either — both fields are always
present, whether the dependency they name is up or down.

**Act, per dependency.**

- **PostgreSQL down:** this is a real outage for every instance that
  cannot reach it. Check the database itself — connectivity, disk,
  replica lag — not the application.
- **Redis down:** nothing to do at the application layer. The cache
  fails open by design; PostgreSQL is already answering every request
  correctly. Fix Redis on its own timeline and watch the cache-hit-rate
  panel in the meantime.
- **S3 / MinIO down:** check the object store. Only receipts are
  affected; orders keep placing normally.
- **Payment gateway degraded:** check the gateway's own status. The
  breaker self-heals — it admits one probe after
  `APP_PAYMENT__BREAKER_RESET_AFTER_SECONDS` (default 30s) and closes
  again if that probe succeeds.

!!! danger "Do not"
    Do not restart instances because Redis is down. They are healthy,
    and a rolling restart during a cache outage adds a cold-start
    stampede to an incident that was, until that restart, entirely
    survivable.

## A burn-rate alert is firing

**Symptom.** One of the alerts in `ops/prometheus/rules/slo.yml` fires:
`SLOAvailabilityFastBurn`, `SLOAvailabilitySlowBurn`,
`SLOAvailabilityBudgetBleed`, or the three `SLOLatency*` equivalents.

A burn rate is the rate the error budget is being consumed, relative to
the rate that would exhaust it exactly at the period's end. `slo.yml`
defines three tiers, and the severity is on the alert, not something you
have to infer:

| Alert pair | Severity | At this rate, the 30-day budget is gone in |
| --- | --- | --- |
| `*FastBurn` | `page` | ~2 days |
| `*SlowBurn` | `page` | ~5 days |
| `*BudgetBleed` | `ticket` | the full 30 days, right on schedule |

Both fast burn and slow burn page. Budget bleed does not — it is a
degradation slow enough to fix during the day, not overnight.

**Confirm.** The Grafana "SLI and SLO" dashboard
(`ops/grafana/dashboards/slo.json`). "Service health"
(`service-health.json`) and "Runtime" (`runtime.json`) narrow it further
if the SLO dashboard shows the burn but not the cause.

**Act.** Identify whether the errors are concentrated in one endpoint or
one dependency. Pull the correlation identifier from a failing request
and follow it through the logs; if a dependency is implicated, go to
[A dependency is down](#a-dependency-is-down) above.

!!! danger "Do not"
    Do not silence the alert without an owner and a deadline attached.
    A silenced budget-bleed alert with no owner is how a ticket-worthy
    degradation becomes next month's fast burn.

## Rolling back

**Symptom.** A release is bad and forward-fixing is slower than
reverting.

**Act, in this order and no other.**

1. **First, establish whether the release included a migration** —
   before touching any image:

   ```bash
   just migrate-version
   ```

   Compare the version this prints against the previous release's
   expected version.

2. **No migration:** roll the application image back. Stop here.
3. **Migration included:** roll the application back only if the
   previous version can run against the *current* schema. A migration
   that dropped or renamed a column the previous release reads means the
   rollback is itself a schema change:

   ```bash
   just migrate-down <steps>
   ```

   Treat this with the same care as [A migration is dirty](#a-migration-is-dirty)
   above — confirm what the schema actually looks like before and after,
   the same way you would for a forward migration.

!!! danger "Do not"
    Do not roll an image back without checking for a migration first.
    This is the mistake that turns a bad release into an outage, which
    is why the check is the first step here, not a caveat at the end.
