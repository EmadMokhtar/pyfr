---
last_reviewed: 2026-09-14
covers:
  - justfile
  - .pre-commit-config.yaml
  - .github/workflows/ci.yml
  - scripts/check_docs_updated.py
  - scripts/check_docs_freshness.py
  - scripts/check_doc_examples.py
---

# Contributing

This page is about working on `{{ cookiecutter.project_slug }}` itself:
what to run before you push, how the documentation is kept true, and the
commit convention the release depends on. The service's design is in
[Architecture](explanation/architecture.md); the reasoning behind each
decision is in the [decision records](adr/README.md).

## Before you push

Set the project up once:

```bash
uv sync && uv run pre-commit install
```

`.python-version` pins the interpreter to 3.13, so `uv sync` uses the same
one continuous integration does. There is no separate setup step and no
drift between your machine and the pipeline. `pre-commit install` wires
up both hook stages: `pre-commit` (formatting, linting, secrets) and
`commit-msg` (the commit convention below).

Development is test-driven: write the failing test first, then the
implementation. [Testing strategy](explanation/testing.md) describes the
tiers and what each one is for.

Then, before every push:

```bash
just check
```

That is `lint`, `typecheck`, `imports`, `test` and `precommit`, followed by
`git diff --exit-code` — two pre-commit hooks can modify files, and the
diff turns a hook that changed the tree into a loud failure instead of a
silent pass on the second run. It needs no Docker and finishes in a couple
of minutes. CI's `check` job runs exactly this.

Before a pull request that touches an adapter, a generated file, the API
contract or observability:

```bash
just check-all
```

That is `check`, then `docs-build`, `test-integration`, `gates`,
`o11y-gates` and `contract-gates` — the six gates CI runs as separate
jobs (`check`, `docs`, `integration`, `gates`, `o11y-gates` and
`contract`), in one local command. It needs Docker: the integration tier
starts real containers, and the contract gate runs `oasdiff` in one.

