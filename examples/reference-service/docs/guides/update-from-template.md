---
last_reviewed: 2026-09-15
covers:
  - justfile
  - .pyfr-answers.yml
  - .pyfr-update-ignore
  - .github/workflows/template-update.yml
---

# Update from the template

This project was generated from [PyFr](https://github.com/EmadMokhtar/pyfr)
at the version `.pyfr-answers.yml` records. The template keeps improving —
CI workflows, container images, the observability wiring, the gates — and
`just update` brings those improvements in without touching what is
yours.

## How it works

An update is an ordinary three-way git merge (a merge that compares both
sides against the last state they agreed on). The tool behind it,
`pyfr-cli`, runs from PyPI through `uvx`, so nothing is installed in this
project:

1. It reads `.pyfr-answers.yml` — the answers this project was generated
   with, and the template version it is at.
2. It renders the template at the target version with those answers, and
   commits the result on a branch named `template`: pristine template
   output, nothing else. That branch is pushed to `origin`; every machine
   that updates this project needs it, so do not delete it.
3. It merges `template` into your branch. Files you changed and the
   template did not keep your version; files the template changed and you
   did not receive the template's; a file you deleted stays deleted. Only
   a line both sides changed conflicts.
4. It records the new version in `.pyfr-answers.yml`.

The paths in `.pyfr-update-ignore` are never touched — see below.

## Running it

```bash
just update
```

updates to the newest template release. To pin a version:

```bash
just update v0.12.0
```

Both need the network. A clean update leaves one merge commit,
`chore: update template vA -> vB`, whose body lists what changed in the
template — plus a `chore: prepare …` or `chore: finish …` commit when the
release shipped a migration script. Run `just check`, then push.

`just update-check` exits 1 when a newer version exists and 0 when this
project is current. The weekly workflow runs the same check, `pyfr
update-check` through `uvx`, as its first step.

## When the merge conflicts

The update stops with exit 1 and lists the files:

```
conflict: pyproject.toml
merge: conflicts in the files above
  1. resolve them, then stage them:  git add <the files>
  2. commit the merge:               git commit --no-edit   (the message is prepared)
  3. run the same command again:     pyfr update  (runs what is left)
```

Resolve each file as in any merge, `git add` it, and commit with
`git commit --no-edit` — `--no-edit` keeps the prepared message; an editor
would strip its `#` headings. Then run `just update` again: it finishes
what is left (the release's `after.py` migration scripts) and records the
version. `git merge --abort` puts everything back if you want to stop.

## What is never updated

`.pyfr-update-ignore` lists the paths the update leaves exactly as this
project has them — yours from the first day, or artifacts of your code:
`README.md`, `CHANGELOG.md`, `uv.lock`, the schema, the OpenAPI document
and its baseline, `docs/adr/`, and the example slice under
`src/…/domain/`, `services/` and `api/v1/`. Everything else is
template-owned and receives fixes by default.

The file uses `.gitignore` syntax, one pattern per line, comments on
their own lines (a `#` after a pattern is part of the pattern), every
pattern anchored with a leading `/`. Add paths as you diverge — a
template-owned file you have rewritten and no longer want fixes for. Do
not add `pyproject.toml` or the workflows to keep a conflict away: a
conflict there is one line to resolve once, and the file keeps receiving
fixes afterwards.

## The weekly pull request

`.github/workflows/template-update.yml` runs every Monday (and on demand).
When a newer template exists it runs the update on a branch named
`pyfr/update-vX.Y.Z`:

- **A clean merge** becomes a pull request titled
  `chore: update template vA -> vB`, with the template's changelog entries
  in its body. CI runs on it like on any other change; review and merge
  it as usual (squash-merge is fine — the tool does not depend on the
  merge commit surviving).
- **Conflicts** become an issue, `chore: template vA -> vB conflicts`,
  naming the files. Run `just update vB` locally: the `template` branch
  is already at `vB` on `origin`, so the run goes straight to the merge.

Nothing is opened twice: the workflow stops when a pull request or issue
for that version is already open.

The workflow pushes with the `RELEASE_TOKEN` secret when the repository
has one, and with its own workflow token otherwise. With the fallback the
pull request still opens, but CI does not start on it — GitHub never runs
workflows for events the workflow token itself caused — so the workflow
leaves a comment: close and reopen the pull request to start CI, or add
`RELEASE_TOKEN`. And when the update changes a file under
`.github/workflows/` — most template releases do — the fallback cannot
push at all: the run fails at its push step with GitHub's `refusing to
allow a GitHub App to create or update workflow` message. The README's
*Continuous integration and releases* says what the token needs (Contents,
Pull requests, Issues and Workflows, read and write) and names the
repository setting the fallback depends on.

## Migration scripts

Some template changes cannot be expressed as a merge — a file that moves,
a setting that changes shape. The template ships a script for those under
`updates/<version>/` in its own repository; `just update` runs them for
every version between yours and the target, before the merge (`before.py`)
and after it (`after.py`), and commits what they change. They are standard
library only and idempotent: an interrupted update is simply run again, so
a script may run more than once for the same version and must do nothing
the second time.

## A project generated before the update tooling existed

Every project generated from PyFr v0.7.0 or later has `.pyfr-answers.yml`,
which is all the tool needs. `just update` first appeared in a later
template version; until this project has the recipe, run the tool directly
from the project root:

```bash
uvx --from pyfr-cli@latest pyfr update
```

The update brings the recipe, this page and `.pyfr-update-ignore` with
it; a project without an ignore file is updated with the tool's built-in
default, which is the same list.

A project generated before v0.7.0 has no answers file. Write one by hand
at the project root, with the answers you generated with and the version
you generated from, then run the command above:

```yaml
_template: https://github.com/EmadMokhtar/pyfr
_template_version: "0.6.0"
project_name: "My Service"
project_slug: "my-service"
package_name: "my_service"
description: "A Python microservice."
author_name: "Your Name"
author_email: "you@example.com"
github_org: "your-org"
database: "postgres"
cache: "redis"
object_storage: "s3"
http_port: "8000"
license: "Apache-2.0"
```

## When the `template` branch is wrong

The tool refuses to run when the `template` branch is not what it
expects, and says so. The cases, and the way out:

- **"template's tip … was not made by pyfr update"** — someone committed
  on the branch by hand. Point it back at the last commit the tool made,
  which the message names: `git branch --force template <sha>`.
- **"the repository has N root commits"** or a rewritten history — the
  tool creates `template` from the repository's first commit, which for a
  generated project is unmodified template output. When that commit is
  gone (a squashed or imported history), point the branch at the commit
  closest to pristine template output that you have, accept one noisier
  merge, and the tool maintains the branch from there:
  `git branch --force template <sha>`, then `just update`.
- **"the local template branch … and origin/template have diverged"** —
  another machine pushed the branch. The remote's version is the one every
  machine uses: `git branch --force template origin/template`.
- **"template is checked out in another worktree"** — a worktree you made
  holds the branch. Save what it holds, `git worktree remove <path>`, run
  again.

Never delete `origin/template`: it holds the commit the next merge is
based on. If it is gone, the tool stops and names this section.

## Trust

`just update` runs code from the template repository — cookiecutter's
hooks and the migration scripts — with your permissions. `_template` in
`.pyfr-answers.yml` must name a repository you trust; the same goes for
`--template`, the one-run override.
