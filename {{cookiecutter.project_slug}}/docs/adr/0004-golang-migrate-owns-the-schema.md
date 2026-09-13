---
last_reviewed: 2026-09-10
---

# 0004. Let golang-migrate own the schema

**Status:** Accepted
**Date:** 2026-09-01

## Context

A generated service needs a migration tool before M1's persistence layer
can exist at all, and that tool has to work the same way in a developer's
laptop, in CI's throwaway containers, and in a production deployment step
that should not need the whole application to run.

## Decision

We use golang-migrate, with plain `.up.sql` / `.down.sql` file pairs as
the only migration format. There is no `alembic/` directory and no
`alembic_version` table anywhere in the project — confirmed directly:
the only `alembic` on disk lives inside the service's `.venv`,
installed as a library, not as a migration tool with its own directory.

## Alternatives considered

- **Alembic.** Rejected as the migration tool itself for two reasons.
  Autogeneration produces migrations nobody reads closely, because the
  diff between two sets of SQLAlchemy models is not the same thing as a
  reviewed change to a live schema. And Alembic's migration runtime is
  Python, so running it means the migration step needs the application's
  full dependency tree; golang-migrate is one static binary in its own
  small image, with no Python interpreter and no import of service code.
- **Hand-run SQL.** Rejected: no version tracking, no reversibility, and
  no gate stopping an environment from silently missing a change or
  applying one twice.

## Consequences

Migrations are reviewable SQL files rather than generated Python, and the
migration image that runs in production is small, language-agnostic and
independent of the application image — a clean Kubernetes init container
or pre-deployment job that never imports service code.

Alembic is not gone from the project; it is kept, deliberately, as a
dev-only dependency used for exactly one job. `pyproject.toml` declares
it under `[dependency-groups] dev` with a comment stating why:
`compare_metadata()` is the comparison engine behind the model/schema
drift gate, the integration test that catches a SQLAlchemy model changed
without a matching migration. Deleting the dependency silently removes
that gate, which is why the comment is there at all — without it, the
presence of a migration library the project supposedly doesn't use reads
as a mistake waiting to be cleaned up.

The cost golang-migrate itself imposes is the **dirty** migration state: a
migration that fails partway leaves the schema_migrations table marked
dirty, and the tool refuses to proceed until a human runs `migrate force`
after confirming the database's real state by hand. That failure mode is
real, not hypothetical, which is why `docs/runbook.md` carries a worked
recovery entry for it rather than leaving it to be rediscovered during an
incident.

Full reasoning: [spec section 6.1](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
