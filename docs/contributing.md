---
last_reviewed: 2026-09-11
covers:
  - scripts/check_docs_updated.py
  - scripts/check_docs_freshness.py
  - scripts/check_doc_examples.py
---

# Contributing

## Repository layout

```
pyfr/
  docs/                        this site
    superpowers/               design specs and plans; not published
  examples/reference-service/  the reference service
  scripts/                     repository tooling
  mkdocs.yml  pyproject.toml   documentation site and its toolchain
  justfile                     documentation commands
  .github/workflows/           continuous integration and publishing
```

The repository root and the reference service are **two separate Python
projects**, each with its own `pyproject.toml`, and they are never synced
together. The root project holds only the documentation toolchain; it is not
a package and nothing is published from it.

## Working on the reference service

From `examples/reference-service/`:

```bash
uv sync && uv run pre-commit install
```

```bash
just check
```

`just check` is the one command to run before pushing: lint, type-check, the
import rule, tests, the git hooks, and a check that nothing was rewritten.
Every recipe is listed in [Commands](reference/commands.md).

`.python-version` pins the interpreter to 3.13, so `uv sync` uses the same one
continuous integration does. There is no separate setup step and no drift
between your machine and the pipeline.

Development is test-driven: write the failing test first, then the
implementation. See [Testing strategy](explanation/testing.md).

## Working on the documentation

From the repository root:

```bash
just docs-install
```

```bash
just docs
```

That serves a live preview on <http://127.0.0.1:8000> and rebuilds as you
save. Before pushing:

```bash
just docs-build
```

That is `mkdocs build --strict`, exactly as continuous integration runs it. A
link to a page that no longer exists, a renamed heading anchor, or an
unresolvable include each fails the build rather than printing a warning
nobody reads.

Adding a page means adding it to `nav:` in `mkdocs.yml`. A page absent from
the navigation is unreachable.

### `docs/superpowers/` is an archive

It holds the design specification and the milestone implementation plans. They
stay in the repository — they are the reasoning behind what this site
describes — but `mkdocs.yml` excludes them from the published site. They are
working documents, thousands of lines long, and out of date by design once a
milestone lands.

Do not treat editing one as documenting a change. The freshness check below
deliberately does not count it.

## Documentation ships with the change

Four independent mechanisms enforce this, and each catches something
different.

**`scripts/check_docs_updated.py`** is a hard gate. It fails a pull request
that changes `examples/reference-service/src/**` without touching `docs/`,
`README.md`, or `mkdocs.yml`. It is a blunt heuristic, on purpose: it cannot
tell a stale sentence from a fresh one, it only notices that source changed
and no documented surface did. A pure refactor or a dependency bump will trip
it, and that is the accepted cost of catching the case that matters. The
escape hatch is the **`no-docs-needed`** label on the pull request — the
workflow re-runs when a label is added, so applying it turns the failed check
green without an empty commit. A label is used rather than a commit message
trailer because pull requests are squash-merged, which rewrites the message.

**`scripts/check_docs_freshness.py`** only warns; nothing it finds can fail a
build. It reports two things: a page whose `covers:` frontmatter names a path
that changed in this pull request while the page itself did not, and a page
whose `last_reviewed` date is more than 180 days old. Where the hard gate
above only notices that *some* source changed and *no* documentation did,
this one names the page and the exact path that moved.

**`lychee` and `mkdocs build --strict`** are hard gates on links, not on
prose. `--strict` fails the build on a link to a page that no longer exists,
a renamed heading anchor, or an unresolvable include. `lychee` does the
equivalent check for links leaving the site, against the real internet, in
its own CI job — kept separate from the site build so a network blip reads as
a network blip, not as a broken site.

**`scripts/check_doc_examples.py`** is a hard gate on behaviour rather than
prose: it runs every `curl` example marked `<!-- exec -->` against a real,
running service (`just docs-examples` starts the full compose stack, runs
the script, then tears the stack down whether it passed or failed) and
fails on the first example whose commands do not succeed. Where the other
three mechanisms ask "did the right files change together", this one asks
"does the documented example still work" — a stale sentence is a nuisance,
but a `curl` example that 404s is a reader concluding the service itself is
broken. It is not part of `just check-all`; it runs as its own
`docs-examples` job in CI, against a stack that job starts itself.

### The `<!-- exec -->` marker

