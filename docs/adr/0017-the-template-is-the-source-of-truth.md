---
last_reviewed: 2026-09-14
covers:
  - scripts/regen.py
  - tests/reference-answers.yaml
---

# 0017. The template is the source of truth, and a golden diff proves it

**Status:** Accepted
**Date:** 2026-09-12

## Context

Phase A built `examples/reference-service/` as ordinary Python so that no
one ever debugged Jinja and Python at the same time (ADR 0002, the
original specification's section 3.3). Phase B turns that tree into the
template body, `{{cookiecutter.project_slug}}/`. From then on two trees
describe one service, and the question is which one a contributor edits and
what stops the other from drifting.

## Decision

The template body is the only source of truth from the first M7 pull
request. `examples/reference-service/` is rendered from it by
`scripts/regen.py` with the fixed answers in `tests/reference-answers.yaml`,
under `PYFR_REGEN` so the render has no side effects, and is committed as
output. `just regen-check` — the `golden` CI job and `tests/test_golden.py` —
fails when the render and the committed example differ by a byte.

One file is outside the comparison: `uv.lock`. A lock is resolver output
for one dependency set, and pruning produces eight; it cannot be a Jinja
document. The example's lock is kept and checked against its regenerated
`pyproject.toml` by `uv lock --check`.

Dependabot edits the rendered example because it cannot parse Jinja. `just
adopt` copies each changed line back into the template file that renders
it; a change that is not a line-for-line replacement is refused and made by
hand.

## Alternatives considered

- **Keep the example hand-maintained and add the golden diff only at the
  end of M7.** Rejected: leaves four pull requests in which the trees can
  disagree with nothing enforcing agreement.
- **Derive the template from the example mechanically.** Rejected: cannot
  express pruning or the `{% raw %}` guards.

## Consequences

- Contributors edit `{{cookiecutter.project_slug}}/` and run `just regen`;
  a hand edit to the example fails the build with the file named.
- Every pull request that touches the template shows its effect on the
  example as an ordinary file diff.
- The example's `git blame` restarts at this decision; the history of its
  files continues in the template body, where `git mv` carried it.
- `just adopt` serves three round trips, not one: Dependabot's pin changes,
  and the generated files (`openapi.json`, `.env.example`, the
  configuration reference) whose generators run in the example and whose
  replaced lines are carried back into the template the same way; and the
  root workflows' action pins, which Dependabot can bump only there, are
  copied into the template's workflows.
- `ruff`, `mypy` and `import-linter` cannot run on the template body. They
  run on the example on every push, and — from PR 5 — on three sampled
  renders on merge.
- The documentation follows the same rule: pages about the service live in
  the template body and are rendered into the example's `docs/`; PyFr's
  own site links to that render as the documentation every generated
  project ships.
