# Commands

Every task is a [`just`](https://github.com/casey/just) recipe. `just` is a
command runner: a `justfile` holds named recipes, and `just <name>` runs one.

The point is that continuous integration runs the *same* commands you run.
"Works on my machine, fails in the pipeline" becomes rare when there is only
one definition of what "lint" means.

Run `just` with no arguments to list the recipes.

## The reference service

Run these from `examples/reference-service/`.

| Command | What it does |
| --- | --- |
| `just install` | Sync dependencies from `uv.lock`. Same as `uv sync`. |
| `just dev` | Run with auto-reload on `APP_HTTP_PORT` (8000 by default). |
| `just test` | Run the test suite with pytest. |
| `just lint` | `ruff check` and `ruff format --check`. Reports; changes nothing. |
| `just fmt` | `ruff check --fix` and `ruff format`. Fixes what it can. |
| `just typecheck` | mypy. Strict on `domain/` and `services/`, lenient elsewhere. |
| `just imports` | import-linter: verify the [dependency rule](../explanation/layers.md). |
| `just precommit` | Run the pre-commit hooks over the project's tracked files. |
| `just check` | Everything above, then `git diff --exit-code`. Run this before pushing. |
| `just up` | Build the image and start the container stack. |
| `just down` | Stop the stack and remove its volumes. |

### Why `just check` ends with a diff check

Several pre-commit hooks **rewrite** files: `ruff-format`, `uv-lock`,
`end-of-file-fixer`, `trailing-whitespace`. A hook that reformats your code
and then exits 0 has "passed" while leaving the tree different from what you
committed. Continuous integration would fail on the first run and pass on the
second, which teaches people to just press the button again.

`git diff --exit-code` afterwards turns any such rewrite into an explicit
failure. If `just check` fails there, run `just fmt`, commit the result, and
push again.

### Why `just precommit` uses `git ls-files`

The recipe is `pre-commit run --files $(git ls-files)`, not
`pre-commit run --all-files`. `--all-files` walks up to the *enclosing*
repository when this project sits inside one — which is exactly the situation
in this repository, where the service lives under `examples/`. It would
reformat files outside the service, including Python snippets inside Markdown
documents. `git ls-files` scopes the run to the service's own files.

In a standalone generated project the two are equivalent, so the recipe is
correct in both layouts.

## The documentation site

Run these from the repository root.

| Command | What it does |
| --- | --- |
| `just docs-install` | Install the documentation toolchain (`uv sync --group docs`). |
| `just docs` | Live preview on <http://127.0.0.1:8000>, rebuilding as you save. |
| `just docs-build` | Build the site into `site/` with `--strict`, exactly as CI does. |

`--strict` turns a warning into a failure. A link to a page that no longer
exists, a heading anchor that was renamed, an include that cannot be
resolved: each fails the build instead of printing a warning nobody reads.
Run `just docs-build` before pushing a documentation change.

!!! warning "Two different servers, one port"

    `just docs` and the service's `just dev` both default to port 8000. Stop
    one before starting the other, or set `APP_HTTP_PORT` to something else.
