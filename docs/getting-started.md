---
last_reviewed: 2026-09-14
covers:
  - cookiecutter.json
  - hooks/pre_gen_project.py
  - hooks/post_gen_project.py
---

# Getting started

This walks you through generating a project from PyFr and running it. It
takes about ten minutes, most of which is the first `just up` building a
container image.

## What you need

| Tool | Why |
| --- | --- |
| [uv](https://docs.astral.sh/uv/) | The only Python tool required. `uvx` runs cookiecutter without installing it, and the generated project uses `uv` for everything else: it fetches the right Python, installs the locked dependencies and runs every command. |
| git | The generated project is a git repository. The hook runs `git init` and makes the first commit. |
| [just](https://github.com/casey/just) | A command runner. Every task in a generated project is a `just` recipe: `just up`, `just check`, and the rest. |
| Docker | Only for `just up`, which builds the image and starts the container stack, and for the container-backed test tiers. `just check` needs no Docker. |

You do **not** need to install Python separately. A generated project pins
the interpreter in `.python-version`, and `uv` fetches it.

## Generate a project

```bash
uvx cookiecutter gh:EmadMokhtar/pyfr
```

`uvx` downloads cookiecutter into a temporary environment and runs it;
`gh:EmadMokhtar/pyfr` names this repository on GitHub. cookiecutter asks the
twelve questions below, in this order. Press Enter to accept a default. For
a choice prompt, type the number of the option you want.

| Prompt | What it decides | Default |
| --- | --- | --- |
| `project_name` | The human-readable name. It is the title of the README and of the documentation site. | `My Service` |
| `project_slug` | The directory name, the repository name and the container image name. Lower-case letters, digits and hyphens, starting with a letter. | Derived: the name lower-cased, spaces replaced by hyphens — `my-service` |
| `package_name` | The Python package under `src/`. It must be a valid Python identifier: lower-case letters, digits and underscores, at most 25 characters, and not the name of a standard-library module. | Derived: the slug with hyphens replaced by underscores — `my_service` |
| `description` | One sentence. It opens the README and is the site's description. | `A Python microservice generated from PyFr.` |
| `author_name` | The author recorded in `pyproject.toml`. The MIT and Proprietary licence texts name it too. | `Your Name` |
| `author_email` | The author's email address in `pyproject.toml`. | `you@example.com` |
| `github_org` | The GitHub user or organisation the repository will live under. It decides the repository URL, the container registry path and the documentation site's address. | `your-org` |
| `database` | `postgres` gives you a PostgreSQL repository, migrations, a migrations image and the schema gates. `none` removes every one of them. | `postgres` (or `none`) |
| `cache` | `redis` gives you a fail-open Redis cache in front of the order repository. `none` removes it. | `redis` (or `none`) |
| `object_storage` | `s3` gives you an S3-compatible receipt store, with MinIO in the local stack. `none` removes it. | `s3` (or `none`) |
| `http_port` | The port the service listens on: in `just dev`, in the compose stack and in the container image. A plain decimal integer between 1 and 65535, and not one the project's own stack binds — 8001 (`just docs`), 9099 (the payment stub), 3000, 4317, 4318 and 9090 (the observability profile), nor 5432, 6379, 9000 or 9001 while PostgreSQL, Redis or MinIO is chosen; the generator refuses those and says which service has the port. | `8000` |
| `license` | Which licence text becomes `LICENSE`. | `Apache-2.0` (or `MIT`, `MPL-2.0`, `Proprietary`) |

Four of the free-text answers — `project_name`, `description`,
`author_name` and `author_email` — are pasted into `pyproject.toml`, Python
docstrings and Markdown exactly as typed. They must not contain a double
quote, a backslash or a control character such as a line break. A bad
answer to any prompt is refused *before* a file is written, with a message
naming the prompt and the rule; nothing is left on disk, and you run the
command again.

The first entry of each choice list is the default, so a `--no-input` run
produces the "everything on" project. To take the defaults but change one
answer, pass it on the command line:

```bash
uvx cookiecutter gh:EmadMokhtar/pyfr --no-input project_name="Order Service" database=none
```

Your answers are recorded in the generated project as `.pyfr-answers.yml`,
together with the template version they were rendered from. Keep it
committed and unedited: M8's template updates read it.

## What the hook does

Once the prompts are answered, cookiecutter writes the project and runs the
template's post-generation hook inside it. The hook does two things.

**It keeps what the answers chose.** The chosen licence text is renamed to
`LICENSE` and the other three are deleted. For each backend answered
`none`, the hook deletes the files and directories that belong to that
backend alone — `migrations/`, the database adapter package, the cache
adapter package, and so on — after cookiecutter has already removed the
lines *inside* mixed files. Then it removes any directory that was left
empty. Nothing of an unchosen backend survives: no dependency, import,
setting, compose service, recipe or file.

**It sets the project up, best effort.** In order:

1. `git init -q`
2. `uv sync` — install the locked dependencies, fetching Python if needed.
3. `uv run pre-commit install` — wire up the git hooks, for both the
   `pre-commit` stage (formatting, linting, secrets) and the `commit-msg`
   stage (the Conventional Commits check).
4. `git add -A`, then the first commit:
   `git commit -q -m "chore: generate the project from pyfr"`.

Every step is best effort. A step that fails — no network for `uv sync`,
no `git` on the machine — prints ``Could not run `<command>`; run it
later.`` and the hook carries on with the next step, and it still exits 0.
An offline laptop must receive a fully written project, not a failed
generation. If the first commit could not be made, the hook says so:
``Run `git add -A && git commit` once the steps above succeed.`` Each step
is independent, so a missing `git` does not stop `uv sync`, and a failed
`uv sync` does not stop the repository being made.

The hook ends by printing what to do next:

```
Next steps:
  cd my-service
  just up          # build the image and start the stack
  just check       # every fast gate
  see README.md for the rest
```

## Run it

```bash
cd my-service
just up
```

`just up` builds the container image and starts the compose stack: the
backends you chose, a payment stub and the API, in dependency order. Once
the API reports healthy, a one-shot `seed` container creates five orders
through it, so there is data to read before you have typed a request. The
API serves on the port you chose — <http://localhost:8000/docs> with the
default — and Ctrl-C stops the stack.

In a second terminal, run every fast gate:

```bash
just check
```

That is lint, type-check, the import-boundary check, the unit and API test
tiers and the pre-commit hooks, followed by `git diff --exit-code` to catch
a hook that changed a file. It needs no Docker and finishes in a couple of
minutes. It is also what the project's own continuous integration runs on
every pull request and every push to `main`, from the first one.

The generated `README.md` lists every recipe, and `just` with no arguments
prints them.

## Where to go next

**The project's own documentation site.** Every generated project ships a
site about itself, under its `docs/`, and its `docs.yml` workflow deploys
it to GitHub Pages on every push to `main` — once the Pages source setting
below is made. Until then, read the reference service's copy of that site
— the same pages, rendered for the "everything on" answers:

- [Getting started](https://emadmokhtar.github.io/pyfr/reference-service/getting-started/)
  places an order and explains each response. It is the same walk-through
  your project's site carries for your service.
- [Commands](https://emadmokhtar.github.io/pyfr/reference-service/reference/commands/)
  is every `just` recipe, and
  [Configuration](https://emadmokhtar.github.io/pyfr/reference-service/reference/configuration/)
  every environment variable.
- [Add an endpoint](https://emadmokhtar.github.io/pyfr/reference-service/guides/add-an-endpoint/)
  builds a feature through all four layers.

**The repository settings.** Five settings live in the GitHub interface,
not in the generated files, and the workflows need them: the Pages source,
a `no-docs-needed` label, a `RELEASE_TOKEN` secret when a ruleset requires
pull requests, squash-merge, and making the published container packages
public after the first release. The generated `README.md` lists all five
under *Continuous integration and releases*, with what goes wrong when each
is missing; the reference service's copy is
[here](https://github.com/EmadMokhtar/pyfr/blob/main/examples/reference-service/README.md#continuous-integration-and-releases).

**How PyFr itself is built** — the template body, the golden diff, pruning
and the regeneration loop — is in [Contributing](contributing.md).
