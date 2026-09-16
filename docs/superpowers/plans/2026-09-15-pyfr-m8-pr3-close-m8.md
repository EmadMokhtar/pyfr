# M8 PR 3 — Close M8 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close milestone M8 on `main`: record the decision (ADR 0018), bring the root documentation to "M0–M8 done", amend the master spec, verify the weekly workflow's conflict, stop and Workflows-permission paths live on `EmadMokhtar/pyfr-m8-verify` against the real `v0.12.0`, and open the PR that closes issue #51.

**Architecture:** A documentation-only pull request (`docs: close m8`), which releases nothing by itself — `release.yml` treats Commitizen's "no bump" exits as a no-op. Every root page that says M8 is "next" or "to go" is rewritten in the present tense; the contributing guide gains the two sections the M8 spec promised (working on `pyfr-cli`, writing a migration script); the live verification happens on the throwaway repository and its results go into the PR body and a short note in the M8 spec. Only a defect found by the verification would add a `fix:` commit (and make the merge a patch release).

**Tech Stack:** MkDocs (`mkdocs build --strict`), the repository's `just check` gate, `gh api` (REST — the GraphQL commands time out from this machine), `uvx --from pyfr-cli`.

**Spec:** `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md` — sections 1 (definition of done, items 4 and 5), 7.2 (root side), 8.5 (not tested automatically), 9 (PR 3 row), 13 (departures from the master spec). Read those sections before starting.

## Global Constraints

Copied from the spec and the repository's rules; every task inherits them.

- Work only in the worktree `/Users/emadmokhtar/Projects/pyfr/.claude/worktrees/m1-work-5c1a84`, on branch `claude/m8-pr3-close-m8` (already created from `origin/main` at `dc7a2d6`, `bump: version 0.11.0 → 0.12.0`). Never `cd` to the primary checkout. Never run bare `git stash`.
- Conventional Commits for every commit; imperative mood, lowercase, no trailing period. Every commit message ends with a blank line and `Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>`. Commit bodies explain *why*, in simple English, no idioms.
- Nothing under `{{cookiecutter.project_slug}}/` changes in this PR. If a task finds it must, stop and report — that would move the PR from `docs:` to `fix:`/`feat:` and release.
- Root documentation pages carry `last_reviewed:` front matter; every page a task edits gets `last_reviewed: 2026-09-15`. Decision records are the exception: their `last_reviewed` is set once, when written, and the record is never edited afterwards.
- Every new page must be in `mkdocs.yml`'s `nav:` (`tests/test_site_nav.py` fails otherwise) and `mkdocs build --strict` must pass — `just docs-build` builds both sites and runs `scripts/check_site_links.py`.
- Pushes go over HTTPS with `gh`'s token: `git -c credential.helper='!gh auth git-credential' push https://github.com/EmadMokhtar/pyfr.git claude/m8-pr3-close-m8`. SSH pushes fail from this session (1Password's agent cannot prompt).
- GitHub calls use `gh api` (REST). `gh pr create` / `gh pr view` use GraphQL and often fail with "TLS handshake timeout" here; retry once, then fall back to REST.
- The PR: title `docs: close m8`, body ends with `Closes #51` and then `🤖 Generated with [Claude Code](https://claude.com/claude-code)`; assignee `EmadMokhtar` (bare login, no `@`); verify the assignee and the issue link after creating.
- `EmadMokhtar/pyfr-m8-verify` is the user's throwaway repository. Never delete it, its branches, or its history without the user's explicit answer. Closing its issues and merging its own pull requests is part of the verification and is fine.
- Language rules for every page edited: expand an acronym on first use, define a technical term in place, short sentences, no idioms or sports/military metaphors.

---

## File structure

| File | Task | Responsibility |
| --- | --- | --- |
| `docs/adr/0018-the-updater-is-a-published-cli.md` (create) | 1 | Decisions M8-1 and M8-3 as a decision record |
| `mkdocs.yml` (modify, nav) | 1 | Makes the record reachable |
| `docs/contributing.md` (modify) | 2 | Layout, the package paragraph, the generated `.github/` list, two new sections, the one-time settings, the commands table |
| `docs/roadmap.md`, `docs/index.md`, `README.md`, `docs/getting-started.md`, `docs/glossary.md`, `docs/explanation/why-a-template.md` (modify) | 3 | "M0–M8 done" everywhere; `just update` named where the reader meets `.pyfr-answers.yml` |
| `docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md` (modify, section 11.2) | 4 | The amendment note the M8 spec promised |
| GitHub: PR `docs: close m8` | 5 | The deliverable; `Closes #51` |
| GitHub: `EmadMokhtar/pyfr-m8-verify` runs; `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md` section 8.5 (modify) | 6 | Live verification and its record |
| GitHub: one follow-up issue on `EmadMokhtar/pyfr` | 7 | The two enhancements deferred from PR 2, plus anything task 6 turns up |

Tasks 1–4 are independent of each other and of the network. Task 5 needs 1–4. Task 6 needs `pyfr-cli 0.12.0` on PyPI (check first: `curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/pyfr-cli/0.12.0/json` must print `200`) and one action by the user (a secret). Task 7 needs 6.

---

### Task 1: ADR 0018

**Files:**
- Create: `docs/adr/0018-the-updater-is-a-published-cli.md`
- Modify: `mkdocs.yml` (the `Decision records` nav list, after the `0017` line)
- Test: `tests/test_site_nav.py`, `just docs-build`

**Interfaces:**
- Consumes: nothing.
- Produces: the page path `adr/0018-the-updater-is-a-published-cli.md`, linked from Task 2 (`docs/contributing.md`) and Task 3 (`docs/roadmap.md`).

Background for the implementer: an ADR (architecture decision record) is a short page that records one decision, the context that forced it, the alternatives, and the consequences. `docs/adr/README.md` explains the rules: the numbering is shared with the generated project's records (its highest is 0016; the root has 0017), records are never edited once accepted, and each record links the spec section that argues it. `docs/adr/0017-the-template-is-the-source-of-truth.md` is the model to match in tone and length.

- [ ] **Step 1: Write the record**

Create `docs/adr/0018-the-updater-is-a-published-cli.md` with exactly this content:

````markdown
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
````

- [ ] **Step 2: Add the nav entry**

In `mkdocs.yml`, directly after the line
`      - 0017 The template is the source of truth: adr/0017-the-template-is-the-source-of-truth.md`
add:

```yaml
      - 0018 The updater is a published CLI: adr/0018-the-updater-is-a-published-cli.md
```

Same indentation as the 0017 line (six spaces, then `- `).

- [ ] **Step 3: Check the page is reachable and the site builds**

Run (from the worktree root):

