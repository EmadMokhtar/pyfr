# PyFr M8 — Template updates

**Date:** 2026-09-14
**Extends:** [`2026-08-28-pyfr-cookiecutter-template-design.md`](2026-08-28-pyfr-cookiecutter-template-design.md)
— decision D14, section 11 (updates) and the M8 row of section 14.
**Status:** approved design, ready for an implementation plan.

M7 made PyFr a usable template. Every project it generates records the
template version it came from in `.pyfr-answers.yml`, and nothing else. M8
spends that record: a generated project pulls a later template version in
through an ordinary git merge, and a weekly job opens a pull request when
one is available. **At the end of M8 the template and the projects it
generated stay in step, forever, with no runtime dependency between them.**

Where this document and section 11 of the master spec disagree, this
document wins; section 13 lists every such point.

---

## 1. Definition of done

M8 is done when all of the following are true on `main`:

1. `pyfr-cli` is on PyPI. Its version is the template's version: the same
   `cz bump` moves `pyproject.toml`, `cookiecutter.json`'s
   `_template_version`, the git tag and the PyPI release together.
   `uvx --from pyfr-cli@latest pyfr --version` prints the newest template
   version.
2. In a project generated at version A, `just update` moves it to version
   B through a merge: files the team deleted stay deleted, paths in
   `.pyfr-update-ignore` are untouched, template-owned changes arrive, and
   `.pyfr-answers.yml` records B. The end-to-end test in section 8.2 proves
   this on every push, without the network.
3. A second update after the first was squash-merged produces no spurious
   conflicts (section 4.3 explains why this needs proving).
4. Every generated project carries `.github/workflows/template-update.yml`,
   which opens a pull request on a clean merge and an issue on a conflict.
   Run once by hand, through `workflow_dispatch`, on a real generated
   project before M8 closes.
5. `docs/guides/update-from-template.md` exists in every generated project;
   the root has ADR 0018 and a contributor's guide to writing a migration
   script; the roadmap, `index.md` and the README say "M0–M8 done".
6. The unit, end-to-end and generation tests pass on every push; the golden
   diff is clean; the wheel builds and its console script runs in CI.

---

## 2. Decisions fixed by this document

| # | Decision | Why |
|---|---|---|
| M8-1 | The updater is a Python package, `pyfr-cli`, published to PyPI from the template repository, run through `uvx`. It is **not** a script inside each generated project. | The updater always runs at the *target* version, so it knows how to migrate to itself; a fix reaches every project at once; projects generated before M8 bootstrap with the same one line; generated projects gain no `cookiecutter` dependency. ADR 0018 records this. |
| M8-2 | Distribution name `pyfr-cli`, command `pyfr`, import name `pyfr_cli`. Subcommands `update` and `update-check` only. | `pyfr` on PyPI belongs to an unrelated solver. `uvx --from pyfr-cli pyfr` never clashes with it: `uvx` runs the package's own command in an isolated environment. `pyfr new` is out of scope (section 12). |
| M8-3 | The `template` branch lives on the remote (`origin/template`) and the updater pushes it before merging. | A squash-merged update pull request discards the merge commit, so the template commit survives nowhere else. Without the pushed branch the second update would re-merge the first (section 4.3). |
| M8-4 | The merge base for a first update is the repository's single root commit. | A generated repository's first commit is unmodified template output, whichever path created it — the hook's `git commit` or Backstage's publish action (master spec 11.7). |
| M8-5 | `.pyfr-update-ignore` uses gitignore syntax, matched with the `pathspec` library. A project without the file uses the built-in default, rendered for its answers. | Teams already know gitignore syntax. Projects generated at v0.7.0–v0.11.0 have no ignore file and must still update. |
| M8-6 | The updater never prompts and never leaves the working tree half-changed. State for a paused run lives in `.git/pyfr-update.json`. A re-run of the same command resumes. | It runs unattended in the weekly workflow. One command, no `--continue` flag to learn. |
| M8-7 | Publishing uses PyPI Trusted Publishing from `release.yml`; the publish job is last and nothing depends on it. | No long-lived PyPI token in a secret. Until the publisher is registered on pypi.org, only that job is red. |
| M8-8 | The weekly workflow reuses `RELEASE_TOKEN`, whose documented permissions widen to Contents, Pull requests and Issues (read and write), with `GITHUB_TOKEN` as the fallback. | One secret to manage. The fallback still opens the pull request; it cannot start CI on it, and the workflow says so in a comment. |
| M8-9 | Migration scripts live at `updates/vX.Y.Z/before.py` and `after.py` in the template repository, outside the template body, and run with `uv run python` in the project. Standard library only, idempotent. | Outside the body so they are never rendered into a project. Standard library only because they run in the project's environment, which may hold nothing else. |

---

## 3. The `pyfr-cli` package

### 3.1 Layout

```
src/pyfr_cli/
  __init__.py     # __version__ from importlib.metadata
  __main__.py     # the `pyfr` command: argparse, exit codes
  git.py          # a thin subprocess wrapper; every git call goes through it
  answers.py      # read .pyfr-answers.yml; write the rendered one back
  versions.py     # list the template's tags, pick the newest, compare
  render.py       # shallow-clone the template at a tag, render it
  ignore.py       # .pyfr-update-ignore: the built-in default, pathspec matching
  vendor.py       # the `template` branch: find, guard, sync, commit, push
  migrate.py      # updates/<version>/before.py and after.py
  changelog.py    # the CHANGELOG.md entries between two versions
  state.py        # .git/pyfr-update.json
  update.py       # the orchestration of section 4
```

