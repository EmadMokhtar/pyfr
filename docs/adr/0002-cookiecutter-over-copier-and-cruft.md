---
last_reviewed: 2026-09-10
---

# 0002. Generate with cookiecutter, not Copier or cruft

**Status:** Accepted
**Date:** 2026-08-28

## Context

PyFr generates services and must be able to send them fixes later — a
security patch to the Dockerfile, a new dashboard, a corrected retry policy
— without every generated service quietly drifting out of reach of the
template that made it. Three engines could plausibly do this: cookiecutter,
Copier and cruft.

## Decision

Generate with cookiecutter. The ability to send later fixes is not bought
from the engine at all: it is built on an ordinary git merge (M8), using a
vendor branch of pristine template output as the merge base. cookiecutter's
job stays narrow — render the template once, at creation time.

## Alternatives considered

- **cruft.** Purpose-built for exactly this, and the least code to write of
  the three. Rejected because its last release was 2024-12-25, roughly
  twenty months before this decision — too dormant to carry a long-lived
  capability that every generated service depends on for its entire life.
  It also applies patches rather than merging, so it fails on precisely the
  files every real project deletes: the worked example every team removes
  in its first week is exactly what a patch cannot be re-applied to.
- **Copier.** The healthiest of the three engines, with project updates and
  cross-version migrations built in — the feature PyFr otherwise has to
  build itself. Rejected for an ecosystem reason, not a technical one:
  Backstage, the developer portal many organisations use to create
  services from a catalogue, has no first-party Copier action. Its only
  Copier action is an unpublished third-party plugin last touched in
  February 2024. Choosing Copier would mean owning a fork of that
  TypeScript to keep portal self-service working, where cookiecutter's
  Backstage module is first-party and actively released.

## Consequences

Choosing cookiecutter means the update mechanism is not inherited from the
engine — it has to be built. M8 exists because of this decision, and it is
the single largest cost this ADR commits the project to: a vendor branch,
a three-way merge, and versioned migration scripts for the changes a merge
cannot express on its own.

In exchange, generation itself stays boring. cookiecutter is widely known,
has no update semantics to learn, and plugs into the tooling teams already
have — including Backstage, without a plugin PyFr would have to maintain.
`.pyfr-answers.yml`, the one file `post_gen_project.py` writes into every
generated repository, exists specifically to make the M8 merge possible:
without it there is no record of what was asked at creation time, and
nothing for an update to re-render against.

Full reasoning: [spec section 11.8](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
