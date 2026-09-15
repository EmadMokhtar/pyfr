---
last_reviewed: 2026-09-15
covers:
  - src/pyfr_cli/vendor.py
  - src/pyfr_cli/update.py
  - .github/workflows/release.yml
---

# 0018. The updater is a published command-line tool, and the template branch lives on the remote

**Status:** Accepted
**Date:** 2026-09-14

## Context

A generated project imports nothing from PyFr (ADR 0002; the original
specification's section 3). M8 has to put the update logic somewhere —
render the template at a newer version with the project's recorded
answers, merge the result, run a release's migration scripts — and has to
give that merge a base commit: the last state both sides agreed on.

The original specification (section 11.2) kept a `template` branch in each
project, local only, rebuilt from the repository's root commit on demand,
and left the updater's home open. Two facts decided both questions. A
squash-merged pull request discards its merge commit, so the template
commit the first update merged survives only if the branch itself was
pushed. And the logic that knows how to move a project *to* version B —
the file that moved, the setting that changed shape — is written together
with B, not with the version A the project has.

## Decision

The updater is `pyfr-cli` on PyPI: command `pyfr`, subcommands `update`
and `update-check`, run through `uvx` — `uvx --from pyfr-cli@latest pyfr
update`, which every generated project wraps as `just update`. Its version
is the template's version: one `cz bump` moves `pyproject.toml`,
`cookiecutter.json`'s `_template_version`, the git tag and the PyPI release
together, so `@latest` is the newest template tag by construction and
`just update v0.13.0` pins the tool and the target at once. `release.yml`
publishes it with PyPI Trusted Publishing (PyPI accepts a short-lived token
GitHub Actions mints for the run), so no PyPI credential is stored
anywhere.

The `template` branch lives on `origin`. Every commit the tool makes on it
carries the trailer `Pyfr-Template-Version: vX.Y.Z`; the tool fetches the
branch before an update and pushes it before merging. Because a squash
merge leaves no merge commit to descend from, the merge base is pinned
explicitly to the recorded version's template commit, through a temporary
`git replace --graft` that is removed when the run ends. M8's design
argues both halves in sections 4.3 and 4.7.

## Alternatives considered

- **A script inside each generated project.** Rejected: the script would
  be updated by the very merge it drives, so a defect in it reaches every
  project and is fixed only by the update it breaks; and a project
  generated before the script existed has no way to start. The published
  tool runs at the *target* version, so it always knows how to migrate to
  itself, and a project generated at v0.7.0 bootstraps with the same one
  line.
- **A local `template` branch rebuilt from the root commit** (the original
  section 11.2). Rejected: correct for the first update only. After a
  squash-merged first update, the second has no commit for the version the
  project now records, and rebuilding it would ask every machine's render
  to be byte-identical.
- **Copier or cruft.** Rejected in ADR 0002; nothing here reopens that.

## Consequences

- The root `pyproject.toml` is a package. `src/pyfr_cli/` is the one thing
  this repository publishes: typed with `mypy --strict`, tested in
  `tests/cli/` and by the end-to-end update test, built and run from its
  wheel in CI.
- A `docs:`-only merge releases nothing, so PyPI can trail `main` by
  documentation commits and never by a template change.
- PyPI and `uvx` are needed at update time, and only then; a generated
  service still imports nothing from PyFr.
- The `template` branch is shared state. Deleting or rewriting it costs
  one noisier merge, and the tool's messages say how to re-point it; every
  generated project carries the procedure in
  `docs/guides/update-from-template.md`.
- One manual step per fork of this repository: a pending publisher on
  pypi.org before the first release, under the fork's own package name.