```bash
uv run --group dev --group docs pytest tests/test_site_nav.py -q && just docs-build 2>&1 | tail -3
```

`pytest tests/test_site_nav.py` checks every page under `docs/` is in the nav. `just docs-build` builds both documentation sites with `--strict` (any warning fails) and checks every link between them.

Expected: `passed`; the build ends with `Every cross-site link resolves in the built site; every repository link names a path in the checkout.`

- [ ] **Step 4: Commit**

```bash
git add docs/adr/0018-the-updater-is-a-published-cli.md mkdocs.yml
git commit -F - <<'EOF'
docs(adr): record that the updater is a published cli on a remote template branch

ADR 0018 records decisions M8-1 and M8-3 of the M8 design: pyfr-cli on
PyPI, run at the target version, and the template branch pushed to
origin so a squash-merged first update leaves the second a merge base.

Refs #51

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 2: The root contributing guide

**Files:**
- Modify: `docs/contributing.md` — six places, named below by the exact text to find.
- Test: `just docs-build`

**Interfaces:**
- Consumes: the ADR path from Task 1 (`adr/0018-the-updater-is-a-published-cli.md`).
- Produces: the anchors `#working-on-pyfr-cli` and `#writing-a-migration-script` (MkDocs derives anchors from headings: lowercase, spaces to hyphens, backticks dropped).

Background: `docs/contributing.md` still describes the root as "not a package and nothing is published from it" — true until PR 1 of M8 made the root `pyproject.toml` the `pyfr-cli` package. The M8 spec, section 7.2, asks this page for two things: how to write a migration script (spec section 6; the contract is `updates/README.md`), and the `pyfr-cli` package — where it lives, how it is tested, how it is released.

- [ ] **Step 1: Front matter**

Change `last_reviewed: 2026-09-14` at the top of the file to `last_reviewed: 2026-09-15`.

- [ ] **Step 2: The layout block**

In the fenced block under `## Repository layout`, make these replacements:

Replace
```
  tests/                       PyFr's own tests: the hooks, the render, the golden diff
```
with
```
  src/pyfr_cli/                the updater a generated project runs: `pyfr update`, `pyfr update-check`
  updates/                     migration scripts, one directory per template release that needs one
  tests/                       PyFr's own tests: the hooks, the render, the golden diff, pyfr-cli
```

Replace
```
  .github/workflows/           continuous integration, the full suite, publishing
```
with
```
  .github/workflows/           continuous integration, the full suite, publishing (GHCR and PyPI)
```

- [ ] **Step 3: The "not a package" paragraph**

Find the sentence (one paragraph, wrapped over several lines):

```
The root project holds the documentation toolchain and the
template toolchain — cookiecutter, the hooks' and generation tests, the
regeneration script; it is not a package and nothing is published from it.
```

Replace it with:

```
The root project holds the documentation toolchain, the template
toolchain — cookiecutter, the hooks' and generation tests, the
regeneration script — and one package: `pyfr-cli`, the updater a generated
project runs as `just update`, published to PyPI by every release
([Working on `pyfr-cli`](#working-on-pyfr-cli)).
```

- [ ] **Step 4: The generated `.github/` list**

Find:
```
The template also ships a generated project's `.github/` — `ci.yml`,
`nightly.yml`, `release.yml`, `docs.yml` and `dependabot.yml`. In this
```
Replace with:
```
The template also ships a generated project's `.github/` — `ci.yml`,
`nightly.yml`, `release.yml`, `docs.yml`, `template-update.yml` and
`dependabot.yml`. In this
```

- [ ] **Step 5: The two new sections**

Insert the following immediately before the line `## Working on the documentation` (so it closes the "Working on the template" part of the page):

````markdown
## Working on `pyfr-cli`

`src/pyfr_cli/` is the updater every generated project runs as `just
update` — `uvx --from pyfr-cli@latest pyfr update` — and the one package
this repository publishes. The design is the M8 specification in
[`docs/superpowers/specs/`](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md);
the decision is [ADR 0018](adr/0018-the-updater-is-a-published-cli.md).

Three things about it differ from the rest of the root tooling:

- **Its version is the template's.** `pyproject.toml`'s `version`,
  `cookiecutter.json`'s `_template_version` and the git tag move together
  in `cz bump`, and `release.yml`'s `publish-pypi` job uploads the wheel
  with PyPI Trusted Publishing once the tag is pushed. Never edit the
  version by hand and never publish by hand: `just update` relies on the
  newest release on PyPI being the newest template tag.
- **It is typed and tested harder than the tooling.** `just typecheck`
  runs `mypy --strict` over it and is part of `just lint`; `tests/cli/`
  holds its unit tests; `tests/test_update_e2e.py` builds a two-version
  template in a temporary directory and runs real updates through it,
  with no network. `just wheel` builds the wheel and runs `pyfr --version`
  from it, as CI's `docs` job does.
- **It must work for every version a project can record.** A project
  generated at v0.7.0 has an answers file and nothing else. The tool
  installs `.pyfr-update-ignore` when it is missing, and every error
  message points at the guide each project carries,
  `docs/guides/update-from-template.md`. When you change what the tool
  needs from a project, the end-to-end test's oldest scenario is the one
  to extend first.

### Writing a migration script

