---
last_reviewed: 2026-09-13
covers:
  - scripts/check_docs_updated.py
  - scripts/check_docs_freshness.py
  - scripts/check_doc_examples.py
  - scripts/regen.py
---

# Contributing

## Repository layout

```
pyfr/
  docs/                        this site
    superpowers/               design specs and plans; not published
  cookiecutter.json  hooks/       the template's prompts and hooks
  {{cookiecutter.project_slug}}/  the template body — the source of truth
  examples/reference-service/  rendered from the template; never edited by hand
  scripts/                     repository tooling
  mkdocs.yml  pyproject.toml   documentation site and its toolchain
  justfile                     repository commands: docs, tests, regen, adopt
  .github/workflows/           continuous integration and publishing
  .github/dependabot.yml       automated dependency updates
```

The repository root and the reference service are **two separate Python
projects**, each with its own `pyproject.toml`, and they are never synced
together. The root project holds the documentation toolchain and the
template toolchain — cookiecutter, the hooks' and generation tests, the
regeneration script; it is not a package and nothing is published from it.

## Working on the template

From the repository root:

```bash
uv sync --group dev && uv run pre-commit install
```

Edit `{{cookiecutter.project_slug}}/`, then:

```bash
just regen
```

That renders the template with `tests/reference-answers.yaml` into
`examples/reference-service/` and is the only way that directory changes.
It also removes anything in `examples/reference-service/` that the template
does not produce — a stray untracked file included — except `uv.lock` and
git-ignored paths such as `.venv/`, so keep scratch files out of that tree.
`just regen-check` (CI's `golden` job) fails the build when the two
disagree, naming the files. Then run the example's own gates:

```bash
cd examples/reference-service && just check
```

The example's `just precommit` steps aside inside this repository — the
root's `.pre-commit-config.yaml` owns the hooks here, and `just precommit`
at the root runs them over every tracked file.

`just security` is the other check worth running before a pull request that
touches a dependency or a Dockerfile. It builds both images, audits the
service's lockfile with pip-audit, scans both images with Trivy and writes the
software bills of materials — the same four recipes CI's `security` job runs,
which adds the repository root's `just audit` for the documentation
toolchain's lock. It needs Docker, and it is deliberately **not** part of
`just check-all`: its result
changes without a commit, because an advisory can be published overnight
against a version that is already locked. `security` can turn red on a
re-run of an unchanged branch — that is normal, and the
[runbook](runbook.md#security-is-red-on-a-pull-request) says what to do
with it. [Supply chain](reference/supply-chain.md) describes each step.

`.python-version` pins the interpreter to 3.13, so `uv sync` uses the same one
continuous integration does. There is no separate setup step and no drift
between your machine and the pipeline.

Development is test-driven: write the failing test first, then the
implementation. See [Testing strategy](explanation/testing.md).

### Generated files

Three files in the template body are produced by tools, and the tools run
in the example, not in the template: `openapi.json` by `just openapi`,
`.env.example` and `docs/reference/configuration.md` by `just config-docs`.
After a template change that affects one of them — a route, a schema, a
setting — the round trip is: `just regen`, run the tool in
`examples/reference-service/`, then bring the result back into the
template. `just adopt` does that when the tool replaced lines; when it
inserted lines (a new setting, a new endpoint), copy them into the template
file by hand, re-inserting the substitutions the render resolved —
`{{ cookiecutter.project_slug }}` for the contract's `title`, for
instance. `just regen-check` then confirms the two agree.

### Backends and pruning

Three prompts choose which backing services a generated project gets:
`database` (`postgres` or `none`), `cache` (`redis` or `none`) and
`object_storage` (`s3` or `none`). Each list's first entry is cookiecutter's
default, so a `--no-input` render is the "everything on" project — the same
shape as `examples/reference-service/`. Whichever combination is chosen, an
unchosen backend must leave no trace: no dependency, import, setting,
compose service, recipe or file for it, and the render still passes `ruff
check` and `ruff format --check`.

Two mechanisms enforce that, at different granularities. `hooks/
post_gen_project.py`'s `PRUNED` table deletes whole files and directories
that belong entirely to one backend — `migrations/`, `src/<package>/
infrastructure/db/`, and so on — after cookiecutter has rendered everything
else. Jinja `{%- if %}` blocks remove lines *inside* files that mix a
backend with other content — `pyproject.toml`, `compose.yaml`, `settings.py`,
`container.py`, `justfile`, `.importlinter`, `.env.example` among others. A
path belonging to one backend is always deleted by the hook, never emptied
by Jinja.

Every conditional in a Python, YAML or TOML file uses cookiecutter's
**left-strip** block tags — `{%- if %}`, `{%- elif %}`, `{%- else %}`,
`{%- endif %}` — each on its own line, never the trim or right-strip forms.
The one exception is a single token inside one line of a shell recipe in
the `justfile` — a recipe parameter default, an image name in a `for` loop —
written inline as `{% if … %}…{% endif %}` with no dashes, because splitting
that line would change the command; a whole recipe, or anything in a
Python, YAML or TOML file, always takes the own-line form. A `{%-` tag consumes the newline
and any whitespace before it, so a block's own leading blank line has to sit
*inside* the block, never before the tag, or the "everything on" render
loses a blank line the pruned render never had — and that render must stay
byte-identical to `examples/reference-service/`. For example:

```
import pytest
{%- if cookiecutter.cache == "redis" %}

from redis.asyncio import Redis
{%- endif %}
```

Two rules follow from this: a conditional wraps a line that already exists
in the everything-on render — it introduces no new logic — and it wraps
only whole existing lines, moving no blank line before the tag it belongs
after.

`{%- else %}` is the exception, for the rare spot where the pruned render
needs a *reduced* line rather than none at all: an import list that loses
one name (`from tests.compose_images import compose_image,
dockerfile_base_image` becomes `from tests.compose_images import
compose_image`), or `container.py`'s `close_container`, whose nested
`try`/`finally` cannot be dedented by Jinja, so the branches with the
database or the cache off repeat the surrounding `try`/`finally` one level
up instead — a four-way `{%- if %} … {%- elif %} … {%- elif %} … {%- else %}`
block, not new control flow.

To see what one combination renders, skip the hook's side effects with
`PYFR_REGEN=1` and pass the answers that differ from the defaults:

```bash
PYFR_REGEN=1 uv run --group dev cookiecutter . --no-input -o /tmp/x database=none cache=none
```

`tests/test_generation.py` renders all eight combinations on every push
(`test_a_render_carries_only_the_backends_it_chose`), running `ruff check`
and `ruff format --check` on each, plus an AST-based resolver for
first-party imports that catches a conditional pruning a `def` while a
test still does `from … import` of it — ruff has no way to know the name
stopped existing, so it stays quiet, and pytest would only discover the gap
while collecting the test. After any template edit, `just regen` then
`git diff --stat examples/reference-service` coming back empty is the proof
that the everything-on render did not move. `just regen-check` run *after*
`just regen` compares the freshly regenerated example against itself and
would not catch a lost byte; run against the committed example instead, it
is the golden diff CI runs, and that does catch one.

### Dependabot and the template

Dependabot's `directory` entries point at `examples/reference-service/`
because it cannot parse Jinja. Its pull requests therefore change the
rendered example, not the template. The `golden` job runs `just adopt`
first on those pull requests, and `.github/workflows/adopt.yml` commits
the same result to `main` after the merge. `adopt` copies a replaced
line back into the template file that renders it; a change of any other
shape — an inserted hook, a new dependency — fails with the file name,
and you make it in the template by hand. If `main` is ever red on
`golden` after a Dependabot merge — `adopt.yml` lost a race with another
merge, or its rebase conflicted — run `just adopt`, commit and push.

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

The commit-message hook is installed by `uv run pre-commit install` at the
repository root — see [Working on the template](#working-on-the-template)
above — which wires up both the `pre-commit` and `commit-msg` stages.

The hook runs Commitizen, and Commitizen comes from the **root** `uv.lock`,
not from a version pinned in the hook configuration: the hook's command is
`uv run --locked --group dev cz`, run from the repository root, so the tool
that checks a message is the same version that later decides the release. Run
`uv sync --group dev` at the repository root once to install it (`just
docs-install` does too, since `dev` is a default group); otherwise `uv run`
installs it on first use, which makes the first commit slower than it needs
to be. One pin, in one file Dependabot updates, is the whole point — see
[ADR 0014](adr/0014-dependabot-and-one-pin-per-tool.md).

## One-time repository settings

Eight settings live in the GitHub interface, not in this repository, so they
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
- **A `RELEASE_TOKEN` secret, so the release push lands.** The `main`
  ruleset requires a pull request and exempts only the repository admin.
  The default `GITHUB_TOKEN` is not exempt, so `release.yml`'s push of the
  bump commit and tag is refused (`GH013`) and every release fails at that
  step with no tag reaching origin — and on a user-owned repository GitHub
  refuses to add the Actions app to the bypass list, so the only route is
  a token whose owner is exempt. Create a fine-grained personal access
  token as the admin (repository access: this repository only; Contents:
  read and write) and store it as the repository secret `RELEASE_TOKEN`.
  The workflows hand it to their push step alone, through that step's
  environment — the checkout keeps no credential, so nothing the job runs
  before the push can read it. Renew it before it expires;
  the failure mode when it lapses is the same `GH013` at the push step.
- **`adopt.yml` pushes to `main`** with the same `RELEASE_TOKEN`, for the
  same reason.
- **After the first release, make the two GHCR packages public.** The first
  `publish-images` run creates `reference-service` and
  `reference-service-migrations` as *private* packages: `docker pull`
  fails for anyone outside the repository, and the nightly `security` job
  can scan `latest` only because it authenticates with the workflow token.
  Use the package's "Change visibility" setting, under the package's own
  settings, once for each of the two. Nothing in `release.yml` can do
  this. The names changed in M7 — an image is named for the generated
  project, and the reference answers name it `reference-service`.
- **Enable Dependabot alerts and Dependabot security updates.** These are
  the "Dependabot alerts" and "Dependabot security updates" toggles under
  the repository's security settings. `.github/dependabot.yml` is the
  *version* updates schedule and works without either. Alerts are what
  tells you about a new advisory between two weekly runs, and security
  updates are what opens a pull request for it the same day rather than at
  the next weekly run.

### The first release run was not like the others

This repository had no git tags until its first release, so that first run
of `.github/workflows/release.yml` could not use Commitizen's normal path:
`cz bump` needs a prior tag to diff against to compute the next version.
The workflow's bootstrap mode instead tagged the version already on disk in
`pyproject.toml` — `v0.5.0`, on 2026-09-11 — directly, with **no bump
commit and no change to `CHANGELOG.md`**, because there was nothing to
bump: `CHANGELOG.md` already described `v0.5.0`, generated from the commit
history that produced it.

So `v0.5.0` sits on `main` with no accompanying version-bump commit, and
that is the **correct** result of the first release, not a stuck or partial
run — see the "Bump the version and write the changelog" step's own comment
in `release.yml` for the two ways `cz bump` was confirmed to fail outright
with zero tags. Every release since — `v0.6.0` was the first — finds a tag
to diff against and takes the normal `cz bump` path, exactly as Commitizen
documents it. The bootstrap branch stays in the workflow: dead code here,
live for a copy of this repository made without its tags.