`src/` sits beside `hooks/`, `scripts/` and `tests/` at the repository root,
outside `{{cookiecutter.project_slug}}/`, so cookiecutter never renders it.
The root `ruff.toml` already covers `src/`; `mypy --strict` over
`src/pyfr_cli` joins the root `just lint`, and `mypy` joins the root `dev`
group. A published tool is type-checked.

### 3.2 Commands

```
pyfr update [--to VERSION] [--no-push] [--template URL]
pyfr update-check [--json] [--template URL]
pyfr --version
```

`--to` accepts `v0.12.0` or `0.12.0`. `--template` overrides the `_template`
URL recorded in the answers file — for tests, and for forks. `--no-push`
skips pushing the `template` branch (offline work); the next run pushes it
— even a run that finds nothing else to do.

`update-check` prints `recorded v0.10.0, newest v0.12.0` and exits 0 when
current, 1 when behind, 2 on error. `--json` prints
`{"recorded": "v0.10.0", "newest": "v0.12.0", "behind": true, "template": "https://github.com/EmadMokhtar/pyfr"}`
for the workflow.

`update` exits 0 when updated or already current, 1 when the user has to
act (a merge with conflicts is waiting), 2 on error. Its output uses stable
line prefixes the workflow reads — `conflict: <path>` for each conflicting
file, `recorded: v0.12.0` at the end.

### 3.3 Dependencies

Declared, not transitive: `cookiecutter>=2.6,<3`, `pyyaml>=6.0`,
`pathspec>=0.12`. `git` and `uv` on `PATH`, checked up front with a plain
error. argparse from the standard library is the CLI layer, as in
`scripts/regen.py`; cookiecutter depends on click, but this repository does
not rest on anyone's transitive dependency.

### 3.4 `pyproject.toml` at the root

- `[project] name = "pyfr-cli"`, `dependencies = [...]`,
  `[project.scripts] pyfr = "pyfr_cli.__main__:main"`.
- `[build-system]` with `hatchling` and
  `[tool.hatch.build.targets.wheel] packages = ["src/pyfr_cli"]`, so the
  wheel carries the package and nothing else — not `hooks/`, not `scripts/`,
  not the template body.
- `[tool.uv] package = false` goes; the project is a package now.
- The header comment changes. Today it says the repository is "not a
  distributable package". The new wording: the template is not a *runtime*
  dependency of a generated service (master spec D1 holds — a service
  imports no PyFr package); `pyfr-cli` is a development-time tool run
  through `uvx`.
- Commitizen keeps `version_provider = "uv"` and
  `version_files = ["cookiecutter.json:_template_version"]`; the lock's
  package entry is now named `pyfr-cli`, and `tests/test_release_bump.py`
  pins that the bump still moves all three places.

### 3.5 Publishing

A `publish-pypi` job in the root `.github/workflows/release.yml`,
`needs: release`, runs only when the release created a tag, with a
15-minute timeout: checkout at the tag, then ask PyPI whether the version
is already there (`https://pypi.org/pypi/pyfr-cli/<version>/json` — 200
means skip, 404 means publish, anything else fails the job rather than
guessing), then `uv build` and `uv publish` with
`permissions: id-token: write`. `uv publish` detects GitHub Actions and
uses Trusted Publishing by itself, so no `pypa/gh-action-pypi-publish`
step: PyPI accepts a short-lived OpenID Connect token that GitHub Actions
mints for the run, and no PyPI token is stored anywhere.

One manual step, once, before PR 1 merges: on pypi.org, register a
*pending publisher* for project `pyfr-cli`, owner `EmadMokhtar`, repository
`pyfr`, workflow `release.yml`, no environment. If it is missing the
`publish-pypi` job fails and every other release job still succeeds; the
job is last and nothing depends on it.

---

## 4. `pyfr update`

### 4.1 Preconditions

Each failure is one line of cause and one of fix on stderr, exit 2:

- Run at the project root: `.pyfr-answers.yml` is in the current directory
  and `git rev-parse --show-toplevel` is that directory.
- `git` and `uv` on `PATH`; `user.name` and `user.email` configured (the
  tool commits).
- `.pyfr-answers.yml` parses and has `_template` and `_template_version`.
  A project generated before v0.7.0 has no such file; the how-to says how
  to write one.
- On a branch, not a detached HEAD.
- No uncommitted changes to tracked files
  (`git status --porcelain --untracked-files=no` is empty). Untracked
  files are fine. This precondition is what makes `git reset --hard HEAD`
  a safe recovery from any later failure (section 10).
- No merge, rebase or cherry-pick in progress — unless
  `.git/pyfr-update.json` says this tool left it there (section 4.8).

### 4.2 The target

`git ls-remote --tags <template>` lists the tags; those matching
`^v\d+\.\d+\.\d+$` are kept and compared as integer tuples; the highest is
the target unless `--to` names one. Pre-release tags never match, so they
are never a target. `_template_version` is recorded without the `v`
(`"0.10.0"`, as `cookiecutter.json` holds it); the tool compares tuples and
prints with the `v`.

- target equals the recorded version → `already current at v0.10.0`,
  exit 0.
- target is lower → error: no downgrades.
- `--to` names a tag that does not exist → error listing the five newest.

### 4.3 The `template` branch

An update is a three-way merge and needs a merge base: a commit both sides
descend from. The `template` branch supplies it: pristine rendered output
and nothing else.

