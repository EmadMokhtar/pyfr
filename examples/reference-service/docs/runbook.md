---
last_reviewed: 2026-09-13
covers:
  - ops/prometheus/rules/
  - justfile
  - src/reference_service/config_check.py
  - .trivyignore.yaml
---

# Runbook

Seven procedures, for seven things that go wrong. Each says what you will
see, how to confirm it, and what to do. The first five are about a running
service; the last two are about a red check on a pull request.

**Before anything else:** capture the correlation identifier from the
failing request. Every log line carries it, and filtering on it hands you
the `trace_id` from the same lines — [correlation identifiers and trace
identifiers are different things](reference/logging.md#correlation-identifiers),
and having both is what turns "the API is slow" into one traceable
request instead of a guess.

All `just` commands below run from `examples/reference-service/`.

## The service will not start

**Symptom.** The process exits within a second of starting, with exit code
78 and `Invalid configuration:` on standard error. In compose, `app` exits
before its health check ever passes.

**Confirm.** Run the configuration check against the same environment. On a
machine with the source checked out:

```bash
just config-check
```

Inside the image, where the environment is whatever the container was
given:

```bash
docker compose run --rm app python -m reference_service.config_check
```

Both load settings exactly as the service does at startup, so they fail in
the same way it did, or they print what it would have run with.

- **Exit 78.** One line per problem, each naming the field, what is wrong
  with it, and the rule that rejected it — and never the value, because for
  `APP_DATABASE__DSN` that value holds a password:

    ```
    Invalid configuration:
      http_port: Input should be less than or equal to 65535 (less_than_equal)
    ```

- **Exit 0.** One JSON object, keys sorted, holding the configuration the
  service *would* run with. Every `SecretStr` prints as `**********`, and the
  password inside any URL — `APP_DATABASE__DSN`, `APP_CACHE__DSN` — is
  replaced the same way. Read it against what you expected: a field showing
  its default was not set where you thought, and a `null` block
  (`"database": null`) means that dependency is not configured at all and
  the in-memory fallback is in use.

**Act.** Fix the variable the message names, and run the check again before
restarting the service. Every variable is listed in
[Configuration](reference/configuration.md#variables).

!!! danger "Do not"
    Do not add a print of the raw settings to find out what the service
    saw. The exit-78 message elides the value on purpose, and `model_dump`
    prints URL passwords in clear — the check exists so that nobody needs
    to.

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

**Symptom.** The symptom differs by dependency, which is the point of this section:
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
cache and object store without gating on either. Each appears there only
when it is configured — a dependency's field is present whether that
dependency is up or down, but a service running with neither `APP_CACHE__*`
nor `APP_STORAGE__*` set returns `dependencies: {}`.

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

**Confirm.** Establish whether the release included a migration — before touching any image:

```bash
just migrate-version
```

Compare the version this prints against the previous release's
expected version.

**Act, in this order and no other.**

1. **No migration:** roll the application image back. Stop here.
2. **Migration included:** roll the application back only if the
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

## `security` is red on a pull request

**Symptom.** CI's `security` job fails. It runs one recipe per step, so
the step name says which one.

**Confirm.** The step that failed is the whole diagnosis:

| Step | What it means |
| --- | --- |
| Build both images | A plain build failure in one of the two Dockerfiles. Nothing to do with advisories. |
| Audit … lock | pip-audit found an advisory against a version pinned in `uv.lock` — the reference service's, or the documentation toolchain's at the repository root; there is one step for each. |
| Scan both images | Trivy found a HIGH or CRITICAL vulnerability with a fix available, or an embedded secret, in one of the two images. |
| Write the software bills of materials | Trivy could not write the SBOM — almost always a problem with the image or the Docker socket, not with a dependency. |

Reproduce locally with `just security`, which runs the same recipes in the
same order (the root's `just audit` aside) and needs Docker.

**Act.**

- **`audit`:** in the project whose lock was named, bump the package and
  re-run:

    ```bash
    uv lock --upgrade-package <name>
    just audit
    ```

    Commit `uv.lock`. If no fixed version exists yet, the recipe's own
    comment in the `justfile` says how to silence one advisory, with a
    reason and a date.

- **`scan`:** follow [Reading a scan failure](reference/supply-chain.md#reading-a-scan-failure)
  — bump the package or the base image, or exempt the finding through
  `.trivyignore.yaml` with a reason, a path and an expiry.

- **A finding that appeared with no related change in the pull request** is
  an advisory published overnight, and the nightly `security` job will be
  red for the same reason. It is the pull request's to fix only if the fix
  is trivial — a one-package bump that passes `just security`. Otherwise
  open an issue for it, exempt it with a short expiry so this pull request
  can merge, and let the issue own the real fix.

!!! danger "Do not"
    Do not add a skip flag, a `continue-on-error`, or an allow-list to make
    the job green. `.trivyignore.yaml` is the only exemption path, every
    entry there expires, and the nightly job re-checks the same thing — a
    silenced job is a job nobody reads ([ADR 0016](adr/0016-image-scanning-fails-on-fixed-findings-and-exemptions-expire.md)).

## A Dependabot pull request is red

**Symptom.** A weekly `build(deps)` or `ci(deps)` pull request opened by
Dependabot has a failing check.

**Confirm.** Which job failed decides which of two cases this is.

**Act, per case.**

1. **A test, lint or gate job failed.** The bump broke something. Treat it
   as any other failing pull request: check out the branch, run the failing
   recipe locally, fix the code or pin the package below the breaking
   version in `pyproject.toml` with a comment saying why. Dependabot's
   branch can be pushed to like any other.

2. **The `security` job failed on an image bump.** A new base image
   version fixed less than hoped, or introduced a new finding. Run
   `just security` on the branch and read the scan table. Two things
   change at once here: `.trivyignore.yaml` entries pinned to findings the
   new version *did* fix are no longer needed and can be dropped, and a
   finding the new version *introduced* may need a new entry, with its own
   reason and expiry. The five entries the file carries today all belong to
   the `migrate/migrate` binary, so a bump of `Dockerfile.migrations`'s
   `FROM` line is exactly this case.

!!! danger "Do not"
    Do not close a red Dependabot pull request to make it go away. Closing
    it without merging tells Dependabot to skip that version — it will not
    open the same bump again, so the vulnerable pin stays until a newer
    release appears, and the alert stays open in between.
