---
last_reviewed: 2026-09-15
---

# Glossary

Terms used across this site, each in one line. This site is about PyFr —
the template, how it is built and how a project is generated from it.
Terms about the service a generated project runs — port, adapter,
readiness, Problem Details, error budget, and the rest — are in the
[reference service's glossary](https://emadmokhtar.github.io/pyfr/reference-service/glossary/),
which every generated project carries for itself.

| Term | Meaning |
| --- | --- |
| ADR | Architecture Decision Record — a one-page note recording a decision, its context, and its consequences. PyFr's own are 0002, 0003 and 0017; the rest belong to the service. |
| Answers | The values given to the twelve prompts. `tests/reference-answers.yaml` holds the fixed set the reference service is rendered from; a generated project records its own in `.pyfr-answers.yml`. |
| Backend combination | One choice for each of the three backend prompts — `database`, `cache`, `object_storage` — so eight combinations in all. "Everything on" is the default; "everything off" is `none` three times. |
| Commitizen | The tool that checks each commit message against Conventional Commits, decides the next version from the commits since the last tag, writes the changelog and tags the release. Pinned once, in `uv.lock`, and run through `uv run --locked cz`. |
| Conventional Commits | A commit message format (`feat:`, `fix:`, `feat!:`) that machines can read to decide version bumps. Required for every commit and every pull request title. |
| cookiecutter | The tool that turns a project template plus your answers into a new repository. |
| Copier | An alternative template tool with updates built in; considered and rejected in [ADR 0002](adr/0002-cookiecutter-over-copier-and-cruft.md). |
| `covers:` | Front-matter key on a documentation page listing the paths the page describes. A change to one of them without a change to the page is reported by the freshness check. |
| cruft | A tool adding update support to cookiecutter templates; considered and rejected in the same record. |
| Dependabot | GitHub's own dependency-update service. Opens a pull request when a pinned version has a newer release. It edits the rendered example, because it cannot parse Jinja, and `just adopt` carries the change into the template. |
| Diátaxis | A documentation framework separating tutorials, how-to guides, reference, and explanation. Both sites follow it. |
| Everything-on render | The render produced by the default answers: PostgreSQL, Redis and S3 all chosen. It is the same shape as the reference service. |
| Full-suite tests | M7's fifth pull request: generate a project in continuous integration for three sampled combinations — everything on, everything off, PostgreSQL only — then `uv sync` and run its entire lint, type-check and test suite. Slow, so they run on merge and nightly rather than on every push. |
| Generation tests | `tests/test_generation.py`: render every backend combination and assert what each render must satisfy — no unchosen backend left behind, no surviving template syntax, `ruff` clean, the site builds. Run on every push. |
| GHCR | GitHub Container Registry — `ghcr.io`, where a project's release workflow pushes its container images. |
| Golden diff | `just regen-check`: render the template with the reference answers and compare the result with the committed `examples/reference-service/`, byte for byte, `uv.lock` excepted. Any difference fails the build with the file named. CI's `golden` job. |
| Hook | A script cookiecutter runs around a render. `hooks/pre_gen_project.py` refuses bad answers before any file is written; `hooks/post_gen_project.py` prunes the unchosen backends, keeps the chosen licence, and — outside regeneration — runs `git init`, `uv sync`, `pre-commit install` and the first commit. |
| Jinja | The placeholder language cookiecutter uses; `{{ }}` marks a substitution and `{% if %}` a conditional block. |
| just | A command runner. A `justfile` holds named recipes; `just <name>` runs one. The root has one, the template body has another. |
| `just adopt` | Copy a line-for-line change Dependabot made in the rendered example back into the template file that renders it, then copy the root workflows' action pins into the template's workflows, and regenerate. Anything that is not a replaced line is refused and made by hand. |
| `just regen` | Render the template with the reference answers into `examples/reference-service/`. The only way that directory changes. |
| `last_reviewed` | Front-matter key on a documentation page: the date someone last read the page against the code. Older than 180 days, the freshness check warns. |
| Left-strip tag | A Jinja block tag written `{%- … %}`: the dash removes the newline and whitespace before it, so the tag's own line vanishes from the render. Every conditional in the template body uses this form. |
| lychee | The external-link checker. `just links` runs it over both sites' Markdown; CI's `links` job does the same from the action. |
| Merge base | The most recent commit two branches share — the "before" state a three-way merge compares both sides against. |
| Migration script | A `before.py` or `after.py` under `updates/<version>/` in this repository, run by `pyfr update` around the merge for a template change a merge cannot express — a moved file, a setting that changed shape. Standard library only; must be safe to run twice. |
| MkDocs | The static-site generator behind both documentation sites, with the Material theme. `mkdocs build --strict` turns every warning into a failure. |
| `no-docs-needed` | A pull-request label that switches off the hard documentation gate for a refactor or an internal-only change. |
| pip-audit | A tool that checks pinned Python packages against the PyPI advisory database. `just audit` runs it over the root `uv.lock`; the reference service runs it over its own. |
| Pruning | Removing everything that belongs to an unchosen backend from a render: whole files and directories by the post-generation hook's `PRUNED` table, lines inside mixed files by Jinja `{%- if %}` blocks. |
| `.pyfr-answers.yml` | A file the template writes into every generated project, recording the answers and the template version it was rendered from. `just update` reads it. Kept committed and unedited. |
| `pyfr-cli` | The updater a generated project runs as `just update`: a Python package on PyPI, command `pyfr`, run through `uvx` at the target template version. Its version is the template's, and it is the one package this repository publishes (ADR 0018). |
| `.pyfr-update-ignore` | A file in every generated project, in gitignore syntax, naming the paths `just update` never touches — the ones the team rewrites. A project without it uses the built-in default for its answers. |
| Reference answers | `tests/reference-answers.yaml`: the fixed, everything-on answers `examples/reference-service/` is rendered from, with the names the reference service has carried since M0. |
| Reference service | `examples/reference-service/`: the complete, running service rendered from the template with the reference answers, and never edited by hand. Its site is the worked example of the documentation every generated project ships. |
| Render | The output of running cookiecutter over the template body with one set of answers. The reference service is one render; the generation tests make eight more. |
| SemVer | Semantic Versioning — `MAJOR.MINOR.PATCH`, where a major bump means a breaking change. Below 1.0.0, a breaking change bumps the minor number instead. |
| Squash merge | Merging a pull request as one commit whose message is the pull request title. Why the title must be a Conventional Commit. |
| Template body | `{{cookiecutter.project_slug}}/`: the directory cookiecutter renders, and the only source of truth for the service. Its name is itself a placeholder, replaced by the project slug. |
| Three-way merge | A merge using the merge base plus both sides, so a tool can tell "they changed it" apart from "you changed it". |
| Trusted Publishing | PyPI accepting a short-lived OpenID Connect token — a signed statement of identity — that GitHub Actions mints for one workflow run, instead of a stored PyPI password or token. How `release.yml` publishes `pyfr-cli`. |
| uv | A fast Python package and project manager. The only Python tool PyFr requires; `uvx` runs cookiecutter through it without an install. |
| Vendor branch | A branch holding pristine upstream output and nothing else, merged in to receive upstream changes. The `template` branch in every generated project, kept on the remote so the second update has the first's commit as its base (ADR 0018). |
| Walking skeleton | A thin but complete end-to-end implementation, proving the architecture before features are added. M0 was one. |