**Why it lives on the remote.** Master spec 11.2 describes a local branch,
always rebuildable from the root commit. That holds for the first update
only. After it, the base for the *second* update must be the template
commit the first merged — and a squash-merged pull request (this
repository's own practice, and most teams') discards the merge commit, so
that template commit survives nowhere unless the branch itself was pushed.
The pushed branch keeps that commit alive; section 4.7 says how the merge
is told to use it. Every machine — a laptop, the weekly workflow's fresh
checkout — starts by fetching it.

**Finding it**, in order:

1. `origin/template` exists → fetch it; a local `template` that is an
   ancestor fast-forwards to it; a local `template` that is not is an error
   naming both commits. An `origin` that cannot be reached at all is an
   error (`git ls-remote` exits 128, not the 2 of an absent branch) —
   unless `--no-push` was given, which promises to work from the local
   branch: then it counts as absent.
2. No remote branch, local `template` exists → use it, with a notice that
   it is not on the remote yet (it will be after this run's push).
3. Neither → create it at the single root commit
   (`git rev-list --max-parents=0 HEAD`). Two or more roots (a subtree
   merge, an imported history) → error pointing to the manual procedure
   in the how-to. The tool prints `template: created from root commit
   <sha> "<subject>"` so a non-pristine root is visible on the first run.

**The guard** (master spec, section 14, "someone hand-edits the `template`
branch"). Every commit this tool makes on `template` carries the trailer
`Pyfr-Template-Version: vX.Y.Z` — a `Key: value` line at the end of the
message, the convention `Signed-off-by:` uses. Walking from the tip, every
commit down to the first one *without* the trailer must carry it; that
first commit is the base. A hand-made commit on top has no trailer at the
tip → refused, with the how-to's procedure. The base is normally the root
commit, whose version is read from `git show <root>:.pyfr-answers.yml`; a
deliberately re-pointed `template` (`git branch -f template <sha>`, the
manual procedure after a rewritten history) is accepted at the cost of one
noisier merge.

**The branch's version** is the tip's trailer, or the base's answers file.
It must be between the recorded version and the target, inclusive. A branch
ahead of the recorded version is a pending update — the weekly workflow
synced and pushed it, and the project has not merged its pull request yet
— and the sync continues from it; the merge base is still the recorded
version's commit. Below the recorded version (the branch was deleted and
rebuilt from the root) or above the target (`--to` names a version the
branch has passed), the tool stops and says which. When the tip already
records the target, sections 4.4 and 4.5 are skipped — the render still
runs, because the answers file the merge records (master spec 11.3, step
10) comes from it, but the sync, commit and push do not — a re-run after a
conflicted merge, or a laptop picking up what the weekly workflow already
pushed.

### 4.4 Render

```
git clone --depth 1 --branch <tag> <template> <tmp>/template
```

A shallow clone (`--depth 1`: the one commit at the tag, no history) into a
temporary directory. Cookiecutter then renders that *local path* — never
the URL, so cookiecutter's own `~/.cookiecutters` cache and its
"delete and re-clone?" prompt are never involved, and the clone's
`updates/` and `CHANGELOG.md` are on disk for sections 4.6 and 4.7.

The render call mirrors `scripts/regen.py`: `no_input=True`,
`default_config=True` (a contributor's `~/.cookiecutterrc` must not reach
it), `extra_context=` the recorded answers, `PYFR_REGEN=1` in the
environment so the target's own post-generation hook prunes and stops.

Which answers: the keys the target's `cookiecutter.json` declares (those
not starting with `_`), taken from the recorded answers where present.
A prompt the target added since the recorded version takes its default,
and the tool prints `render: new prompt <name> defaulted to <value>` —
the team can change it in `.pyfr-answers.yml` afterwards. A recorded
answer the target no longer declares is dropped silently. A recorded
choice the target no longer offers is a cookiecutter `ValueError`, shown
verbatim; so is a rejection by the target's pre-generation hook.

### 4.5 Sync and commit

```
git worktree add <tmp>/worktree template
```

A worktree is a second checkout of the same repository in another
directory, on another branch; the project's own checkout is untouched.

In it: every file in the render is copied over (bytes, creating
directories); every tracked file the render does not produce is deleted;
both steps skip paths `.pyfr-update-ignore` matches (section 5.2 — the
project's file, read from the project's working tree, or the built-in
default when it has none). Empty directories are removed. `git add -A`,
then:

```
chore: template v0.10.0 -> v0.12.0

Pyfr-Template-Version: v0.12.0
```

`--allow-empty`: when nothing in the body changed for these answers, the
trailer still records the version.

The commit passes `--no-verify`, as does every commit this tool makes: the
worktree shares `.git/hooks`, where the generator installed pre-commit,
and the project's hooks must not run against the pristine template in a
directory that has no environment. CI runs the gates on the pull request.

Then `git push origin template`, unless `--no-push`. A rejected push
(another machine advanced the branch in between) stops the run with exit
2; a re-run fetches and continues. The worktree is removed in a `finally`;
`git worktree prune` at the start of every run clears what a killed run
left.

### 4.6 Migration scripts

From the clone's `updates/`, the directories named `vX.Y.Z` with a version
in `(recorded, target]`, in ascending order. For each, `before.py` runs now
and `after.py` after the merge (section 4.7), each as

```
uv run --no-project python <clone>/updates/vX.Y.Z/before.py
```

