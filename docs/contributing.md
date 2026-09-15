---
last_reviewed: 2026-09-15
covers:
  - justfile
  - scripts/regen.py
  - scripts/check_site_links.py
  - .github/workflows/ci.yml
  - .github/workflows/docs.yml
  - .github/workflows/full-suite.yml
  - "{{cookiecutter.project_slug}}/scripts/check_docs_updated.py"
  - "{{cookiecutter.project_slug}}/scripts/check_docs_freshness.py"
---

# Contributing

## Repository layout

```
pyfr/
  docs/                        this site: about PyFr itself
    superpowers/               design specs and plans; not published
  cookiecutter.json  hooks/    the template's prompts and hooks
  {{cookiecutter.project_slug}}/  the template body — the source of truth
    docs/  mkdocs.yml            a generated project's own site
    scripts/                     the documentation hygiene scripts
  examples/reference-service/  rendered from the template; never edited by hand
  scripts/regen.py             the regeneration loop: regen, regen-check, adopt
  scripts/check_site_links.py  the links between the two sites, and into the repository
  src/pyfr_cli/                the updater a generated project runs: `pyfr update`, `pyfr update-check`
  updates/                     migration scripts, one directory per template release that needs one
  tests/                       PyFr's own tests: the hooks, the render, the golden diff, pyfr-cli
  mkdocs.yml  pyproject.toml   this site and the root toolchain
  justfile                     repository commands — see Commands below
  .github/workflows/           continuous integration, the full suite, publishing (GHCR and PyPI)
  .github/dependabot.yml       automated dependency updates
```

