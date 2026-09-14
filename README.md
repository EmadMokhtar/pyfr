<div align="center">

# 🐍 PyFr

**A cookiecutter template for production-ready Python microservices.**

*Answer a few prompts. Get a service that runs, is tested, is observable, and is documented.*

[![CI](https://github.com/EmadMokhtar/pyfr/actions/workflows/ci.yml/badge.svg)](https://github.com/EmadMokhtar/pyfr/actions/workflows/ci.yml)
[![Docs](https://img.shields.io/badge/docs-pyfr-blue)](https://emadmokhtar.github.io/pyfr/)
[![Python](https://img.shields.io/badge/python-3.13%2B-blue)](https://www.python.org/)
[![License: MPL 2.0](https://img.shields.io/badge/license-MPL--2.0-brightgreen)](LICENSE)
[![Status: pre-release](https://img.shields.io/badge/status-building%20toward%20M7-orange)](https://emadmokhtar.github.io/pyfr/roadmap/)

📖 **[Read the documentation →](https://emadmokhtar.github.io/pyfr/)**

</div>

---

## 👋 Welcome

Every team starts a new Python service the same way: wiring up logging, health
checks, configuration, error formats, a container image. It takes two to four
weeks, and every team's result is a little different.

PyFr aims to make that a ten-minute step instead — and to make the result the
same good one every time.

**The generated code is yours.** 🎁 Nothing is published to a package index, and
a generated service imports no PyFr package. There is no framework to upgrade,
no runtime dependency on us, and nothing to lock you in. From M8, a generated
project will still be able to pull later template fixes into itself through an
ordinary `git merge`.

## 🚧 Honest status: M0–M6 done, M7 in progress, M8 to go

**The template exists and renders** — `uvx cookiecutter gh:EmadMokhtar/pyfr`
generates a project today. M7 is the conversion into a template, in five
pull requests, and four have landed: the template renders from twelve
prompts, prunes the backends you do not choose, gives a generated project
its own workflows, and ships its own documentation site about itself. What
remains is the fifth: the full-suite tests, which generate a project in CI
and run its whole lint, type-check and test suite — see the
[roadmap](https://emadmokhtar.github.io/pyfr/roadmap/).
The [**reference service**](examples/reference-service/) is rendered from
that template; it is the complete, running service you can run, read, and
copy from right now.

PyFr is built in three phases:

| Phase | Milestones | What happens |
| --- | --- | --- |
| **A** | M0–M6 | Build the reference service as ordinary Python — no template placeholders anywhere |
| **B** | M7 | Convert it into the cookiecutter template ✨ |
| **C** | M8+ | Keep the two in step, forever |

The rule behind that order: never debug Jinja and Python at the same time. 🙂

**M0 through M6 — the reference service — are complete. M7, the conversion
into a template, is under way.** See the
[roadmap](https://emadmokhtar.github.io/pyfr/roadmap/) for what ships when.

## 🚀 Try it in one command

```bash
uvx cookiecutter gh:EmadMokhtar/pyfr
```

cookiecutter asks twelve questions — the project's name, its author, which
of PostgreSQL, Redis and S3 it gets, its port, its licence — and every one
has a default. The hook then prunes what you did not choose, runs `git
init`, `uv sync` and `pre-commit install`, and makes the first commit, each
step best effort, so an offline laptop still gets a whole project.

Then `cd` into it, `just up`, and open <http://localhost:8000/docs>. 👋

The [getting started guide](https://emadmokhtar.github.io/pyfr/getting-started/)
explains each prompt and what the hook does; the generated project's own
site takes it from there.

## 📦 What's in the box

Every item below already runs in the reference service today — nothing here is
a promise:

- ⚡ **FastAPI**, with an application factory and a lifespan.
- 🧱 **Four layers** — domain, services, infrastructure, api — with the
  dependency rule enforced by a build check, not by code review.
- ✅ **Configuration validated at startup.** A bad value stops the process
  with a readable message and exit code 78, instead of causing a 500 an hour
  later.
- 📋 **Structured logging** — one JSON object per line on standard output,
  with third-party records passing through the same chain.
- 💚 **Three health endpoints** answering three different questions. Liveness
  never checks a dependency, so a database hiccup cannot restart every
  instance at once.
- 🚨 **RFC 9457 Problem Details** error responses.
- 🔗 **Correlation identifiers** binding one value to every log line a single
  request produced.
- 🛑 **Graceful shutdown**, so a rolling deployment does not drop live
  requests.
- 🔒 **A hardened container image**: non-root, no build tools, no shell
  utilities in the final layer, and reproducible installs from a lock file.
- 📖 **Its own documentation site**, built from its own `docs/` and
  deployed to GitHub Pages by its own workflow — the
  [reference service's site](https://emadmokhtar.github.io/pyfr/reference-service/)
  is the worked example.

M1–M6 have since added persistence, OpenTelemetry, contract testing, cache and
object storage, release automation, and supply-chain auditing, scanning and
publishing — the [roadmap](https://emadmokhtar.github.io/pyfr/roadmap/) lists
what each one delivered.

## 📚 Documentation

Two sites, deployed together. **[PyFr's site](https://emadmokhtar.github.io/pyfr/)**
is about the template: generating a project, how the template is built and
tested, and why it is a template rather than a framework. **[The reference
service's site](https://emadmokhtar.github.io/pyfr/reference-service/)** is
about the service: it is the documentation every generated project ships
about itself, rendered here for the reference answers.

| Page | What it covers |
| --- | --- |
| 🏁 [Getting started](https://emadmokhtar.github.io/pyfr/getting-started/) | Generate a project: the twelve prompts, the hook, the first `just up` |
| 🗺️ [Roadmap](https://emadmokhtar.github.io/pyfr/roadmap/) | What ships when |
| 🤝 [Contributing](https://emadmokhtar.github.io/pyfr/contributing/) | Working on PyFr itself: the template body, the golden diff, pruning, the two sites |
| 🏁 [Run the service](https://emadmokhtar.github.io/pyfr/reference-service/getting-started/) | Place an order and read each response |
| 🔨 [Add an endpoint](https://emadmokhtar.github.io/pyfr/reference-service/guides/add-an-endpoint/) | Build a feature through all four layers |
| 🏛️ [Architecture](https://emadmokhtar.github.io/pyfr/reference-service/explanation/architecture/) | How the pieces fit, and why |
| ⚙️ [Configuration](https://emadmokhtar.github.io/pyfr/reference-service/reference/configuration/) | Every environment variable |

The design specification and milestone plans live in
[`docs/superpowers/`](docs/superpowers/). They contain the reasoning behind
the decisions the site describes, and are deliberately not published.

## 🛠️ Development

The repository root and the reference service are two separate Python
projects, each with its own `pyproject.toml`. They are never synced together.
The template body, `{{cookiecutter.project_slug}}/`, is the source of truth:
edit it, run `just regen`, and the reference service is rendered from it —
never edit `examples/reference-service/` by hand.

```bash
# The template and its tests: both sites build, the root suite, the golden diff
uv sync --group dev --group docs && just check
```

```bash
# The reference service
cd examples/reference-service && uv sync && just check
```

```bash
# PyFr's documentation site, with a live preview
just docs-install && just docs
```

The [contributing guide](https://emadmokhtar.github.io/pyfr/contributing/)
has the whole loop: the regeneration and golden diff, backends and pruning,
the two documentation sites and every root `just` recipe.

## 🤝 Contributing

Issues, questions, and pull requests are all welcome — including "I read this
and it didn't make sense," which is one of the most useful things you can send
while the project is this young.

Commit messages and pull request titles must follow
[Conventional Commits](https://www.conventionalcommits.org/). The
[contributing guide](https://emadmokhtar.github.io/pyfr/contributing/) has the
rest.

## 🙏 Credits

PyFr's architecture is influenced by [GoFr](https://gofr.dev), the Go
microservice framework — the context-driven layering and the emphasis on
developer experience, adapted to Python's ecosystem and to a template rather
than a library.

## ⚖️ License

[Mozilla Public License 2.0](LICENSE).
