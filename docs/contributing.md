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

Two continuous integration jobs enforce this.

**`docs`** builds the site with `--strict` on every push and pull request.

**`docs-freshness`** fails a pull request that changes
`examples/reference-service/src/**` without touching `docs/`, `README.md`, or
`mkdocs.yml`.

It is a blunt heuristic, on purpose. It cannot tell a stale sentence from a
fresh one; it only notices that source changed and no documented surface did.
A pure refactor or a dependency bump will trip it, and that is the accepted
cost of catching the case that matters.

The escape hatch is the **`no-docs-needed`** label on the pull request. The
workflow re-runs when a label is added, so applying it turns the failed check
green without an empty commit.

A label is used rather than a commit message trailer because pull requests are
squash-merged, which rewrites the message.

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

Three settings live in the GitHub interface, not in this repository, so they
are easy to miss when standing up a fork.

- **Settings → Pages → Source = "GitHub Actions".** Without it the `Docs`
  workflow's build job succeeds while its deploy job fails with an opaque
  error, and every published documentation link stays dead.
- **A `no-docs-needed` label must exist**, or the freshness check has no
  escape hatch.
- **Squash-merge as the merge strategy**, since the commit convention above
  assumes the pull request title becomes the commit on `main`.