Most template changes reach a project through the merge. A change a merge
cannot express — a file that moves, a setting that changes shape — ships a
script under `updates/<version>/`, where `<version>` is the tag of the
release that needs it: `before.py` runs on the project's tree before the
merge, `after.py` after the merge is committed. Either may be absent.
[`updates/README.md`](https://github.com/EmadMokhtar/pyfr/blob/main/updates/README.md)
is the contract; in short:

- **Standard library only.** The scripts run with `uv run --no-project
  python`, so nothing from the project's environment is installed first.
- **Idempotent** — running twice equals running once. A failed update is
  re-run, and a script that already did its work exits 0 without doing it
  again. Check before you act.
- `before.py` moves things so the merge lines up (`git mv` through
  `subprocess`); `after.py` rewrites contents once the template's version
  of a file is in place. The tool commits what each leaves — `git add`
  any file you create, because the commit stages tracked files only.
- **Exit non-zero to stop the update.** Whatever the script writes to
  stderr is shown to the user.
- **A deleted file is not an error.** Teams delete example files; a script
  that finds its target missing exits 0.

Test one the way `tests/test_update_e2e.py` tests its fixture scripts:
generate at the previous version, edit the project the way a team would,
update, assert the tree. `updates/` sits outside the template body, so a
script is never rendered into a project.

````

(Keep the blank line after the section so the following `## Working on the documentation` heading is separated.)

- [ ] **Step 6: The one-time settings**

Find:
```
Seven settings live in the GitHub interface, not in this repository, so they
are easy to miss when standing up a fork.
```
Replace with:
```
Seven settings live in the GitHub interface and one on pypi.org, not in
this repository, so they are easy to miss when standing up a fork.
```

Then, after the last bullet of that list (the one that starts `- **Enable Dependabot alerts and Dependabot security updates.**` and ends `the next weekly run.`), add this bullet:

```
- **A pending publisher on pypi.org for `pyfr-cli`, before the first
  release.** Project `pyfr-cli`, owner `EmadMokhtar`, repository `pyfr`,
  workflow `release.yml`, no environment. `release.yml`'s `publish-pypi`
  job uploads with Trusted Publishing — PyPI accepts a short-lived token
  GitHub mints for the run — so no PyPI token is stored. Without the
  publisher that job fails and every other release job still succeeds; it
  runs last and nothing depends on it. A fork publishes under its own
  package name, or not at all: `pyfr-cli` is this repository's.
```

- [ ] **Step 7: The commands table**

Replace the `just test` row's first sentence. Find:
```
| `just test` | This repository's own tests (`tests/`) — the hooks' tests, the generation-test matrix that renders all eight backend combinations and checks each one, `scripts/regen.py`'s tests and the golden diff — with both
```
Replace with:
```
| `just test` | This repository's own tests (`tests/`) — the hooks' tests, the generation-test matrix that renders all eight backend combinations and checks each one, `scripts/regen.py`'s tests, the golden diff, `pyfr-cli`'s unit tests (`tests/cli/`) and the end-to-end update test — with both
```

Replace the `just lint` row:
```
| `just lint` | `ruff check` and `ruff format --check` over the root's own Python: `hooks/`, `scripts/`, `tests/`. The template body is excluded; the example is linted by its own `just lint`. |
```
with:
```
| `just lint` | `just typecheck`, then `ruff check` and `ruff format --check` over the root's own Python: `hooks/`, `scripts/`, `src/`, `tests/`. The template body is excluded; the example is linted by its own `just lint`. |
| `just typecheck` | `mypy --strict` over `src/pyfr_cli/`, the one package this repository publishes. Part of `just lint` and of `just check`. |
| `just wheel` | Build the `pyfr-cli` wheel and run `pyfr --version` from it, exactly as CI's `docs` job does; the version it prints must be `pyproject.toml`'s. Needs the network. |
```

Replace the `just check` row:
```
| `just check` | `docs-build`, `test` and `regen-check` — everything CI's `docs` job checks at the repository level. Run before pushing a documentation, template or repository-tooling change. |
```
with:
```
| `just check` | `docs-build`, `typecheck`, `test` and `regen-check` — everything CI checks at the repository level without Docker. Run before pushing a documentation, template, `pyfr-cli` or repository-tooling change. |
```

- [ ] **Step 8: Check the CI job name used above**

Run: `awk '/^  docs:$/,/^  docs-freshness:$/' .github/workflows/ci.yml | grep -c "just wheel"`

Expected: `1` — the `docs` job (its id is `docs`, kept for the branch ruleset; its comment says it also type-checks and builds the wheel) runs `just wheel`. If it prints `0`, find the job with `grep -n "just wheel" -B 40 .github/workflows/ci.yml | grep "^[0-9]*-  [a-z-]*:$" | tail -1` and use that name in the two places Step 5 and Step 7 mention `docs`.

- [ ] **Step 9: Build**

Run: `just docs-build 2>&1 | tail -3`

Expected: the build ends with `Every cross-site link resolves in the built site; every repository link names a path in the checkout.` A failure naming `#working-on-pyfr-cli` means the heading's anchor differs — run `grep -o 'id="working-on[^"]*"' site/contributing/index.html` and use the id it prints.

- [ ] **Step 10: Commit**

```bash
git add docs/contributing.md
git commit -F - <<'EOF'
docs: describe working on pyfr-cli and writing a migration script

The contributing guide still called the root "not a package". Since M8
the root pyproject.toml is pyfr-cli, published to PyPI by every release,
with its own type check, unit tests, end-to-end test and wheel step. The
migration-script contract lives in updates/README.md; this page now
summarises it and says how to test one.

Refs #51

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 3: "M0–M8 done" on every root page

**Files:**
- Modify: `docs/roadmap.md`, `docs/index.md`, `README.md`, `docs/getting-started.md`, `docs/glossary.md`, `docs/explanation/why-a-template.md`
- Test: `just docs-build`

**Interfaces:**
- Consumes: the ADR path from Task 1.
- Produces: nothing other tasks read.

Every edit below is "find this exact text, replace with this exact text". Front matter: set `last_reviewed: 2026-09-15` in each of the five `docs/` pages (the README has none).

- [ ] **Step 1: `docs/roadmap.md`**

Find:
```
**M0, M1, M2, M3, M4, M5, M6 and M7 are done; M8 is next.** Everything on this site describes code that exists today.
```
Replace with:
```
**All nine milestones, M0 through M8, are done.** Everything on this site describes code that exists today.
```

Find the M8 table row:
```
| **M8** | Template updates | Planned | A generated project can pull in later template versions through a git merge, with a weekly job that opens a pull request when one is available. |
```
Replace with:
```
| **M8** | Template updates | **Done** | A generated project pulls later template versions into itself through a git merge. `just update` runs the published `pyfr-cli` at the target version: it re-renders the template with the project's recorded answers onto a `template` branch kept on the remote, merges it with the base pinned to the recorded version's commit — so a squash-merged first update leaves the second a correct base — and runs a release's migration scripts before and after. `.pyfr-update-ignore`, in gitignore syntax, names the paths the team owns and the merge never touches; files the team deleted stay deleted. Every generated project carries `.github/workflows/template-update.yml`, which runs the update each Monday and opens a pull request with the template's changelog on a clean merge, or an issue naming the conflicting files otherwise, and a guide, *Update from the template*, with the conflict procedure. Delivered in three pull requests: `pyfr-cli` on PyPI with Trusted Publishing (v0.11.0), the generated project's side (v0.12.0), and the closing documentation with ADR 0018. |
```

Find:
```
**Phase C** (after M7, permanently) keeps the two in step forever after.
```
Replace with:
```
**Phase C** (M8, then permanently) keeps the two in step forever after: the
template stays the source of truth, the reference service is regenerated
from it, and a generated project pulls later template versions into itself
with `just update` (ADR 0018).
```

- [ ] **Step 2: `docs/index.md`**

Find: `!!! note "Status: M0–M7 done, M8 to go"` → replace with: `!!! note "Status: M0–M8 done"`

Find:
```
    generated for real and run through their own `just check-all`. M8 —
    template updates for generated projects — is next.