with the project root as the working directory and `PYFR_UPDATE_FROM`,
`PYFR_UPDATE_TO` (with the `v`) in the environment. `--no-project` skips
the project's own `uv sync`: the scripts are standard library only
(decision M8-9), a sync would be slow, and it would fail in a fresh
checkout that has no environment yet. A non-zero exit stops
the run with exit 2 and the script's output. Changes the before-scripts
leave are committed as `chore: prepare for template v0.12.0` so the merge
starts from a clean tree; section 6 gives the scripts' contract.

### 4.7 Merge and record

**Pinning the merge base.** The base must be the template commit at the
*recorded* version — call it `T_prev`: the root commit on a first update,
otherwise the `template` commit whose trailer names the recorded version.
Git would pick it by itself only if `T_prev` is in `HEAD`'s history, and
after a squash-merged update pull request it is not: the squash discards
the merge commit, `git merge-base` falls back to the root, and every hunk
the team resolved last time conflicts again (verified in the PR 1 plan).
So when `T_prev` is not an ancestor of `HEAD`, the tool adds it as a
temporary extra parent — `git replace --graft HEAD <HEAD's parents>
T_prev`, a replacement object under `refs/replace/` that changes how git
reads the commit, not the commit itself — runs the merge, and deletes the
graft. The merge commit's parents are the real `HEAD` and the template
commit; nothing of the graft remains. This is what makes `origin/template`
necessary: `T_prev` must exist somewhere.

```
git merge --no-ff --no-commit template
```

`--no-ff`: always a merge commit, never a fast-forward, even in a project
that committed nothing since its root. `--no-commit`: stop before
committing so the answers file can join the commit.

Then, clean or not, the render's `.pyfr-answers.yml` — the recorded answers,
the new prompts' defaults, `_template_version` at the target — is copied
into the working tree and staged; the `_template` the project recorded is
kept — `--template` is a one-off override and a fork stays pointed at
itself. It is an ignored path, so the merge never touches it and it rides
in the merge commit either way. The same goes for
the render's `.pyfr-update-ignore` when the project has none (the
built-in-default case of section 5.2): the default ignores the file
itself, so the merge could never deliver it, and the tool copies and
stages it here instead.

- **Clean:** commit `chore: update template v0.10.0 -> v0.12.0` with the
  template's `CHANGELOG.md` entries in `(recorded, target]` as the body
  (section 4.9); run the after-scripts; commit what they changed as
  `chore: finish template v0.12.0`; print `recorded: v0.12.0`; exit 0.
- **Conflicts:** print one `conflict: <path>` line per file from
  `git diff --name-only --diff-filter=U`, then the three commands that
  finish the job — resolve the files and `git add` them,
  `git commit --no-edit`, `pyfr update` again. The tool writes the
  prepared message (subject and changelog body, section 4.9) into
  `.git/MERGE_MSG`; `--no-edit` commits it as written, where a plain
  `git commit` would open the editor and its default clean-up
  (`--cleanup=strip`) would delete every line starting with `#` — the
  `## [vX]` and `### Feat` headings. Write the state file. Exit 1.

### 4.8 Resuming

`.git/pyfr-update.json` (found through `git rev-parse --git-dir`, so a
worktree finds its own) holds `{"from": "v0.10.0", "to": "v0.12.0",
"phase": "merging" | "after-scripts", "graft": "<sha>" | null}` — `graft`
is the sha of the `HEAD` the tool grafted an extra parent onto for the
merge (section 4.7), or `null` when no graft was needed, so a run that
died before deleting the graft is cleaned up by the next one. It is never
committed: `.git/` is not part of the tree.

Running `pyfr update` again:

- phase `merging` and `MERGE_HEAD` still exists → the merge is unfinished:
  print the three commands again, exit 1.
- phase `merging` and the merge is committed → phase becomes
  `after-scripts`.
- phase `after-scripts` → re-clone the target (section 4.4, for
  `updates/`), run the after-scripts, commit, delete the state file, exit 0.

`git merge --abort` while in phase `merging` puts the tree back where it
was; the next `pyfr update` finds the state file, no `MERGE_HEAD`, and a
recorded version still at the old value — it deletes the stale state and
starts over, skipping the render because `template` is already at the
target.

### 4.9 Changelog entries

The template's `CHANGELOG.md` is Commitizen's: `## v0.12.0 (2026-09-20)`
headings. The sections whose version is in `(recorded, target]` are
concatenated, newest first, into the merge commit's body — and from there
into the weekly pull request's body. The heading of each section links to
the release: `https://github.com/EmadMokhtar/pyfr/releases/tag/v0.12.0`,
built from the `_template` URL.

---

## 5. What a generated project receives

### 5.1 Two recipes

In the generated `justfile`, next to `changelog` and `next-version`:

```
# Pull in a newer template version through a git merge. Runs the updater
# at the target version: the newest release on PyPI is, by construction,
# the newest template tag (docs/guides/update-from-template.md).
update to="":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "{% raw %}{{to}}{% endraw %}" ]; then
        version="{% raw %}{{to}}{% endraw %}"; version="${version#v}"
        uvx --from "pyfr-cli==${version}" pyfr update --to "v${version}"
    else
        uvx --from pyfr-cli@latest pyfr update
    fi

# Exit non-zero when a newer template version exists. The weekly
# workflow runs this first.
update-check:
    uvx --from pyfr-cli@latest pyfr update-check
```