Two documentation sites live here, and the split is by subject. The root
`docs/` describes PyFr: how to generate a project, how the template is
built and tested, and why it is a template. Everything about the *service*
a project runs — the getting started walk-through, the runbook, the
guides, the reference pages, the service's decision records — is in the
template body's `docs/`, because every generated project ships that site
about itself. [Working on the documentation](#working-on-the-documentation)
has the mechanics.

Two scripts live at the root: `scripts/regen.py`, the regeneration loop,
and `scripts/check_site_links.py`, which only this repository needs
because only it builds two sites into one. The three documentation
hygiene scripts — `check_docs_updated.py`, `check_docs_freshness.py` and
`check_doc_examples.py` — live in the template body's `scripts/`, with
their tests in its `tests/unit/`, because a generated project runs them
in its own continuous integration. PyFr runs the example's rendered
copies over its own pages; [Documentation ships with the
change](#documentation-ships-with-the-change) says which job runs which.

The repository root and the reference service are **two separate Python
projects**, each with its own `pyproject.toml`, and they are never synced
together. The root project holds the documentation toolchain, the template
toolchain — cookiecutter, the hooks' and generation tests, the
regeneration script — and one package: `pyfr-cli`, the updater a generated
project runs as `just update`, published to PyPI by every release
([Working on `pyfr-cli`](#working-on-pyfr-cli)).

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

The template also ships a generated project's `.github/` — `ci.yml`,
`nightly.yml`, `release.yml`, `docs.yml`, `template-update.yml` and
`dependabot.yml`. In this
repository their render at `examples/reference-service/.github/` is output
and inert: GitHub runs workflows from a repository's root only, and the
root's own workflows test the example through `working-directory`. Edit
them in the template. The generation tests parse every render's
workflows, check that each `just` recipe a step calls exists in that
render's justfile, and that a pruned backend leaves no word behind in
them; `tests/test_regen.py` holds every `uses:` ref in the template's
workflows equal to the root's. The workflows themselves run only in a
generated project.

### The full-suite tests

The generation tests prove every render is well-formed. Three renders are
also proven to be *services*: `tests/test_generated_service.py` renders
everything on (the reference answers), everything off, and PostgreSQL
alone, for real — the post-generation hook runs `git init`, `uv sync` and
the first commit, exactly as on a user's machine — and runs each project's
own `just check-all`, the six gates its CI runs as separate jobs. The two
smaller combinations also change the name, organisation, licence and port,
so those substitutions are proven to produce a working project too. Three
syncs and three full gate runs take too long for every push, so the tests
carry the `full_suite` marker, `pyproject.toml` deselects it by default,
and `.github/workflows/full-suite.yml` runs them on every merge to `main`,
nightly, and on demand — one job per combination. Locally, with Docker
running:

```bash
just test-full-suite            # all three, a few minutes each
just test-full-suite postgres-only
```

A failing gate fails the test with that gate's output, and the render is
kept on disk (the test prints where); a passing render is removed, since
each carries a `.venv/` of a few hundred megabytes.

The service's own checks before a pull request — `just check`, `just
check-all` and `just security` — are the example's, and the example's site
describes them in its
[Contributing](https://emadmokhtar.github.io/pyfr/reference-service/contributing/)
page. Run them from `examples/reference-service/`.

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
compose service, recipe, page or file for it, and the render still passes
`ruff check` and `ruff format --check`.

Two mechanisms enforce that, at different granularities. `hooks/
post_gen_project.py`'s `PRUNED` table deletes whole files and directories
that belong entirely to one backend — `migrations/`, `src/<package>/
infrastructure/db/`, and so on — after cookiecutter has rendered everything
else. Jinja `{%- if %}` blocks remove lines *inside* files that mix a
backend with other content — `pyproject.toml`, `compose.yaml`, `settings.py`,
`container.py`, `justfile`, `.importlinter`, `.env.example`, `mkdocs.yml`
and the documentation pages among others. A path belonging to one backend
is always deleted by the hook, never emptied by Jinja.

Every conditional in a Python, YAML, TOML or Markdown file uses
cookiecutter's **left-strip** block tags — `{%- if %}`, `{%- elif %}`,
`{%- else %}`, `{%- endif %}` — each on its own line, never the trim or
right-strip forms. There are two exceptions. The first is a single token
inside one line of a shell recipe in the `justfile` — a recipe parameter
default, an image name in a `for` loop — written inline as
`{% if … %}…{% endif %}` with no dashes, because splitting that line would
change the command; a whole recipe, or anything in a Python, YAML or TOML
file, always takes the own-line form. The second is inside one sentence
of a Markdown page, where a word or phrase differs by backend and the
line cannot be split without breaking the sentence: there the trim forms
`{%- if … -%}` / `{%- else -%}` / `{%- endif -%}` (both dashes, so no
newline survives on either side of the branch) are allowed, and each use
carries a Jinja comment — `{#- … #}`, which renders as nothing — naming
why the line could not be split. There is one such use today: the
observability reference's sentence on the removed instrumentation
dependency, whose ending is either a full stop or a pointer to
`instrument_redis`. Prefer a `{%- set %}` phrase variable, described
below, wherever the varying part can be named.

A `{%-` tag consumes the newline and any whitespace before it, so a
block's own leading blank line has to sit *inside* the block, never
before the tag, or the "everything on" render loses a blank line the
pruned render never had — and that render must stay byte-identical to
`examples/reference-service/`. The mirror case has one
sanctioned exception: where a pruned block must *leave* a blank line
behind — a bullet list whose first item is conditional, and Markdown
needs a blank line between the paragraph above and whichever item comes
first — the block ends with `{%- else %}` followed by a plain `{% endif %}`
with no dash, whose kept newline is that blank line. It is used once, in
the runbook's "Act, per dependency" list; comment it wherever it recurs.
For example:

```
import pytest
{%- if cookiecutter.cache == "redis" %}

from redis.asyncio import Redis
{%- endif %}
```

Two rules follow from this: a conditional wraps a line that already exists
in the everything-on render — it introduces no new logic — and it wraps
only whole existing lines, moving no blank line before the tag it belongs
after. In a Markdown page the same rule means a conditional paragraph
starts with a blank line *inside* the branch; a conditional table row or
list item has no blank line at all, because one would end the table.

`{%- else %}` is the exception, for the rare spot where the pruned render
needs a *reduced* line rather than none at all: an import list that loses
one name (`from tests.compose_images import compose_image,
dockerfile_base_image` becomes `from tests.compose_images import
compose_image`), or `container.py`'s `close_container`, whose nested
`try`/`finally` cannot be dedented by Jinja, so the branches with the
database or the cache off repeat the surrounding `try`/`finally` one level
up instead — a four-way `{%- if %} … {%- elif %} … {%- elif %} … {%- else %}`
block, not new control flow.

Where a sentence *enumerates* things that vary by backend — a list of
package names, a comma-separated set of dependencies — nesting `{%- if %}`
blocks inside the sentence produces a page nobody can read. Build the
list in a `{%- set %}` variable at the top of the page or table instead,
and join it where the sentence needs it. `docs/explanation/layers.md`
does this for the import-linter table: a `{%- set _forbidden = ["FastAPI",
"Starlette"] + (["SQLAlchemy", "asyncpg"] if cookiecutter.database ==
"postgres" else []) + … %}` line above the row, and `{{ _forbidden |
join(', ') }}` in the row. The `set` line renders as nothing — its `{%-`
consumes the newline before it, and its plain `%}` keeps the line's own —
so it takes the place of one line and moves no blank line; the leading
underscore marks the variable as the page's own. This is also the tool
for a sentence whose *wording* varies by backend: set the phrase once at
the top, and the sentence stays one plain line. The `/readyz` example in
the HTTP API reference and in the README is built that way, from a
`_checks` string and a `_deps` list set under the heading above it, and
needs no exception to the own-line rule.

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
while collecting the test. The same test reads the pages that document
what a render *has* — the index, getting started, the runbook, the
commands, configuration, observability and supply-chain references, the
container guide, the glossary and `mkdocs.yml` — and fails on a word of a
pruned backend in any of them. Comparative prose elsewhere, such as a
decision record that weighs PostgreSQL against an in-memory store, is
deliberately not policed. After any template edit, `just regen` then
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

Action versions go the other way. Dependabot's `github-actions` ecosystem
reads `/.github/workflows` only, so its bumps land in this repository's
own workflows, and `just adopt` copies each bumped `uses:` ref into the
template's workflows and regenerates the example. `tests/test_regen.py`
fails when a template workflow pins an action at a different ref than the
root does — or uses one the root does not — so every action a generated
project runs is one Dependabot sees here. Between a `ci(deps)` merge and
`adopt.yml`'s commit, another pull request's `docs` job can fail that
test — its merge ref has the new root pins and the old template pins;
re-run it once the adopted commit is on `main`.

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

## Working on the documentation

### Two sites, one deploy

This repository builds two MkDocs sites and deploys them as one.

- **PyFr's site** is the root `docs/` with the root `mkdocs.yml`, built
  into `site/` and served at `https://emadmokhtar.github.io/pyfr/`. Its
  pages are this one, the home page, getting started, the roadmap, the
  glossary, PyFr's three decision records (0002, 0003 and 0017) and *Why a
  template, not a framework*.
- **The reference service's site** is `examples/reference-service/docs/`
  with that project's `mkdocs.yml`, built into `site/reference-service/`
  and served at `https://emadmokhtar.github.io/pyfr/reference-service/`.
  Both are rendered from the template body, so a page there is edited in
  `{{cookiecutter.project_slug}}/docs/` and regenerated. Every generated
  project builds the same site about itself and deploys it with its own
  `docs.yml`.

`just docs-build` builds both, in that order, with `mkdocs build
--strict`; `.github/workflows/docs.yml` runs the same recipe and uploads
`site/` as one Pages artifact. The second build runs inside
`examples/reference-service/` with that project's own toolchain and its
own `mkdocs.yml`, and sets four environment variables the template's
`mkdocs.yml` reads with `!ENV`: `SITE_URL`, so the rendered `site_url` is
the nested address; `REPO_URL` and `REPO_NAME`, so the header's
repository link and name are PyFr's, not the reference service's; and
`EDIT_URI`, so each page's edit link opens the *template* page —
`edit/main/{{cookiecutter.project_slug}}/docs/`, with the braces
percent-encoded so the URL is valid — because the rendered example is
never edited by hand. A generated project leaves all four unset — its
`mkdocs.yml` reads `site_url: !ENV [SITE_URL, "<its own Pages address>"]`
and the same shape for the other three — and gets a site at the top of
its own domain, linked to its own repository. `mkdocs build --strict`
turns a warning into a failure: a link to a page that no longer exists, a
renamed heading anchor, or an unresolvable include each fails the build
rather than printing a warning nobody reads.

A link **within** a site is relative, as usual: `roadmap.md`,
`../explanation/layers.md`. A link **between** the two sites is an
absolute URL, always: from a root page to a service page it is
`https://emadmokhtar.github.io/pyfr/reference-service/<page>/`, and from a
template page to a root page it is
`https://emadmokhtar.github.io/pyfr/<page>/`. MkDocs' `--strict` fails a
relative link to a page outside the site it is building, so there is no
other way to write one. The root `lychee.toml` excludes PyFr's own Pages
host from the external-link check for the same reason: a link to a page
added in the branch being checked resolves only after the deploy. What
checks those links instead is `scripts/check_site_links.py`, the last step
of `just docs-build`: it reads every `https://emadmokhtar.github.io/pyfr/…`
link out of both documentation trees and resolves it against the `site/`
directory just built — the page must exist there, and an anchor must be an
element id in it — so a renamed page or heading on either side fails the
build before it reaches the deploy. Given `--repo-root`, as the recipe
passes it, the same script also reads every link into this repository's
tree on GitHub — `edit/main/…`, `blob/main/…` and `tree/main/…` under
`https://github.com/EmadMokhtar/pyfr/` — out of the *built* HTML of both
sites and checks that the path exists in the checkout. That covers the
edit links Material writes from `edit_uri`, which `lychee.toml` skips
because a page added in the branch exists on `main` only after the merge,
and the decision records' links into `docs/superpowers/`, which it skips
for the same reason.

A page in the template's `docs/` carries the project's identity, never the
reference service's: `{{ cookiecutter.project_slug }}`,
`{{ cookiecutter.project_name }}`, `{{ cookiecutter.package_name }}` and
`{{ cookiecutter.github_org }}` where the project is named, and PyFr's own
URLs literal. `tests/test_generation.py` renders the default answers and
fails on `reference-service`, `reference_service`, `Reference Service` or
`emadmokhtar` in any rendered page, the README, the scripts, `mkdocs.yml`
or the workflows, outside PyFr's two URLs — which is also why a template
page can never link to the reference service's site.

### Front matter

Every published page opens with YAML front matter. `last_reviewed` is the
date someone last read the page against the code; `covers:` lists the
paths the page describes, so a change to one of them without a change to
the page can be reported. At the root the paths are repository-relative
(`scripts/regen.py`, `hooks/post_gen_project.py`). In the template's pages
they are relative to the *generated project* (`justfile`,
`src/{{ cookiecutter.package_name }}/settings.py`), because that is where
the freshness script checks them. The script asks git for the changed
paths with `--relative`, so they come back relative to the directory it
runs in: the root's `docs/` when PyFr runs it from the root, the
project's `docs/` when a generated project runs it from its own root.

### The local loop

```bash
just docs-install
```

```bash
just docs
```

That serves a live preview of PyFr's site on <http://127.0.0.1:8000> and
rebuilds as you save. For the reference service's site, run `just docs` in
`examples/reference-service/` instead; it serves on port 8001, so the two
previews can run together. Before pushing:

```bash
just docs-build
```

Adding a page means adding it to `nav:` in the right `mkdocs.yml`. A page
absent from the navigation is unreachable. In the template's `mkdocs.yml`
a nav entry for a page that is only about one backend sits inside that
backend's `{%- if %}` block.

### `docs/superpowers/` is an archive

It holds the design specification and the milestone implementation plans. They
stay in the repository — they are the reasoning behind what this site
describes — but `mkdocs.yml` excludes them from the published site. They are
working documents, thousands of lines long, and out of date by design once a
milestone lands.

Do not treat editing one as documenting a change. The freshness checks below
deliberately do not count it.

## Documentation ships with the change

Four independent mechanisms enforce this, and each catches something
different. The scripts are the template's, run from their rendered copies
under `examples/reference-service/scripts/`; a generated project runs the
same scripts over itself, with the defaults. Here every option names
PyFr's own trees.

**`check_docs_updated.py`** is a hard gate: CI's **`docs-freshness`** job.
It fails a pull request that changes `{{cookiecutter.project_slug}}/src/`
without touching the root `docs/`, `README.md`, `mkdocs.yml`, or the
template's `docs/` or `README.md`. The job runs

```bash
python3 examples/reference-service/scripts/check_docs_updated.py \
  --source '{{cookiecutter.project_slug}}/src/' \
  --docs docs/ --docs README.md --docs mkdocs.yml \
  --docs '{{cookiecutter.project_slug}}/docs/' \
  --docs '{{cookiecutter.project_slug}}/README.md' \
  --exclude-docs docs/superpowers/ "$BASE_SHA" HEAD
```

It is a blunt heuristic, on purpose: it cannot tell a stale sentence from a
fresh one, it only notices that source changed and no documented surface
did. A pure refactor or a dependency bump will trip it, and that is the
accepted cost of catching the case that matters. The escape hatch is the
**`no-docs-needed`** label on the pull request — the workflow re-runs when
a label is added, so applying it turns the failed check green without an
empty commit. A label is used rather than a commit message trailer because
pull requests are squash-merged, which rewrites the message.

**`check_docs_freshness.py`** only warns; nothing it finds can fail a
build. CI's **`docs-warnings`** job runs `just docs-freshness "$BASE_SHA"
HEAD`, which runs the script twice — at the root over PyFr's own `docs/`,
then inside `examples/reference-service/` over the rendered pages:

```bash
uv run --group docs python examples/reference-service/scripts/check_docs_freshness.py \
  --exclude docs/superpowers/ origin/main HEAD
cd examples/reference-service && \
  uv run --group docs python scripts/check_docs_freshness.py origin/main HEAD
```

It reports two things: a page whose `covers:` front matter names a path
that changed in this pull request while the page itself did not, and a
page whose `last_reviewed` date is more than 180 days old. Pages under
`docs/adr/` are skipped: a decision record does not go stale. Where the
hard gate above only notices that *some* source changed and *no*
documentation did, this one names the page and the exact path that moved.
The second run is what checks the template's pages here: a change to the
template body regenerates them, so their `covers:` coupling is reported
in this repository too, not only in a generated project's own CI.

**`lychee` and `mkdocs build --strict`** are hard gates on links, not on
prose. `--strict` fails the build on a link to a page that no longer
exists, a renamed heading anchor, or an unresolvable include; CI's
**`docs`** job runs `just check`, which starts with `just docs-build` over
both sites. `lychee` does the equivalent check for links leaving the site,
against the real internet, in its own **`links`** job — kept separate from
the site build so a network blip reads as a network blip, not as a broken
site. It reads the root `docs/`, the root `README.md`, and the *rendered*
example's `docs/` and `README.md`: the template body's Markdown carries
Jinja inside its URLs, so the render is what a link checker can read. `just
links` runs the same command locally, given a `lychee` binary.

**`check_doc_examples.py`** is a hard gate on behaviour rather than prose:
it runs every `curl` example marked `<!-- exec -->` against a real,
running service. Those examples live in the template's pages, so this
check runs where the service is: CI's **`docs-examples`** job runs `just
docs-examples` inside `examples/reference-service/`, which starts the
compose stack, runs the script and tears the stack down whether it passed
or failed. The root pages carry no marked examples, and the script fails
on a tree with none — "no examples found" is treated as a bug — which is
why PyFr never runs it over the root `docs/`. How to mark an example, and
the two rules a marked block must satisfy, are on the reference service's
[Contributing](https://emadmokhtar.github.io/pyfr/reference-service/contributing/#the-exec-marker)
page.

### `just docs-freshness` is not CI's `docs-freshness` job

These share a name and run different scripts, which makes it easy to reach
for the wrong one while reproducing a red pull request.

The CI job named **`docs-freshness`** runs `check_docs_updated.py` — the
hard gate above. The **`just docs-freshness`** recipe runs
`check_docs_freshness.py` — the advisory warnings above, which is what
CI's separate **`docs-warnings`** job calls. Reproduce a red
`docs-freshness` check locally with the `python3` command quoted above,
with `origin/main HEAD` as its two refs — not with `just docs-freshness`.
That recipe runs the other script, never fails, and will tell you nothing
about why the hard gate is red.

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

The script is the template's, so the switch would land in every generated
project too. That is a reason to be slow about it, not a reason to skip
the three conditions.

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
fix(template): prune the cache's readiness probe with the cache
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
[ADR 0014](https://emadmokhtar.github.io/pyfr/reference-service/adr/0014-dependabot-and-one-pin-per-tool/).

A generated project carries its own Commitizen (spec M7-9): `commitizen`
in its `dev` group, a `[tool.commitizen]` table in its `pyproject.toml`,
the same commit-message hook, and `just changelog` / `just next-version`.
Its version, tags and releases are its own; the root's copy decides PyFr's
releases only. In this repository the example's copy is rendered output,
and the root's hook is the one that checks your messages.

The release moves one more version. `cookiecutter.json`'s
`_template_version` — the value every generated project records in its
`.pyfr-answers.yml` — is written by the same `cz bump` as
`pyproject.toml`'s version (`version_files` in `[tool.commitizen]`), and
`just regen` runs as that bump's pre-bump hook, after the write and before
the commit, so the example's `.pyfr-answers.yml` records the released
version in the bump commit. Between releases the two versions are equal by
construction, and `tests/test_generation.py` fails the pull request that
edits one by hand; `cz bump --check-consistency` in `release.yml` refuses
to release if they have drifted anyway. A generated project's
`_template_version` is therefore the tag its template body was released
under — what M8 will read to bring it up to date.

## One-time repository settings

Seven settings live in the GitHub interface and one on pypi.org, not in
this repository, so they are easy to miss when standing up a fork. The repository's default
workflow-token permission is *not* one of them: every workflow that writes
declares the permission it needs in its own `permissions:` key, which
GitHub honours whatever the repository default says — a project generated
from this template released from a fresh repository left at the default
"Read repository contents" setting, pushing its tag and publishing its
images with the workflow token alone.

- **Settings → Pages → Source = "GitHub Actions".** Without it the `Docs`
  workflow's build job succeeds while its deploy job fails with an opaque
  error, and every published documentation link stays dead.
- **A `no-docs-needed` label must exist**, or the freshness check has no
  escape hatch.
- **Squash-merge as the merge strategy**, since the commit convention above
  assumes the pull request title becomes the commit on `main`.
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
- **A pending publisher on pypi.org for `pyfr-cli`, before the first
  release.** Project `pyfr-cli`, owner `EmadMokhtar`, repository `pyfr`,
  workflow `release.yml`, no environment. `release.yml`'s `publish-pypi`
  job uploads with Trusted Publishing — PyPI accepts a short-lived token
  GitHub mints for the run — so no PyPI token is stored. Without the
  publisher that job fails and every other release job still succeeds; it
  runs last and nothing depends on it. A fork publishes under its own
  package name, or not at all: `pyfr-cli` is this repository's.

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

## Commands

Run these from the repository root. The reference service has its own
`justfile`, documented on
[its own site](https://emadmokhtar.github.io/pyfr/reference-service/reference/commands/);
run those from `examples/reference-service/`. Several recipes share a
name with one of the service's — `check`, `docs-build`, `links`, `audit`,
`changelog` — and check different things from a different directory. They
are not interchangeable.

| Command | What it does |
| --- | --- |
| `just docs-install` | Install the documentation toolchain (`uv sync --group docs`). |
| `just docs` | Live preview of PyFr's site on <http://127.0.0.1:8000>, rebuilding as you save. |
| `just docs-build` | Build both sites into `site/` with `--strict`, exactly as CI and `docs.yml` do: PyFr's at the top, and the reference service's rendered site — built from `examples/reference-service/` with its own toolchain and its own `mkdocs.yml`, with `SITE_URL` set to its nested address, `REPO_URL` and `REPO_NAME` pointing its header at this repository, and `EDIT_URI` pointing its edit links at the template body — under `site/reference-service/`; then `scripts/check_site_links.py` resolves every link between the two sites against that tree, and every link into this repository's tree on GitHub against the checkout. |
| `just links` | Dead external links, via [`lychee`](https://github.com/lycheeverse/lychee), over the root `docs/`, the root `README.md` and the rendered example's `docs/` and `README.md`. Needs the `lychee` binary locally (`brew install lychee`); CI's `links` job gets it from the action instead, against the same `lychee.toml` and the same paths. |
| `just test` | This repository's own tests (`tests/`) — the hooks' tests, the generation-test matrix that renders all eight backend combinations and checks each one, `scripts/regen.py`'s tests, the golden diff, `pyfr-cli`'s unit tests (`tests/cli/`) and the end-to-end update test — with both the `dev` and `docs` groups, because the generation tests build a render's site with the root's MkDocs. Needs no Docker. |
| `just test-full-suite [combination]` | The full-suite tests: three combinations rendered for real, synced, committed and run through their own `just check-all`. Slow; needs Docker and the network. `combination` is one of `everything-on`, `everything-off`, `postgres-only`. CI runs them on merge to `main` and nightly, never on a pull request — see [above](#the-full-suite-tests). |
| `just precommit` | The repository's git hooks over every tracked file — the reference service's own `just precommit` skips itself when it finds it is nested inside this repository. |
| `just regen` | Regenerate `examples/reference-service/` from the template with the answers in `tests/reference-answers.yaml`; run this after every change to `{{cookiecutter.project_slug}}/` and commit the result. |
| `just regen-check` | The golden diff: render and compare, writing nothing. CI's `golden` job. |
| `just adopt` | Copy Dependabot's edits to the rendered example back into the template, then check; only for line-for-line replacements — anything else fails with the file name and is made in the template by hand. Then, in the other direction, copy the root workflows' action pins into the template's workflows and regenerate the example — Dependabot's `github-actions` updates land in `/.github/workflows` only. |
| `just audit` | pip-audit over the root `uv.lock` — the documentation and release toolchain — with the same flags as the reference service's own `audit`. CI's `security` job runs both. |
| `just lint` | `just typecheck`, then `ruff check` and `ruff format --check` over the root's own Python: `hooks/`, `scripts/`, `src/`, `tests/`. The template body is excluded; the example is linted by its own `just lint`. |
| `just typecheck` | `mypy --strict` over `src/pyfr_cli/`, the one package this repository publishes. Part of `just lint` and of `just check`. |
| `just wheel` | Build the `pyfr-cli` wheel and run `pyfr --version` from it, exactly as CI's `docs` job does; the version it prints must be `pyproject.toml`'s. Needs the network. |
| `just changelog` | Preview the changelog entry the next release would write, from Conventional Commit history. Read-only. |
| `just next-version` | Preview the version number the next release would choose. Read-only — the release itself runs in CI (`.github/workflows/release.yml`). |
| `just docs-freshness [base] [head]` | The **advisory** warnings only: a stale `last_reviewed` date, or a `covers:` path that changed while its page did not. Runs the example's `scripts/check_docs_freshness.py` twice — at the root over `docs/` with `--exclude docs/superpowers/`, then inside `examples/reference-service/` over the rendered pages; defaults to `origin/main HEAD`. Never fails. **This is not CI's `docs-freshness` job** — see [above](#just-docs-freshness-is-not-cis-docs-freshness-job). |
| `just check` | `docs-build`, `typecheck`, `test` and `regen-check` — everything CI checks at the repository level without Docker. Run before pushing a documentation, template, `pyfr-cli` or repository-tooling change. |

!!! warning "Two different servers, one port"

    `just docs` at the root and the service's `just dev` both default to
    port 8000. Stop one before starting the other, or set `APP_HTTP_PORT`
    to something else for the service.