`just security` is the other check worth running before a pull request that
touches a dependency or a Dockerfile. It builds every image this project
ships, audits `uv.lock` with pip-audit, scans each image with Trivy and
writes a software bill of materials per image — the same four recipes
CI's `security` job runs. It needs Docker, and it is deliberately **not**
part of `just check-all`: its result changes without a commit, because an
advisory can be published overnight against a version that is already
locked. `security` can turn red on a re-run of an unchanged branch — that
is normal, and the [runbook](runbook.md#security-is-red-on-a-pull-request)
says what to do with it. [Supply chain](reference/supply-chain.md)
describes each step.

## Documentation ships with the change

Four independent mechanisms enforce this, and each catches something
different. All four run in `.github/workflows/ci.yml`, and each has a
`just` recipe or a script you can run locally.

**`scripts/check_docs_updated.py`** is a hard gate: CI's **`docs-freshness`**
job. It fails a pull request that changes `src/` without touching `docs/`,
`README.md` or `mkdocs.yml`. It is a blunt heuristic, on purpose: it cannot
tell a stale sentence from a fresh one, it only notices that source changed
and no documented surface did. A pure refactor or a dependency bump will
trip it, and that is the accepted cost of catching the case that matters.
The escape hatch is the **`no-docs-needed`** label on the pull request —
the workflow re-runs when a label is added, so applying it turns the failed
check green without an empty commit. A label is used rather than a commit
message trailer because pull requests are squash-merged, which rewrites the
message. Reproduce a red check locally with:

```bash
python3 scripts/check_docs_updated.py origin/main HEAD
```

**`scripts/check_docs_freshness.py`** only warns; nothing it finds can fail
a build. It is what `just docs-freshness` runs, and what CI's
**`docs-warnings`** job calls. It reports two things: a page whose `covers:`
front matter names a path that changed in this pull request while the page
itself did not, and a page whose `last_reviewed` date is more than 180 days
old. Pages under `docs/adr/` are skipped: a decision record does not go
stale. Where the hard gate above only notices that *some* source changed
and *no* documentation did, this one names the page and the exact path
that moved.

**`lychee` and `mkdocs build --strict`** are hard gates on links, not on
prose. `--strict` fails the build on a link to a page that no longer
exists, a renamed heading anchor, or an unresolvable include; `just
docs-build` runs it, and so do CI's **`docs`** job and `docs.yml` before a
deploy. `lychee` does the equivalent check for links leaving the site,
against the real internet, in its own **`links`** job — kept separate from
the site build so a network blip reads as a network blip, not as a broken
site. `just links` runs the same check locally, given a `lychee` binary,
against the same `lychee.toml`.

**`scripts/check_doc_examples.py`** is a hard gate on behaviour rather than
prose: it runs every `curl` example marked `<!-- exec -->` against a real,
running service. `just docs-examples` starts the compose stack in its own
Compose project, runs the script, then tears the stack down whether it
passed or failed. The script runs every example and fails if any does not
succeed. Where the other three mechanisms ask "did the right files change
together", this one asks "does the documented example still work" — a
stale sentence is a nuisance, but a `curl` example that 404s is a reader
concluding the service itself is broken. It is not part of `just
check-all`; it runs as its own **`docs-examples`** job in CI, against a
stack that job starts itself.

### Front matter

Every page under `docs/` opens with YAML front matter, and the freshness
script reads two keys from it:

```yaml
---
last_reviewed: 2026-09-14
covers:
  - justfile
  - src/{{ cookiecutter.package_name }}/settings.py
---
```

`last_reviewed` is the date someone last read the page against the code;
set it when you write or review a page. `covers:` lists the paths the page
describes, relative to the project root, so a change to one of them without
a change to the page can be reported; a directory prefix covers everything
under it. Leave `covers:` out when a page tracks no particular file.

### The local loop

```bash
just docs-install
```

```bash
just docs
```

That serves a live preview on <http://127.0.0.1:8001> and rebuilds as you
save. Before pushing:

```bash
just docs-build
```

Adding a page means adding it to `nav:` in `mkdocs.yml`. A page absent from
the navigation is unreachable.

### The `<!-- exec -->` marker

A fenced block opts into `check_doc_examples.py` by putting the literal
line `<!-- exec -->` on its own line, immediately before the block's
opening fence:

    <!-- exec -->
    ```bash
    curl -si http://localhost:{{ cookiecutter.http_port }}/healthz
    ```

Most fenced blocks in this documentation are not runnable — a file's
contents, a fragment of output, a command that would modify the reader's
own machine — so the marker is opt-in rather than "every bash fence": that
keeps the runnable set small enough to trust, instead of a wall of
exclusions for everything that is not meant to run.

A marked block must satisfy two rules. The check's own execution model
takes care of the first one; the second is not enforced by anything and
has to be got right by hand:

- **Self-contained.** Each marked block genuinely runs as its own `bash
  -euo pipefail` invocation, with nothing carried over from an earlier
  block — no shared shell variable, no earlier `cd`. A block that depends
  on state a previous example left behind fails on its own, since that
  state was never there to begin with.
- **Assert something; do not merely run something.** `curl` on its own
  exits `0` on an HTTP error response — a 404 or a 500 is still a
  "successful" `curl` invocation as far as the shell is concerned, and
  the check only looks at the shell's exit code. A marked block has to
  check the response itself and fail the shell if it does not match, the
  way the examples in [Getting started](getting-started.md) capture the
  response and then `grep -q ... <<< "$response"` against the status line
  and body. `curl -f` is the single-command version of the same rule when
  only the status code matters.

If every `<!-- exec -->` block is ever removed from `docs/`, the check
fails on purpose: "no examples found" is treated as a bug — the marker
was renamed, or the examples were deleted — never as a silent pass. A new
runnable example anywhere under `docs/` needs the marker and has to
satisfy both rules above. Do not make one depend on seeded data: the ids
`just up` seeds differ per machine, and `just docs-examples` starts its
stack without the seed.

### `just docs-freshness` is not CI's `docs-freshness` job

These share a name and run different scripts, which makes it easy to reach
for the wrong one while reproducing a red pull request.

The CI job named **`docs-freshness`** runs `scripts/check_docs_updated.py` —
the hard gate above. The **`just docs-freshness`** recipe runs
`scripts/check_docs_freshness.py` — the advisory warnings above, which is
what CI's separate **`docs-warnings`** job calls. Reproduce a red
`docs-freshness` check with the `python3` command above, not with `just
docs-freshness`. That recipe runs the other script, never fails, and will
tell you nothing about why the hard gate is red.

### When the warnings become failures

Not yet, and not on their own. Flipping `check_docs_freshness.py`'s two
warnings to hard failures needs all three of the following to be true first,
checkably:

- **Every published page carries `covers:` wherever a genuine coupling
  exists.** A warning that never fires because nothing declares the coupling
  is not evidence the check works — it is evidence nobody wrote the
  front matter yet.
- **A month of pull requests has passed with the warnings producing no noise
  that nobody acted on.** Verified by reading the pull requests, not assumed.
- **The team has agreed to retire `check_docs_updated.py` in the same
  change.** Keeping both as hard gates means one pull request can fail twice
  for the same reason, under two different names, with two different fixes.

The switch is deliberate and not taken here, because a large refactor
trips path coupling across many pages at once, which lands exactly when a
team is busiest.

## Conventional Commits are required

Every commit message **and** every pull request title must follow
[Conventional Commits](https://www.conventionalcommits.org/):

```
<type>[optional scope][!]: <description>
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `perf`, `build`, `ci`,
`chore`, `style`, `revert`. Imperative mood, lowercase, no trailing full stop.

```
docs: explain the shutdown deadline mismatch
fix(api): return 422 instead of 500 for mixed currencies
feat!: require APP_ENVIRONMENT to be set explicitly
```

This is not a style preference. `release.yml` derives the next version
number and the changelog from commit history, so a non-conforming message
silently breaks the release. Because pull requests are **squash-merged**,
the pull request title becomes the commit on `main` — so the title is what
that automation actually reads. A `!` marker has a second reader: the
contract gate treats a commit range with one as a declared breaking change
— see [The API contract](reference/contract.md).

The commit-message hook is installed by `uv run pre-commit install` — see
[Before you push](#before-you-push) — which wires up both the `pre-commit`
and `commit-msg` stages.

The hook runs Commitizen, and Commitizen comes from `uv.lock`, not from a
version pinned in the hook configuration: the hook's command is `uv run
--locked cz`, so the tool that checks a message is the same version that
later decides the release. `commitizen` is pinned exactly, in the `dev`
group of `pyproject.toml`, and that one pin is the only place its version
lives — Dependabot updates it there. `uv sync` installs it; otherwise `uv
run` installs it on first use, which makes the first commit slower than it
needs to be. One pin, in one file Dependabot updates, is the whole point —
see [ADR 0014](adr/0014-dependabot-and-one-pin-per-tool.md).

Two recipes preview what the release will do, without doing it:

| Command | What it does |
| --- | --- |
| `just changelog` | The changelog entry the next release would write, from the Conventional Commits since the last tag. Read-only. |
| `just next-version` | The version the next release would choose. Read-only. Before the first release there is no tag to count from, and the recipe says so: the first run of `release.yml` tags the version on disk as it is. |

## Repository settings

Six settings live in the GitHub interface, not in this repository, and
the workflows need them: the Pages source, a `no-docs-needed` label, a
`RELEASE_TOKEN` secret when a ruleset on `main` requires pull requests,
or for the weekly template update to push workflow changes and run CI,
the Actions permission to open pull requests when that secret is absent,
squash-merge, and making the published container packages public after
the first release. The `README.md` lists all six under *Continuous
integration and releases*, with what goes wrong when each is missing.
The weekly `template-update.yml` is described in [Update from the
template](guides/update-from-template.md).