(`{% raw %}{{to}}{% endraw %}` is how the template body's `justfile`
already writes `just`'s own `{{name}}` past Jinja — see its `migrate-new`
recipe; the rendered recipe reads `{{to}}`.)

`@latest` makes `uvx` resolve the newest release instead of reusing a
cached environment. The implementation plan verifies the exact `--from`
spelling against the pinned `uv`; `--refresh-package pyfr-cli` is the
fallback if `@latest` is not accepted in `--from`.

Neither `pyfr-cli` nor `cookiecutter` enters the project's dependency
groups.

### 5.2 `.pyfr-update-ignore`

The paths an update never touches. Gitignore syntax: blank lines and lines
starting with `#` are skipped (a `#` after a pattern is part of the
pattern, as in `.gitignore`), a trailing `/` names a directory and
everything under it, `*` and `**` as in `.gitignore`, `!` negates. The tool
applies it in step 4.5 — the template side never changes these paths, so
the merge never forms an opinion about them.

The generated default, rendered for the answers (`<package>` is
`package_name`; the `migrations/` and `schema.sql` lines appear only when
`database` is `postgres`, since they are pruned otherwise):

```
# Paths `just update` leaves exactly as this project has them: yours from
# the first day, or artifacts of your code. Add paths as you diverge --
# one gitignore pattern per line, comments on their own lines.
# Everything not listed is template-owned and receives fixes by default.

# Written by the update itself.
/.pyfr-answers.yml
# This file.
/.pyfr-update-ignore
/README.md
/CHANGELOG.md
# Resolver output; run `uv lock` after an update that touched pyproject.toml.
/uv.lock
# Your schema.
/migrations/
/schema.sql
# Artifacts of your code: the contract, and the baseline your release promotes.
/openapi.json
/openapi.baseline.json
# Your decisions.
/docs/adr/
# The example slice, then your business model.
/src/<package>/domain/
/src/<package>/services/
/src/<package>/api/v1/
```

Every pattern carries a leading `/`: without it, gitignore syntax matches
the name at any depth, and `README.md` would also match
`docs/adr/README.md`.

`uv.lock` is new against master spec 11.4, and necessary: the render has
no lock (`uv sync` is an environmental hook step, skipped under
`PYFR_REGEN`), so without the line the sync would delete `uv.lock` on the
template side and every update would conflict on it.

Everything else is template-owned, including `pyproject.toml`, `tests/`,
`.github/`, both Dockerfiles, `compose.yaml`, the `justfile`, the tool
configurations, `ops/`, `scripts/`, `docs/` outside `adr/`, and the
`observability/`, `infrastructure/` and `api/` packages outside `v1/`. A
team's added dependency lines and the template's changed lines merge at
line level and conflict only when both touch the same lines — the
mechanism working as designed.

The tool ships the same list, as a template, in `ignore.py`: a project
generated at v0.7.0–v0.11.0 has no ignore file, uses the built-in default
rendered for its answers, and receives the file with the update.

### 5.3 `.github/workflows/template-update.yml`

```
on:
  schedule:
    - cron: "23 6 * * 1"      # Mondays 06:23 UTC; off the hour, like nightly.yml
  workflow_dispatch:
permissions:
  contents: write
  pull-requests: write
  issues: write
```

Steps, one job:

1. `actions/checkout` with `fetch-depth: 0` (the root commit and `template`
   must be reachable). The checkout keeps the *workflow* token — it dies
   with the job, and `pyfr update` needs it to fetch `origin/template` of
   a private repository. `RELEASE_TOKEN` never enters the checkout: the
   template's own hooks and `uvx`'s installs run in later steps, and a
   long-lived token must not be readable there — the same rule
   `release.yml` follows. The tool runs with `--no-push`, and a separate
   push step pushes `template` and the update branch with `RELEASE_TOKEN`
   when it exists (so CI starts on the pull request), the workflow token
   otherwise. *(Amended in PR 2: the original text persisted
   `RELEASE_TOKEN` in the checkout.)*
2. Install `uv`; set `user.name`/`user.email` as `release.yml` does.
3. `uvx --from pyfr-cli@latest pyfr update-check --json`. Exit 0 → done.
   Exit 2 → the job fails.
4. `git switch -c pyfr/update-<newest>`, then
   `uvx --from pyfr-cli@latest pyfr update --no-push`, output captured to a file.
   - **Exit 0** → the push step pushes `template` and the branch; `gh pr create` titled
     `chore: update template v0.10.0 -> v0.12.0`, body from the merge
     commit (`git log -1 --format=%b --grep='^chore: update template '`). Skipped when an open pull request
     from that branch exists (`gh pr list --head`). When `RELEASE_TOKEN`
     is unset (`env: HAS_TOKEN: ${{ secrets.RELEASE_TOKEN != '' }}`),
     add one comment: GitHub does not start workflows for events the
     workflow token caused, so close and reopen this pull request to
     start CI, or add `RELEASE_TOKEN`.
   - **Exit 1** → `git merge --abort`; `gh issue create` titled
     `chore: template v0.10.0 -> v0.12.0 conflicts` with the `conflict:`
     paths from the captured output and the release link from the JSON's
     `template` field, telling the team to run `just update` locally.
     Skipped when an open issue with that title exists. `template` is
     already pushed at the target, so the local run skips the render.
   - **Exit 2** → the job fails with the captured output.

The shell stays thin: every decision is the tool's exit code, tested in
section 8. The `GITHUB_TOKEN` fallback also needs the repository setting
"Allow GitHub Actions to create and approve pull requests"; the README says
so where `RELEASE_TOKEN` is already described.