A fenced block opts into `check_doc_examples.py` by putting the literal
line `<!-- exec -->` on its own line, immediately before the block's
opening fence:

    <!-- exec -->
    ```bash
    curl -si http://localhost:8000/healthz
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
runnable example anywhere under `docs/` (outside `docs/superpowers/`,
which this check does not scan) needs the marker and has to satisfy both
rules above.

### `just docs-freshness` is not CI's `docs-freshness` job

These share a name and run different scripts, which makes it easy to reach
for the wrong one while reproducing a red pull request.

The CI job named **`docs-freshness`** runs `scripts/check_docs_updated.py` —
the hard gate above. The **`just docs-freshness`** recipe runs
`scripts/check_docs_freshness.py` — the advisory warnings above, which is
what CI's separate **`docs-warnings`** job calls. Reproduce a red
`docs-freshness` check locally with:

```bash
python3 scripts/check_docs_updated.py origin/main HEAD
```

not with `just docs-freshness`. That recipe runs the other script, never
fails, and will tell you nothing about why the hard gate is red.

### When the warnings become failures

Not yet, and not on their own. Flipping `check_docs_freshness.py`'s two
warnings to hard failures needs all three of the following to be true first,
checkably:

- **Every published page carries `covers:` wherever a genuine coupling
  exists.** A warning that never fires because nothing declares the coupling
  is not evidence the check works — it is evidence nobody wrote the
  frontmatter yet.
- **A month of pull requests has passed with the warnings producing no noise
  that nobody acted on.** Verified by reading the pull requests, not assumed.
- **The team has agreed to retire `check_docs_updated.py` in the same
  change.** Keeping both as hard gates means one pull request can fail twice
  for the same reason, under two different names, with two different fixes.

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

This is not a style preference. Release automation derives the next version
number and the changelog from commit history, so a non-conforming message
silently breaks the release. Because pull requests are **squash-merged**, the
pull request title becomes the commit on `main` — so the title is what that
automation actually reads.

The commit-message hook is installed by `uv run pre-commit install` in the
reference service, which wires up both the `pre-commit` and `commit-msg`
stages.

## One-time repository settings

Five settings live in the GitHub interface, not in this repository, so they
are easy to miss when standing up a fork.

- **Settings → Pages → Source = "GitHub Actions".** Without it the `Docs`
  workflow's build job succeeds while its deploy job fails with an opaque
  error, and every published documentation link stays dead.
- **A `no-docs-needed` label must exist**, or the freshness check has no
  escape hatch.
- **Squash-merge as the merge strategy**, since the commit convention above
  assumes the pull request title becomes the commit on `main`.
- **Settings → Actions → General → Workflow permissions → "Read and write
  permissions".** The `Release` workflow (`.github/workflows/release.yml`)
  pushes a tag (and, after the first release, a bump commit carrying the
  version, the changelog and the promoted API contract baseline) back to
  `main`.
  With the default read-only permission, that push fails with a 403 error —
  and it fails *after* `cz bump` has already created the commit and tag in
  the runner's local checkout, so the run looks like it did most of the work
  before dying on something that reads like a permissions typo rather than a
  missing setting.
- **Branch protection on `main`, if enabled, must let the release push
  through.** A protected `main` rejects a push from the default
  `GITHUB_TOKEN` the same way it would reject one from any other
  contributor, so every release fails at the push step with no tag ever
  reaching origin. Either exempt the `github-actions[bot]` actor in the
  protection rule, or supply a personal access token or a GitHub App
  installation token that is exempt. Whichever route is chosen, the token
  that matters is the one passed to the `actions/checkout@v4` step, not the
  one used later for `gh release create`: `git push` uses the credentials
  `checkout` wired into the local git config, so replacing only the
  `gh release create` token changes nothing.

### The first release run is not like the others

This repository starts with no git tags at all, so its very first run of
`.github/workflows/release.yml` cannot use Commitizen's normal path: `cz
bump` needs a prior tag to diff against to compute the next version, and
there isn't one yet. That first run instead tags the current version —
`v0.5.0`, already on disk in `pyproject.toml` — directly, with **no bump
commit and no change to `CHANGELOG.md`**, because there is nothing to
bump: `CHANGELOG.md` already describes `v0.5.0`, generated from the
commit history that produced it.

So a tag appearing on `main` with no accompanying version-bump commit is
the **correct** result of that first release, not a stuck or partial run —
see the "Bump the version and write the changelog" step's own comment in
`release.yml` for the two ways `cz bump` was confirmed to fail outright
with zero tags. Every release after the first finds a tag to diff against
and takes the normal `cz bump` path, exactly as Commitizen documents it.