```
Replace with:
```
    generated for real and run through their own `just check-all`. M8,
    template updates, is complete too: `just update` pulls a later
    template version into a generated project through an ordinary git
    merge, and a weekly workflow in every generated project opens the
    pull request for it.
```

Find:
```
    Phase B (M7) converted it into the template. Phase C keeps the two in
    step forever after.
```
Replace with:
```
    Phase B (M7) converted it into the template. Phase C (M8, then
    permanently) keeps the two in step forever after.
```

Find:
```
already generated — and M8 removes it: a generated project pulls later
```
Replace with:
```
already generated — and M8 removed it: a generated project pulls later
```

- [ ] **Step 3: `README.md`**

Find:
```
no runtime dependency on us, and nothing to lock you in. From M8, a generated
project will still be able to pull later template fixes into itself through an
ordinary `git merge`.
```
Replace with:
```
no runtime dependency on us, and nothing to lock you in. A generated project
still receives later template fixes: `just update` pulls them into itself
through an ordinary `git merge`.
```

Find: `## ✅ Status: M0–M7 done, M8 to go` → replace with: `## ✅ Status: M0–M8 done`

Find:
```
a generated project its own workflows and its own documentation site
about itself, and records the template version it came from. See the
[roadmap](https://emadmokhtar.github.io/pyfr/roadmap/) for what each
milestone delivered.
```
Replace with:
```
a generated project its own workflows and its own documentation site
about itself, and records the template version it came from. M8, template
updates, is complete too: `just update` pulls a later template version
into a generated project through a git merge, and a weekly workflow opens
the pull request for it. See the
[roadmap](https://emadmokhtar.github.io/pyfr/roadmap/) for what each
milestone delivered.
```

Find: `| **C** | M8+ | Keep the two in step, forever |`
Replace with: `| **C** | M8, then forever | Keep the two in step: the template stays the source of truth, and a generated project pulls later versions into itself 🔁 |`

Find:
```
**M0 through M7 — the reference service and its conversion into a
template — are complete. M8, template updates for generated projects, is
next.** See the [roadmap](https://emadmokhtar.github.io/pyfr/roadmap/)
for what ships when.
```
Replace with:
```
**M0 through M8 — the reference service, its conversion into a template,
and template updates for generated projects — are complete.** See the
[roadmap](https://emadmokhtar.github.io/pyfr/roadmap/) for what each
milestone delivered.
```

- [ ] **Step 4: `docs/getting-started.md`**

Find:
```
together with the template version they were rendered from. Keep it
committed and unedited: M8's template updates read it.
```
Replace with:
```
together with the template version they were rendered from. Keep it
committed and unedited: `just update` reads it ([Updating
later](#updating-later)).
```

Then insert this section immediately before the final paragraph that starts `**How PyFr itself is built**`:

```markdown
## Updating later

A generated project is yours, and it still receives later template
versions. `just update` re-renders the template at the newest release with
the answers in `.pyfr-answers.yml` and merges the result into your branch
through an ordinary git merge: your edits survive, files you deleted stay
deleted, and paths listed in `.pyfr-update-ignore` are never touched. The
project's `.github/workflows/template-update.yml` runs the same update
every Monday and opens a pull request when there is something to merge, or
an issue naming the files when the merge conflicts. The project's own
guide, *Update from the template* — published for the reference service at
<https://emadmokhtar.github.io/pyfr/reference-service/guides/update-from-template/>
— has the details and the conflict procedure.

```

- [ ] **Step 5: `docs/glossary.md`**

The table is alphabetical. Make these changes:

After the `| Merge base | ...` row, add:
```
| Migration script | A `before.py` or `after.py` under `updates/<version>/` in this repository, run by `pyfr update` around the merge for a template change a merge cannot express — a moved file, a setting that changed shape. Standard library only; must be safe to run twice. |
```

Find the `.pyfr-answers.yml` row's ending `M8's template updates read it. Kept committed and` and replace those words with `` `just update` reads it. Kept committed and `` (leave the rest of the row as it is).

After the `.pyfr-answers.yml` row, add:
```
| `pyfr-cli` | The updater a generated project runs as `just update`: a Python package on PyPI, command `pyfr`, run through `uvx` at the target template version. Its version is the template's, and it is the one package this repository publishes (ADR 0018). |
| `.pyfr-update-ignore` | A file in every generated project, in gitignore syntax, naming the paths `just update` never touches — the ones the team rewrites. A project without it uses the built-in default for its answers. |
```

After the `| Three-way merge | ...` row, add:
```
| Trusted Publishing | PyPI accepting a short-lived OpenID Connect token — a signed statement of identity — that GitHub Actions mints for one workflow run, instead of a stored PyPI password or token. How `release.yml` publishes `pyfr-cli`. |
```

Replace the `Vendor branch` row:
```
| Vendor branch | A branch holding pristine upstream output and nothing else, merged in to receive upstream changes. How M8's template updates work. |
```
with:
```
| Vendor branch | A branch holding pristine upstream output and nothing else, merged in to receive upstream changes. The `template` branch in every generated project, kept on the remote so the second update has the first's commit as its base (ADR 0018). |
```

- [ ] **Step 6: `docs/explanation/why-a-template.md`**

Find:
```
M8 makes a generated project able to pull in later template versions through
an ordinary git merge.
```
Replace with:
```
A generated project pulls in later template versions through an ordinary
git merge — `just update`, delivered in M8 and recorded in ADR 0018.
```

- [ ] **Step 7: Nothing left says M8 is pending**

Run:
```bash
grep -rn -i "M8 to go\|M8 is next\|M8 —\|M8 -\|From M8\|M8 removes\|M8 makes\|M8's template updates\|M0–M7 done" README.md docs --include='*.md' --exclude-dir=superpowers
```
Expected: no output. Any line printed is a stale mention — fix it in the same present-tense style and re-run.

- [ ] **Step 8: Build**

Run: `just docs-build 2>&1 | tail -3`

Expected: ends with `Every cross-site link resolves in the built site; every repository link names a path in the checkout.` (The new `<https://emadmokhtar.github.io/pyfr/reference-service/guides/update-from-template/>` link is a cross-site link the script resolves against the built tree; the guide exists in the example's docs.)

- [ ] **Step 9: Commit**