### 5.4 The token

`RELEASE_TOKEN` today: a fine-grained personal access token, Contents read
and write, this repository only, needed when a ruleset on `main` requires
pull requests. M8 widens the documented permissions to Contents, Pull
requests and Issues (read and write) and states the two consequences of
leaving it unset: the update pull request opens but its CI does not start
until someone closes and reopens it, and the repository setting above must
be on. Documented in the generated README ("Continuous integration and
releases") and `docs/contributing.md`, where the token already appears.

---

## 6. Migration scripts — `updates/`

Some template changes cannot be expressed as a merge: a file that moves,
a setting that changes shape. The template ships versioned scripts:

```
updates/
  README.md            # this contract, for contributors
  v0.13.0/
    before.py          # runs on the project's tree before the merge
    after.py           # runs after the merge is committed
```

Contract, enforced by the runner and documented in the root
`docs/contributing.md`:

- Directory names are `vX.Y.Z`, the version whose update they belong to.
  Either file may be absent.
- Run with `uv run python <script>`, working directory the project root,
  `PYFR_UPDATE_FROM` and `PYFR_UPDATE_TO` in the environment. Standard
  library only: the project's environment may contain nothing else.
- `before.py` moves things so the merge lines up — typically `git mv` via
  `subprocess` — and may edit files; the tool commits what it leaves.
  `after.py` rewrites contents once the template's version of a file is
  in place; the tool commits what it leaves.
- Idempotent: running twice equals running once. A failed update is
  re-run, and a script that already did its work must exit 0 without
  doing it again.
- Exit non-zero to stop the update. The message is shown to the user.
- One `updates/<version>/` per template release that needs one; M8 ships
  the runner and `updates/README.md`, and no script — nothing between
  v0.10.0 and the M8 releases moves a file.

A migration script is tested in the template repository the same way the
end-to-end test in section 8.2 tests its fixture scripts: generate at the
previous version, update, assert the tree.

---

## 7. Documentation

### 7.1 Generated side

- `docs/guides/update-from-template.md` — running `just update` and
  `just update-check`; reading the output; `.pyfr-update-ignore` and how
  to grow it; finishing a conflicted merge; what the weekly pull request
  and issue mean; what migration scripts do; bootstrapping a project
  generated before this version (`uvx --from pyfr-cli@latest pyfr update`
  works on any project with `.pyfr-answers.yml`; a project from before
  v0.7.0 writes the file by hand from the example given); the manual
  re-point procedure when the root commit is gone or the history was
  rewritten (`git branch -f template <sha>`, then `just update`); and
  why the `template` branch is on the remote and must not be deleted.
- `docs/reference/commands.md` — rows for `just update` and
  `just update-check`.
- `docs/contributing.md` — the workflow, next to the other three, and the
  widened `RELEASE_TOKEN`.
- `README.md` — the token's permissions and the repository setting.
- `docs/glossary.md` — the vendor branch entry already exists; it gains
  "on the remote".

Every new page carries `last_reviewed` and `covers:` front matter as the
hygiene scripts require.

### 7.2 Root side

- `docs/adr/0018-the-updater-is-a-published-cli.md` — decision M8-1 and
  M8-3: a published `pyfr-cli` run at the target version, and the
  `template` branch on the remote. Alternatives: a script inside each
  project; a local-only branch rebuilt from the root.
- `docs/contributing.md` — writing a migration script (section 6), and
  the `pyfr-cli` package: where it lives, how it is tested, how it is
  released.
- `docs/roadmap.md`, `docs/index.md`, `README.md` — M8 done; the status
  line becomes "M0–M8 done"; the three-phase table's phase C is no longer
  future tense.
- `docs/glossary.md` — `pyfr-cli`, Trusted Publishing.
- The master spec gains a short amendment note at the top of section 11.2
  pointing here for the remote branch, as M7 amended earlier sections.

---

## 8. Tests

### 8.1 Unit tests — every push, seconds

`tests/pyfr_cli/`, one file per module:

- `versions`: parse a fixed `git ls-remote` output; the newest `vX.Y.Z`
  wins; `v1.0.0-rc1` and `latest` are ignored; `--to` with and without
  `v`; equal → current; lower → refused.
- `vendor`: on repositories built in `tmp_path` — one root passes, two
  roots refuse; the guard accepts root + trailer commits and refuses a
  hand-made commit at the tip; the branch's version comes from the
  trailer, or from the root's answers file.
- `ignore`: every pattern shape (file, `dir/`, `*`, `**`, `!`), the file
  ignoring itself, the built-in default rendered for postgres and for
  none.
- Sync: copy, delete, ignore, empty-directory removal, against fixture
  directories.
- `migrate`: the `(from, to]` range and its order; `before` then `after`;
  a non-zero exit stops; both environment variables arrive.
- `changelog`: the `(A, B]` sections from a Commitizen-format fixture.
- `answers`: a missing key, a missing file, the `v`-less version.
- `state`: write, read, delete; found through `--git-dir` in a worktree.
- `__main__`: exit codes 0/1/2, `update-check --json`, every precondition
  message.

### 8.2 End-to-end update test — every push, tens of seconds

`tests/test_update_e2e.py`. Network-free. Fixtures build, in `tmp_path`:

- **A local template remote**: a git repository holding a copy of this
  checkout's `cookiecutter.json`, `hooks/`, `{{cookiecutter.project_slug}}/`,
  `CHANGELOG.md` and `updates/`, committed and tagged `v100.0.0` —
  far above any real version, `_template_version` rewritten to match.
- **A second version**, tagged `v100.1.0`: a template-owned line changed
  (in `ruff.toml`), a file added, a file removed, a prompt added with a
  default, `CHANGELOG.md` extended, and `updates/v100.1.0/before.py`
  (a `git mv` of a template-owned file) and `after.py` (a content
  rewrite of the moved file).
- **A project** rendered at `v100.0.0` with `PYFR_REGEN=1`, then
  `git init`, `git add -A`, one commit — Backstage's publish path (master
  spec 11.7), and no `uv sync`. A bare repository as `origin`, pushed.
