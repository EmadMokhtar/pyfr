---
last_reviewed: 2026-09-10
---

# 0012. Hold mypy strict on the inner layers only

**Status:** Accepted
**Date:** 2026-08-28

## Context

M0 has to settle how strictly mypy checks the codebase before more than a
handful of files exist, because a strictness level relaxed later reads as
giving up, while one tightened later means retrofitting annotations
across everything already written.

## Decision

We check `domain/` and `services/` strictly, and everything else
leniently. `pyproject.toml`'s `[tool.mypy]` table sets a lenient baseline
across the whole tree — `ignore_missing_imports = true`, plus the usual
unused-ignore and redundant-cast warnings — and one `[[tool.mypy.overrides]]`
block layers the strict checks on top for `{{ cookiecutter.package_name }}.domain.*` and
`{{ cookiecutter.package_name }}.services.*` only: `disallow_untyped_defs`,
`disallow_incomplete_defs`, `disallow_untyped_calls`,
`disallow_any_generics`, `check_untyped_defs`, `no_implicit_reexport` and
`warn_return_any`. `api/` and `infrastructure/` run under the lenient
baseline alone, with none of those checks turned on. `just check` runs
`mypy` with no `--strict` flag on the command line; the strictness lives
entirely in the overrides in configuration, not in how the tool is
invoked.

## Alternatives considered

- **Strict everywhere.** Rejected: third-party stubs in the
  infrastructure layer — the SQLAlchemy, Redis and aioboto3 clients in
  particular — are imperfect, and full strictness there produces a
  codebase of `# type: ignore` comments rather than caught bugs. That is
  worse than lenient checking, because a wall of suppression comments
  looks rigorous while catching nothing.
- **Lenient everywhere.** Rejected: the domain and services layers are
  exactly where types encode business rules — a `Money` amount that
  cannot be negative, an `Order` that cannot exist with zero lines — and
  that is precisely where strictness pays for itself by catching a
  violated invariant at type-check time instead of at runtime.

## Consequences

Type errors are caught where they carry meaning — a business rule
expressed as a type, silently weakened by a change to the model — without
demanding a stub-quality argument in every adapter that talks to a
third-party client.

The cost is an uneven rule that has to be explained to every new
contributor, since "strict here, lenient there" is not the kind of rule
that reads as obviously correct on first encounter — hence the comment
directly above the override block in `pyproject.toml`. It is also a
boundary that has to be maintained deliberately as the tree grows: a new
top-level package under `src/{{ cookiecutter.package_name }}/` gets the lenient
baseline by default unless someone remembers to add it to the override's
module list, so the strict boundary can silently fail to expand to code
that actually belongs inside it.

Full reasoning: [spec section 10.4](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