```bash
git add docs/roadmap.md docs/index.md README.md docs/getting-started.md docs/glossary.md docs/explanation/why-a-template.md
git commit -F - <<'EOF'
docs: say m0 through m8 are done

The roadmap, the site's front page, the README, the getting-started page
and the explanation page all said M8 was next. It shipped in v0.11.0 and
v0.12.0. Getting started now tells a new user what `just update` does,
and the glossary defines pyfr-cli, .pyfr-update-ignore, migration script
and Trusted Publishing.

Refs #51

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 4: The master spec's amendment note

**Files:**
- Modify: `docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md` (section 11.2)
- Test: none automated — `docs/superpowers/` is excluded from the site build. Check by reading.

**Interfaces:** none.

Background: the original design ("master spec") says in section 11.2 that the `template` branch is local and rebuilt from the root commit. M8's design departs from that (its section 13 lists every departure) and promises, in section 7.2, "a short amendment note at the top of section 11.2 pointing here".

- [ ] **Step 1: Insert the note**

Find the heading line `### 11.2 The template branch` and the blank line after it. Insert, after that blank line and before the paragraph starting `An update is a three-way merge`:

```markdown
> **Amended by M8 (2026-09-14).** The branch is not local-only. It lives on
> `origin`, and the updater fetches it before an update and pushes it before
> merging: a squash-merged update pull request discards the merge commit, so
> the second update needs the first's template commit kept alive on the
> remote, and the merge base is pinned to it explicitly. The reconstruction
> from the root commit below holds for the *first* update only. See
> [`2026-09-14-pyfr-m8-template-updates-design.md`](2026-09-14-pyfr-m8-template-updates-design.md),
> sections 4.3 and 4.7; its section 13 lists every departure from this
> section 11, including the `PYFR_REGEN` name, the default ignore list, how
> migration scripts run, and the updater itself (`pyfr-cli`, ADR 0018).

```

(Blank line after the quote block, so the original paragraph stays separate.)

- [ ] **Step 2: Read it back**

Run: `sed -n '/^### 11.2 The template branch/,/^An update is a three-way merge/p' docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md`

Expected: the heading, a blank line, the ten quoted lines, a blank line, then `An update is a three-way merge, which needs a **merge base**...`.

- [ ] **Step 3: Commit**

```bash
git add docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md
git commit -F - <<'EOF'
docs(pyfr): note in the master spec that the template branch lives on the remote

Section 11.2 described a local branch rebuilt from the root commit. M8
moved it to origin (its design, sections 4.3 and 13); the note points
readers of the original design at the amended one.

Refs #51

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
```

---

### Task 5: Open the pull request

**Files:** none in the repository.

**Interfaces:**
- Consumes: Tasks 1–4 committed on `claude/m8-pr3-close-m8`.
- Produces: the PR number, used by Task 6 (to report results) and Task 7 (to cross-link).

- [ ] **Step 1: Full gate**

Run: `just check 2>&1 | tail -5`

`just check` builds both sites, type-checks `pyfr-cli`, runs the repository's tests and the golden diff.

Expected: `294 passed` (plus deselected), `Success: no issues found`, `examples/reference-service matches the template.` Nothing in this PR changes tests or the template, so the numbers match `main`.

- [ ] **Step 2: Push**

`git -c credential.helper='!gh auth git-credential' push …` pushes over HTTPS using `gh`'s stored token for this one command only.

```bash
git -c credential.helper='!gh auth git-credential' push -u https://github.com/EmadMokhtar/pyfr.git claude/m8-pr3-close-m8
```

- [ ] **Step 3: Write the body**

Write `/private/tmp/claude-501/-Users-emadmokhtar-Projects-pyfr--claude-worktrees-m1-work-5c1a84/86219545-f7dc-4115-aedb-2fd16ee8def7/scratchpad/pr3-body.md`:

```markdown
## Summary

Closes milestone M8, template updates for generated projects. Documentation only: nothing under `{{cookiecutter.project_slug}}/` or `src/pyfr_cli/` changes, so this merge releases nothing.

- **ADR 0018** records decisions M8-1 and M8-3: the updater is `pyfr-cli` on PyPI, run at the target version; the `template` branch lives on the remote so a squash-merged first update leaves the second a merge base.
- **`docs/contributing.md`** gains *Working on `pyfr-cli`* (version, tests, release) and *Writing a migration script* (the `updates/` contract in short); the layout block, the generated `.github/` list, the one-time settings (the pypi.org publisher) and the commands table (`just typecheck`, `just wheel`) catch up with M8.
- **Roadmap, front page, README, getting started, glossary, explanation:** "M0–M8 done"; `just update` named where a reader meets `.pyfr-answers.yml`; glossary rows for `pyfr-cli`, `.pyfr-update-ignore`, migration script and Trusted Publishing.
- **Master spec 11.2** carries the amendment note the M8 design promised.

## Live verification (spec 8.5)

_Filled in by the verification task — see the comments below._

## Test plan

- [x] `just check` — both sites build with `--strict`, links resolve, `mypy --strict`, 294 tests, golden diff clean
- [ ] Weekly workflow on `EmadMokhtar/pyfr-m8-verify`, `v0.11.0 -> v0.12.0` (a workflow-changing update): push refused without `RELEASE_TOKEN`, with the Workflows-permission annotation; conflict → issue; issue exists → stop; clean → pull request with CI running

Closes #51

🤖 Generated with [Claude Code](https://claude.com/claude-code)
```

- [ ] **Step 4: Create, assign, verify**

REST, because GraphQL times out from this machine:

```bash
gh api --method POST repos/EmadMokhtar/pyfr/pulls -f title='docs: close m8' -f head=claude/m8-pr3-close-m8 -f base=main -F body=@/private/tmp/claude-501/-Users-emadmokhtar-Projects-pyfr--claude-worktrees-m1-work-5c1a84/86219545-f7dc-4115-aedb-2fd16ee8def7/scratchpad/pr3-body.md --jq '.number, .html_url'
```

Then, with the number it printed as `N`:

```bash
gh api --method POST repos/EmadMokhtar/pyfr/issues/N/assignees -f 'assignees[]=EmadMokhtar' --jq '.assignees[].login'
gh pr view N --json closingIssuesReferences --jq '.closingIssuesReferences[].number'
```

Expected: `EmadMokhtar`; `51`. If the second command times out, retry once; if it still fails, open `https://github.com/EmadMokhtar/pyfr/pull/N` in the browser and confirm the "Development" side panel lists #51.

- [ ] **Step 5: Bind the PR to the session** (desktop app): call `mcp__ccd_pr__bind_pr` with the PR URL so CI failures wake the session.

---

### Task 6: Live verification on `EmadMokhtar/pyfr-m8-verify`

**Files:**
- Modify (at the end): `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md`, section 8.5 — one verification note.
- Work area: a clone of the verify repository in the scratchpad directory, `/private/tmp/claude-501/-Users-emadmokhtar-Projects-pyfr--claude-worktrees-m1-work-5c1a84/86219545-f7dc-4115-aedb-2fd16ee8def7/scratchpad/verify`.