- **The team's first week**, scripted: delete the example slice's files
  *outside* the ignore list (the case master spec 11.3 built the whole
  mechanism for); edit `README.md`; add a dependency line to
  `pyproject.toml`; edit a line in the file `before.py` will move.

Scenarios, each a test:

1. **Clean update** to `v100.1.0`: exit 0; the deletions stayed deleted;
   the README edit and the dependency line survived; the `ruff.toml`
   change, the new file and the removal arrived; the moved file kept the
   team's edit and got `after.py`'s rewrite, in a separate commit;
   `.pyfr-answers.yml` records `100.1.0` and the new prompt's default;
   `origin/template`'s tip carries the trailer; a second `pyfr update`
   prints "already current"; `update-check` exits 0.
2. **Squash-merge survival**: squash the merge commit into one ordinary
   commit (`git reset --soft` to the pre-merge commit, commit), tag
   `v100.2.0` on the remote with one more template change, update again —
   exit 0, no conflict, because the merge base was pinned to the template
   commit at the recorded version, which `origin/template` keeps alive
   (section 4.7). This is the proof of decision M8-3 and of the pinned
   base.
3. **Conflict and resume**: edit the `ruff.toml` line the template also
   changes; update → exit 1; `conflict: ruff.toml` printed;
   `.pyfr-answers.yml` staged at the new version; the state file exists;
   resolve, `git add`, `git commit`; `pyfr update` again → `after.py`
   ran, its commit exists, the state file is gone, exit 0.
4. **Fresh clone**: clone the project from `origin` into a new directory,
   no local `template`; update → it fetched `origin/template`.
5. **Guard**: a hand-made commit on `template` → exit 2 with the how-to's
   message; the working tree untouched.
6. **No ignore file**: a project without `.pyfr-update-ignore` — in
   PR 1 every fixture project, since the template body gains the file
   only in PR 2; from PR 2 on, the test deletes it and commits first —
   updates with the built-in default applied (the README edit survived),
   and from PR 2 on the file arrives with the update.

Cookiecutter renders take about a second each; the suite stays well under
a minute and runs with `just test`.

### 8.3 Generation tests

In `tests/test_generation.py`: `.pyfr-update-ignore` has the
`migrations/` and `schema.sql` lines exactly when `database` is `postgres`;
`template-update.yml` and `docs/guides/update-from-template.md` exist in
every combination; the existing "every rendered `justfile` parses" test
covers the two recipes. The golden diff covers `examples/reference-service`
once `just regen` has run.

### 8.4 Packaging

A step in the root CI's `check` job, after `just test`: `uv build`, then
`uvx --from dist/*.whl pyfr --version` must print the version. A shell
step, not a pytest test — it needs the network to resolve the wheel's
dependencies.

### 8.5 Not tested automatically

- The PyPI publish: verified by the first release after PR 1.
- The workflow's `gh` steps: the shell is thin and every branch is a
  tested exit code. Verified once by `workflow_dispatch` on a freshly
  generated project as the last step of PR 2.
- The full-suite tests stay as they are: `just update-check` against real
  PyPI works only after the first publish and needs the network, so it is
  not added to them.

---

## 9. Delivery — three pull requests

Each releasable on its own, in this order; each merge releases.

| PR | Title | Contents | Releases |
|---|---|---|---|
| 1 | `feat: add pyfr-cli with pyfr update and update-check` | `src/pyfr_cli/`; the packaged root `pyproject.toml` and its comment; `updates/README.md`; unit and end-to-end tests; `mypy` in `just lint`; the wheel step in CI; the `publish-pypi` job. Nothing under `{{cookiecutter.project_slug}}/` changes. **The pending publisher on pypi.org is registered before this merges.** | v0.11.0, and `pyfr-cli 0.11.0` on PyPI |
| 2 | `feat: let a generated project update itself from the template` | The two recipes; `.pyfr-update-ignore`; `template-update.yml`; the guide, the commands rows, the token documentation; generation tests; `just regen`. Ends with the `workflow_dispatch` verification on a real generated project. | v0.12.0 |
| 3 | `docs: close m8` | ADR 0018; the root contributing guide; roadmap, index, README, glossary; the master spec's amendment note; whatever the verification in PR 2 turned up. | None by itself: `docs:` commits do not bump (`release.yml` treats Commitizen's exits 3 and 21 as a no-op). A `fix:` from the verification would make it a patch release. |

PR 2's `uvx --from pyfr-cli@latest` works because PR 1's release already
published. Each PR links an issue, is assigned, and carries a Conventional
Commits title — the repository's rules.

---

## 10. Error handling

- Every error: one line of cause, one line of fix, stderr, exit 2. No
  stack trace unless `PYFR_DEBUG` is set.