**Interfaces:**
- Consumes: PR number `N` from Task 5; `pyfr-cli 0.12.0` on PyPI.
- Produces: run ids, issue and PR numbers on the verify repository, reported in a comment on PR `N` and in the spec note; possibly follow-up items for Task 7.

Background. The verify repository was generated at `v0.10.0` during PR 2. Its state now: `main` records `_template_version: "0.10.0"` and carries a hand-copied, slightly older `template-update.yml`; PR #1 there (`chore: update template v0.10.0 -> v0.11.0`, branch `pyfr/update-v0.11.0`) is open and unmerged; the `template` branch on its remote is at the `v0.11.0` template commit; it has no `RELEASE_TOKEN`. The `v0.11.0 -> v0.12.0` template change touches `.github/workflows/release.yml` and adds `.github/workflows/template-update.yml`, so every push of it needs the **Workflows** permission — which is exactly the case PR 2 could not verify.

What the workflow does on a conflict, in order: runs the update (`exit 1`, merge aborted), pushes `template:template`, then opens the issue. A step that fails skips the steps after it, so without `RELEASE_TOKEN` a workflow-changing update fails at the push — clean or conflicted — before any issue or pull request. That fixes the order below: first the refused push (no secret), then the user adds the secret, then conflict → issue, stop, and clean → pull request.

Scenarios and expected results:

| # | State | Expected |
| --- | --- | --- |
| A | No `RELEASE_TOKEN`; `README.md` edited on the line the template rewrites | Update runs (`.pyfr-update-ignore` installed; `conflict: README.md` in the log; merge aborted); push of `template:template` refused; the push step fails with the `::error::` annotation naming the Workflows permission; no issue, no pull request |
| B | `RELEASE_TOKEN` (Contents, Pull requests, Issues, Workflows) added by the user; same edit | `template` pushed to `v0.12.0`; issue `chore: template v0.11.0 -> v0.12.0 conflicts` opened, body lists `` `README.md` `` only; no pull request; job green |
| C | Same, dispatched again | The "Stop when…" step finds the open issue, prints `v0.12.0 already has an open pull request or issue; nothing to do.`, the update step is skipped; no second issue; job green |
| D | Issue closed; edit reverted | Update runs from the pushed `template` tip (log: the sync is skipped because the tip already records `v0.12.0`); clean merge; both pushes succeed; PR `chore: update template v0.11.0 -> v0.12.0` opens with the changelog body; **no** "CI has not run" comment; the project's `ci.yml` and `docs.yml` runs start on the PR (a personal access token's events start workflows) |

- [ ] **Step 1: Confirm PyPI has 0.12.0**

```bash
curl -s -o /dev/null -w '%{http_code}\n' https://pypi.org/pypi/pyfr-cli/0.12.0/json
```
Expected: `200`. If `404`, the `Release` run on `main` has not finished: `gh api repos/EmadMokhtar/pyfr/actions/runs --jq '.workflow_runs[] | select(.name == "Release") | "\(.status) \(.conclusion) \(.id)"' | head -1` — wait for `completed success`, then re-check.

- [ ] **Step 2: Merge the verify repository's PR #1 by squash and delete its branch**

This brings its `main` to `v0.11.0` the way a team would, so the run below is the "second update after a squash merge" case (spec, definition of done, item 3) — live.

```bash
gh api --method PUT repos/EmadMokhtar/pyfr-m8-verify/pulls/1/merge -f merge_method=squash -f commit_title='chore: update template v0.10.0 -> v0.11.0 (#1)' --jq '.merged'
gh api --method DELETE repos/EmadMokhtar/pyfr-m8-verify/git/refs/heads/pyfr/update-v0.11.0
gh api repos/EmadMokhtar/pyfr-m8-verify/contents/.pyfr-answers.yml --jq '.content' | base64 -d | grep _template_version
```
Expected: `true`; no output; `_template_version: "0.11.0"`.

- [ ] **Step 3: Clone, update the workflow file, seed the conflict**

`git clone` copies the repository; `cp` overwrites the project's workflow with the `v0.12.0` render (the template's `template-update.yml` contains no cookiecutter variable, so the example's render is byte-identical for every project — `grep -c cookiecutter '{{cookiecutter.project_slug}}/.github/workflows/template-update.yml'` prints `0`). The `sed` edits the README line that the `v0.12.0` template rewrites ("Five settings" becomes "Six settings" in the template), which guarantees the merge conflicts on `README.md` and nowhere else.

```bash
S=/private/tmp/claude-501/-Users-emadmokhtar-Projects-pyfr--claude-worktrees-m1-work-5c1a84/86219545-f7dc-4115-aedb-2fd16ee8def7/scratchpad
git -c credential.helper='!gh auth git-credential' clone https://github.com/EmadMokhtar/pyfr-m8-verify.git "$S/verify"
cp examples/reference-service/.github/workflows/template-update.yml "$S/verify/.github/workflows/template-update.yml"
git -C "$S/verify" add .github/workflows/template-update.yml
git -C "$S/verify" commit -q -m "ci: bring template-update.yml to the v0.12.0 render" -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
grep -n "^Five settings live in the GitHub interface, not in this repository. The$" "$S/verify/README.md"
sed -i '' 's/^Five settings live in the GitHub interface, not in this repository. The$/Five settings live in the GitHub interface, not in this repository (the team wiki says who holds each). The/' "$S/verify/README.md"
git -C "$S/verify" commit -q -am "docs: say where the settings are recorded" -m "Seeds a conflict with the v0.12.0 template for the M8 verification." -m "Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>"
git -C "$S/verify" -c credential.helper='!gh auth git-credential' push -q origin main && git -C "$S/verify" log -2 --format='%h %s'
```
Expected: the `grep` prints exactly one line number; the push succeeds (the `gh` token carries the `workflow` scope; if GitHub refuses the workflow-file push, ask the user to run the push from their terminal — do not work around it).

- [ ] **Step 4: Scenario A — dispatch without the secret**

`workflow_dispatch` starts the workflow by hand on `main`.

```bash
gh api --method POST repos/EmadMokhtar/pyfr-m8-verify/actions/workflows/template-update.yml/dispatches -f ref=main
```
Wait about two minutes, then:
```bash
gh api "repos/EmadMokhtar/pyfr-m8-verify/actions/runs?event=workflow_dispatch&per_page=1" --jq '.workflow_runs[0] | "\(.id) \(.status) \(.conclusion)"'
```
Repeat until `completed`. Expected `failure`. Then, with the run id as `RUN`:
```bash
gh api "repos/EmadMokhtar/pyfr-m8-verify/actions/runs/RUN/jobs" --jq '.jobs[0].steps[] | "\(.conclusion)\t\(.name)"'
gh api "repos/EmadMokhtar/pyfr-m8-verify/check-runs/$(gh api "repos/EmadMokhtar/pyfr-m8-verify/actions/runs/RUN/jobs" --jq '.jobs[0].id')/annotations" --jq '.[] | select(.annotation_level == "failure") | .message'
gh api repos/EmadMokhtar/pyfr-m8-verify/actions/runs/RUN/logs > "$S/runA.zip" && unzip -o -q "$S/runA.zip" -d "$S/runA" && grep -h "ignore:\|^.*conflict: \|create or update workflow" "$S/runA"/*/*Run\ the\ update*.txt "$S/runA"/*/*Push*.txt | cut -c30-
gh api "repos/EmadMokhtar/pyfr-m8-verify/issues?state=open" --jq 'length'
```
Expected: steps `Run the update` = `success`, the push step = `failure`, the issue and PR steps = `skipped`; one annotation starting `The push was refused because the update changes a workflow file and the token lacks the Workflows permission.`; the log shows `ignore: no .pyfr-update-ignore; using the built-in default`, `ignore: installed .pyfr-update-ignore from the template`, `conflict: README.md`, and GitHub's `refusing to allow a GitHub App to create or update workflow`; `0` open issues.

Record `RUN` as **run A**. Anything that differs from the expectation is a finding: write it down for the PR comment (and for Task 7 or a `fix:` — stop and report to the user before writing code).

- [ ] **Step 5: STOP — the user adds the secret**

Report run A to the user and ask them to do this (it needs their GitHub password manager; Claude must not create tokens or enter credentials):

> Create a fine-grained personal access token: Settings → Developer settings → Personal access tokens → Fine-grained tokens. Repository access: *Only select repositories* → `pyfr-m8-verify`. Repository permissions: **Contents**, **Issues**, **Pull requests**, **Workflows** — all *Read and write*. Then on `pyfr-m8-verify`: Settings → Secrets and variables → Actions → New repository secret, name `RELEASE_TOKEN`, value the token.

Continue only after the user says it is done. Check: `gh api repos/EmadMokhtar/pyfr-m8-verify/actions/secrets --jq '.secrets[].name'` prints `RELEASE_TOKEN`.

- [ ] **Step 6: Scenario B — conflict → issue**

Dispatch and poll exactly as in Step 4. Expected `completed success`. Then:
```bash
gh api "repos/EmadMokhtar/pyfr-m8-verify/actions/runs/RUN/jobs" --jq '.jobs[0].steps[] | "\(.conclusion)\t\(.name)"'
gh api "repos/EmadMokhtar/pyfr-m8-verify/issues?state=open" --jq '.[] | select(.pull_request == null) | "\(.number) \(.title)\n\(.body)"'
gh api repos/EmadMokhtar/pyfr-m8-verify/branches --jq '.[].name'
gh api repos/EmadMokhtar/pyfr-m8-verify/commits/template --jq '.commit.message'
```
Expected: push step `success`, issue step `success`, PR step `skipped`; one issue `chore: template v0.11.0 -> v0.12.0 conflicts` whose body lists `` - `README.md` `` and nothing else under the first sentence, and ends with `https://github.com/EmadMokhtar/pyfr/releases/tag/v0.12.0`; branches `main` and `template` only (no `pyfr/update-v0.12.0`); the `template` tip's message ends with `Pyfr-Template-Version: v0.12.0`.

Record **run B** and the **issue number**.

- [ ] **Step 7: Scenario C — the stop**

Dispatch and poll. Expected `completed success`. Then:
```bash
gh api "repos/EmadMokhtar/pyfr-m8-verify/actions/runs/RUN/jobs" --jq '.jobs[0].steps[] | "\(.conclusion)\t\(.name)"'
gh api "repos/EmadMokhtar/pyfr-m8-verify/issues?state=open" --jq '[.[] | select(.pull_request == null)] | length'
```
Expected: the stop step `success` and every step after it `skipped`; still `1` open issue. Record **run C**.

- [ ] **Step 8: Scenario D — clean merge → pull request with CI**

Close the issue, revert the seed edit, push:
```bash
gh api --method PATCH repos/EmadMokhtar/pyfr-m8-verify/issues/ISSUE -f state=closed --jq '.state'
git -C "$S/verify" revert --no-edit HEAD
git -C "$S/verify" -c credential.helper='!gh auth git-credential' push -q origin main
```
(`git revert` makes a new commit that undoes the seed commit; the workflow-file commit stays.)

Dispatch and poll. Expected `completed success`. Then:
```bash
gh api "repos/EmadMokhtar/pyfr-m8-verify/actions/runs/RUN/jobs" --jq '.jobs[0].steps[] | "\(.conclusion)\t\(.name)"'
gh api "repos/EmadMokhtar/pyfr-m8-verify/pulls?state=open" --jq '.[] | "\(.number) \(.title) \(.head.ref)\n\(.body)"'
gh api "repos/EmadMokhtar/pyfr-m8-verify/issues/PRNUM/comments" --jq 'length'
gh api "repos/EmadMokhtar/pyfr-m8-verify/actions/runs?branch=pyfr/update-v0.12.0" --jq '.workflow_runs[] | "\(.name) \(.event) \(.status)"'
gh api repos/EmadMokhtar/pyfr-m8-verify/actions/runs/RUN/logs > "$S/runD.zip" && unzip -o -q "$S/runD.zip" -d "$S/runD" && grep -h "template:" "$S/runD"/*/*Run\ the\ update*.txt | cut -c30-
```
Expected: push step and PR step `success`, issue step `skipped`; one PR `chore: update template v0.11.0 -> v0.12.0` from `pyfr/update-v0.12.0` whose body is the `v0.12.0` changelog entry; `0` comments (the token is a personal access token, so no "CI has not run" note); at least `CI pull_request` and `Docs pull_request` runs listed on the branch; the update log's `template:` lines say the tip already records `v0.12.0` and the sync was skipped. Record **run D** and the **PR number**.

Leave the pull request open; the user decides whether to merge it or keep the repository as it is. Do not delete anything.

- [ ] **Step 9: Report on PR `N`**

Write `$S/verification-comment.md`:

```markdown
### Live verification of `template-update.yml` (spec 8.5)

Repository `EmadMokhtar/pyfr-m8-verify`, generated at v0.10.0, squash-merged its v0.11.0 update first, then updated `v0.11.0 -> v0.12.0` — a template change that touches `.github/workflows/`, so every push needs the Workflows permission.

| Scenario | Run | Result |
| --- | --- | --- |
| A. No `RELEASE_TOKEN`, conflicting `README.md` edit | [run A](https://github.com/EmadMokhtar/pyfr-m8-verify/actions/runs/RUNA) | Update ran (`.pyfr-update-ignore` installed, `conflict: README.md`, merge aborted); the `template` push was refused; the step failed with the Workflows-permission annotation; no issue, no pull request |
| B. `RELEASE_TOKEN` with Workflows, same edit | [run B](https://github.com/EmadMokhtar/pyfr-m8-verify/actions/runs/RUNB) | `template` pushed to v0.12.0; [issue #ISSUE](https://github.com/EmadMokhtar/pyfr-m8-verify/issues/ISSUE) opened naming `README.md` only |
| C. Dispatched again with the issue open | [run C](https://github.com/EmadMokhtar/pyfr-m8-verify/actions/runs/RUNC) | Stopped at the existence check; nothing else ran |
| D. Issue closed, edit reverted | [run D](https://github.com/EmadMokhtar/pyfr-m8-verify/actions/runs/RUND) | Clean merge from the already-pushed `template` tip; [pull request #PRNUM](https://github.com/EmadMokhtar/pyfr-m8-verify/pull/PRNUM) opened with the changelog; CI started on it; no "CI has not run" comment |

Findings: _none_ / _list_.
```

Replace `RUNA`…`PRNUM` with the recorded numbers and fill in *Findings*. Post it:
```bash
gh api --method POST repos/EmadMokhtar/pyfr/issues/N/comments -F body=@"$S/verification-comment.md" --jq '.html_url'
```
Then edit the PR body's `_Filled in by the verification task — see the comments below._` line to `See the verification comment below.` and tick the second test-plan box:
```bash
gh api repos/EmadMokhtar/pyfr/pulls/N --jq '.body' > "$S/pr3-body.md"
```
edit the file, then
```bash
gh api --method PATCH repos/EmadMokhtar/pyfr/pulls/N -F body=@"$S/pr3-body.md" --jq '.number'
```

- [ ] **Step 10: The spec note**

In `docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md`, section 8.5, find:
```
  `workflow_dispatch` on a project generated at `v0.10.0` as the last step
  of PR 2; the conflict path needs two releases whose template bodies
  differ, and is verified the same way in PR 3, once `v0.12.0` exists.
```
Replace with:
```
  `workflow_dispatch` on a project generated at `v0.10.0` as the last step
  of PR 2; the conflict path needs two releases whose template bodies
  differ, and is verified the same way in PR 3, once `v0.12.0` exists.
  *(Verified in PR 3 on `EmadMokhtar/pyfr-m8-verify`, `v0.11.0 -> v0.12.0`
  after a squash-merged first update: the refused push without
  `RELEASE_TOKEN` and its annotation, conflict → issue, issue → stop, and
  clean → pull request with CI running under a token that has the
  Workflows permission. The run links are in the pull request.)*
```

Commit:
```bash
git add docs/superpowers/specs/2026-09-14-pyfr-m8-template-updates-design.md
git commit -F - <<'EOF'
docs(pyfr): record the live verification of the weekly workflow

Refs #51

Co-Authored-By: Claude Opus 5 <noreply@anthropic.com>
EOF
git -c credential.helper='!gh auth git-credential' push https://github.com/EmadMokhtar/pyfr.git claude/m8-pr3-close-m8
```

---

### Task 7: The follow-up issue

**Files:** none.

**Interfaces:**
- Consumes: PR number `N`; the findings from Task 6.
- Produces: an issue number, added to the PR body's summary as `Follow-ups: #M`.

Two enhancements were noted during PR 2 and left out on purpose (they are features, and PR 3 is `docs:`); Task 6 may add more. They go in one issue so they are not lost.

- [ ] **Step 1: Write and create**

Write `$S/followups.md`:

```markdown
Left over from M8's live verification (#N). Neither is a defect; both are small enhancements to `pyfr-cli` and the weekly workflow.

1. **`update-check --json` should include `release_url`.** `pyfr_cli.changelog.release_url` already derives `https://github.com/<owner>/<repo>/releases/tag/vX.Y.Z` from the recorded `_template`; `template-update.yml` rebuilds that address by hand for the issue body. Exposing it keeps the two in one place.
2. **Stop on any open `pyfr/update-*` pull request, not only the newest version's.** Today the stop step looks for a pull request or issue for `NEWEST` only. If a team has not merged last month's `pyfr/update-v0.12.0`, this month's run opens `pyfr/update-v0.13.0` beside it, and the older one conflicts with the newer as soon as either merges. Skipping while any `pyfr/update-*` pull request is open — and saying so in the log — is the safer default.

<!-- add Task 6 findings here, one numbered item each -->

Refs #51
```

```bash
gh api --method POST repos/EmadMokhtar/pyfr/issues -f title='feat(pyfr-cli): follow-ups from the m8 live verification' -F body=@"$S/followups.md" --jq '.number, .html_url'
```

- [ ] **Step 2: Cross-link from the PR**

Append a line `Follow-ups: #M` (M = the new issue number) to the PR body's `## Summary` section, below the bullet list, using the same fetch-edit-PATCH sequence as Task 6, Step 9.

- [ ] **Step 3: Hand back**

Report to the user: PR `N`'s URL, CI state, the four run links, the issue and PR on the verify repository, the follow-up issue, and the one open question — whether to keep `pyfr-m8-verify` as it is (it is theirs; nothing was deleted).

---

## Self-review

**Spec coverage.** Section 1, item 4 — the workflow run by hand on a real project: done in PR 2 (clean path) and Task 6 here (conflict, stop, refused push, pull request with CI). Item 5 — ADR 0018 (Task 1), contributor's guide to migration scripts (Task 2), roadmap/index/README "M0–M8 done" (Task 3). Section 7.2 — every bullet has a task: ADR (1), `contributing.md` (2), roadmap/index/README (3), glossary `pyfr-cli` and Trusted Publishing (3, Step 5), the master spec note (4). Section 8.5 — the conflict path verified once `v0.12.0` exists (6). Section 9, PR 3 row — title, contents, "whatever the verification turned up" (6 → 7 or a `fix:`). `getting-started.md` was not in 7.2; it said "M8's template updates read it" and is fixed in Task 3 for the same reason as the others.

**Placeholders.** The plan uses `N`, `RUN`, `ISSUE`, `PRNUM`, `M` for numbers that exist only at execution time; each is defined where it first appears and the step says where the value comes from. No "TBD"/"add appropriate …" steps.

**Consistency.** The ADR file name `0018-the-updater-is-a-published-cli.md` is identical in Tasks 1, 2 and 3 and matches spec 7.2. The anchor `#working-on-pyfr-cli` (Task 2, Step 3) is checked in Task 2, Step 9. The verify-repository clone path `$S/verify` is defined in Task 6, Step 3 and reused unchanged in Steps 8–9. The CI job name `docs` for `just wheel` is checked in Task 2, Step 8 before it is relied on.