- The working tree is never left half-changed. Rendering and syncing
  happen in temporary directories and the `template` worktree; both are
  removed in a `finally`, and `git worktree prune` at the start of a run
  clears a killed run's leftovers. The only working-tree mutations are
  the before-scripts (committed before the merge), git's own merge
  (recoverable with `git merge --abort`), the staged answers file, and
  the after-scripts (committed). Because a clean tree is a precondition,
  `git reset --hard HEAD` is always a safe recovery from a failed script,
  and the error message says so.
- A rejected push of `template` stops the run before the merge; the local
  branch is correct and a re-run fetches, finds it current, and continues.
- A killed run mid-merge leaves git's ordinary merge state and the state
  file; the next run reads both (section 4.8).
- The tool never prompts. Every input is an argument, an environment
  variable or a file.

---

## 11. Risks

| Risk | Mitigation |
|---|---|
| Trusted Publishing not registered when PR 1 merges | Only `publish-pypi` is red; it is last and nothing depends on it; the how-to for contributors names the pypi.org step. |
| A non-pristine root commit (the first commit was amended before the first push) | The wrong merge base once; the first run prints the commit it used; the how-to's re-point procedure. |
| `uvx --from pyfr-cli@latest` spelling differs across `uv` versions | Verified in the plan against the `uv` the generated project pins; `--refresh-package` is the fallback. |
| A team's `pyproject.toml` edit collides with the template's | An ordinary line-level merge conflict, resolved once; the ignore file is not the answer, because the file must keep receiving template fixes. |
| `origin/template` deleted by a tidy-up | The guide says not to. The tool then recreates the branch from the root and stops with exit 2 before the working tree changes — the branch's version is below the recorded one (section 4.3) — naming the guide's re-point procedure (`git branch --force template <the last template commit>`); it does not merge against the wrong base. |
| The weekly workflow opens the same pull request or issue twice | Both steps look for an open one first. |
| `pathspec` semantics differ from git's in an edge case | The unit tests pin the patterns the default uses; anything exotic a team adds is theirs to check with `git check-ignore`'s equivalent, documented. |

---

## 12. Out of scope for M8

- `pyfr new` — `uvx cookiecutter gh:EmadMokhtar/pyfr` stays the way to
  generate.
- Downgrades.
- Updating across template forks beyond `--template`.
- Writing the pre-v0.7.0 answers file automatically.
- Any real `updates/<version>/` script; none is needed yet.
- Adding `just update-check` to the full-suite tests (section 8.5).
- Kubernetes, devcontainers and the rest of M9.

---

## 13. Departures from the master spec

| Master spec | This document | Why |
|---|---|---|
| 11.2: the `template` branch is local and rebuilt from the root on demand | On the remote, pushed before every merge (4.3) | Squash merges destroy the merge commit; the second update needs the first's template commit. |
| 11.3: `PYFR_REGENERATE` | `PYFR_REGEN` | The variable M7 actually implemented. |
| 11.4: the default ignore list | Adds `uv.lock`, `openapi.baseline.json`, `.pyfr-update-ignore` (5.2) | The render has no lock; the baseline is promoted by the project's release; the ignore file is the team's. |
| 11.5: scripts "run with `uv run`" | `uv run --no-project python <script>`, standard library only, output committed by the tool (6) | The project's environment may hold nothing else; the merge needs a clean tree. |
| 11.6: the updater is unspecified; `docs/how-to/` | A published `pyfr-cli` (3); `docs/guides/` | Decision M8-1; the directory M7 actually created. |
| 11.3: nothing about resuming | `.git/pyfr-update.json`, one command (4.8) | A conflicted merge is finished by the user; the after-scripts still have to run. |

---

## 14. Glossary

| Term | Meaning |
|---|---|
| Vendor branch | A branch holding pristine upstream output and nothing else, merged in to receive upstream changes. Here: `template`. |
| Merge base | The commit both sides of a merge descend from — the last state they agreed on. |
| Three-way merge | Combining two versions of a tree by comparing each against their common base; a change made on one side only is taken without asking. |
| Squash merge | Merging a pull request as one new commit that carries the result but none of the branch's commits. |
| Worktree | A second checkout of the same repository, in another directory, on another branch. |
| Shallow clone | A clone with one commit and no history (`--depth 1`). |
| Trailer | A `Key: value` line at the end of a commit message, like `Signed-off-by:`. Here: `Pyfr-Template-Version:`. |
| Console script | A command installed with a Python package; `pyfr` is `pyfr-cli`'s. |
| `uvx` | Runs a Python tool in a throwaway environment without installing it in the project. |
| Trusted Publishing | PyPI accepting a short-lived identity token from a CI provider (here GitHub Actions, through OpenID Connect) instead of a stored API token. |
| OpenID Connect (OIDC) | An identity protocol; here, the way GitHub proves to PyPI which repository and workflow is publishing. |
| hatchling | A small, standard Python build backend — the tool that turns a source tree into a wheel. |
| Wheel | Python's built package format, what PyPI serves. |
| `pathspec` | A pure-Python library implementing gitignore pattern matching. |
| gitignore syntax | The pattern language of `.gitignore`: `dir/`, `*`, `**`, `!` negation, `#` comments. |
| Idempotent | Running it twice has the same effect as running it once. |
| Fine-grained personal access token | A GitHub token limited to named repositories and named permissions. |
| Pending publisher | A Trusted Publishing registration on pypi.org made before the project's first upload. |
