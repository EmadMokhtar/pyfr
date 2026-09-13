# M7 PR 4 — The documentation split — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Pages about the service move into the template body and become a generated project's own MkDocs site — templatised, pruned per backend, built and deployed by the project's own workflows — while PyFr's root site describes PyFr and links to the reference service's site, both built and deployed by one workflow; the three documentation-hygiene scripts move with the pages; the configuration-reference lookup that keeps a generated project's `check` and `gates` jobs red is fixed.

**Architecture:** Pages move by whom they describe (spec §9.1): `guides/*`, `reference/*`, `runbook.md`, `explanation/{architecture,layers,testing}.md`, ADRs 0001 and 0004–0016 and the service halves of `getting-started.md`, `contributing.md` and `glossary.md` go to `{{cookiecutter.project_slug}}/docs/`; `index.md`, `getting-started.md`, `roadmap.md`, `contributing.md`, `glossary.md`, `explanation/why-a-template.md` and ADRs 0002, 0003, 0017 stay and are rewritten around the template. The template gains `mkdocs.yml` (`site_url: !ENV [SITE_URL, …]`), a `docs` dependency group, `lychee.toml`, the docs recipes, `docs.yml`, and the documentation jobs deferred from PR 3. PyFr's `just docs-build` and `docs.yml` build the root site into `site/` and the reference service's rendered site into `site/reference-service/`, and deploy the one directory (§9.2). The hygiene scripts live in the template's `scripts/`; PyFr's root checks call the example's rendered copies.

**Tech Stack:** cookiecutter (Jinja), MkDocs 1.6 + Material, lychee, GitHub Actions/Pages, pytest + pytest-cookies.

**Spec:** `docs/superpowers/specs/2026-09-12-pyfr-m7-templatise-design.md` §9 (all), §8 (the documentation jobs and `docs.yml`, deferred here by PR 3's amendment), §10.1, §12 row 4, §14 ("A wrong `{% if %}` in … the configuration reference").

## Global Constraints

- The template body `{{cookiecutter.project_slug}}/` is the only source of truth; never edit `examples/reference-service/` by hand. After every template edit run `just regen` and commit the regenerated example **in the same commit**; `just regen-check` green at every commit.
- When the template's `pyproject.toml` changes, re-lock the example in the same commit: `(cd examples/reference-service && uv lock && uv sync)`.
- Jinja block tags stand on their own line at column 0 with a left-strip dash (`{%- if cookiecutter.database == "postgres" %}`, `{%- else %}`, `{%- endif %}`, `{%- raw %}`, `{%- endraw %}`); the tag vanishes with its line. In Markdown, a conditional block starts and ends at a blank line so the surrounding paragraphs keep their spacing in every render (put the blank line *inside* the branch, after the opening tag, as PR 3's `dependabot.yml` does). Never an inline `{% if %}` in Markdown or YAML.
- GitHub Actions expressions (`${{ … }}`) sit inside raw regions; a raw region never contains `{{ cookiecutter` or `{%- if`.
- **Identity in the template's docs:** `reference-service` → `{{ cookiecutter.project_slug }}`; `reference_service` → `{{ cookiecutter.package_name }}`; "Reference Service" → `{{ cookiecutter.project_name }}`; "the reference service" / "PyFr's reference service" → "the service" / "this service"; `EmadMokhtar` / `emadmokhtar` in a URL of the *project* (its repository, its GHCR images, its Pages site) → `{{ cookiecutter.github_org }}` (`| lower` for `ghcr.io` and the Pages host). URLs of **PyFr itself** (`https://github.com/EmadMokhtar/pyfr…`, `https://emadmokhtar.github.io/pyfr/…`) stay literal: a generated project links back to the template it came from.
- **Prose stays prose.** For the reference answers (everything on), a moved page renders to exactly its former root text apart from the edits this plan names (front-matter `covers:` paths, cross-site links, identity substitutions, the conditional tags). No rewording of moved pages except where a sentence is only true in PyFr's repository ("the reference service", "this repository's `justfile`") — then the smallest change that makes it true in a generated project.
- **Every rendered page is true in every backend combination.** A section that documents a component the render does not have (the migrations image, the Redis panel, the S3 bucket variables) sits inside that backend's `{%- if %}`; a nav entry for a page that is only about one backend is conditional. Comparative prose that *mentions* a backend to explain a design (ADR 0005 on in-memory adapters, `why-a-template.md`) is not pruned.
- Both sites build with `mkdocs build --strict` at every commit: PyFr's (`just docs-build` at the root, which from Task 2 builds both) and every render's (Task 2's generation test builds the everything-on and none-none-none renders).
- Action refs in the template's workflows equal the root's: `actions/checkout@v7`, `astral-sh/setup-uv@v7`, `extractions/setup-just@v4`, `actions/configure-pages@v6`, `actions/upload-pages-artifact@v5`, `actions/deploy-pages@v5`, `lycheeverse/lychee-action@v2` (`tests/test_regen.py` enforces it).
- Root Python (`scripts/`, `tests/`) ruff-clean at 88 columns; the template's Python ruff-clean under the render's `ruff.toml` (the invariant runs `ruff check` and `ruff format --check` on every render).
- Conventional Commits; commit messages in plain English; each commit ends with the attribution line the session gives. One commit per task unless a step says otherwise.
- The root's `just lint`, `just check` (docs-build, test, regen-check) and `just precommit` stay green at every commit; the example's `just check` stays green at every commit.
- Prose in docs: plain English, one idea per sentence, acronyms expanded on first use in a page.

## Verified Facts

1. **No snippet includes.** No page under `docs/` uses `--8<--`, so moving pages breaks no `pymdownx.snippets` path.
2. **`covers:` paths are root-relative today** (`examples/reference-service/src/reference_service/config_check.py`, `examples/reference-service/justfile`, …); `scripts/check_docs_freshness.py` compares them with `git diff --name-only base...head`, which prints repository-relative paths. Run from a subdirectory with `--relative`, git prints paths relative to that directory and only within it — so the moved script can work from a generated project's root (`covers: src/…`) and from `examples/reference-service/` alike.
3. **The hygiene scripts' path assumptions.** `check_docs_updated.py`: `SOURCE_PREFIXES = ("examples/reference-service/src/",)`, `DOCS_PATHS = ("docs/", "README.md", "mkdocs.yml")`, `EXCLUDED_DOCS_PREFIX = "docs/superpowers/"`, two positional refs. `check_docs_freshness.py`: `DOCS_ROOT = Path("docs")`, `EXCLUDED_PREFIXES = ("docs/superpowers/", "docs/adr/")`, two positional refs. `check_doc_examples.py <docs-root>` (defaults to `docs`). Their tests (`tests/test_check_docs_freshness.py`, `tests/test_check_doc_examples.py`) import the scripts through `sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))`. There is no test for `check_docs_updated.py`.
4. **`<!-- exec -->` examples** live in `docs/getting-started.md`, `docs/reference/http-api.md` and `docs/contributing.md` (the section explaining the marker). After the split the executable examples are in the generated project's docs; `check_doc_examples.py` exits 1 with "No … blocks found" on a tree with none, so PyFr's root must not run it over root pages.
5. **`generate_config_docs.py`** resolves `_REPOSITORY_ROOT = _SERVICE_ROOT.parents[1]` and reads/writes `docs/reference/configuration.md` there (lines 284–288, and `relative_to(_REPOSITORY_ROOT)` at 442). In a generated project that path is two directories above the project; it is why `tests/unit/test_config_docs.py`'s two tests and `just gates` (`config-docs-check`) fail in every render today (smoke test of PR 3: `FileNotFoundError: /home/runner/work/docs/reference/configuration.md`).
6. **The configuration page's generated table** (`<!-- generated: config-table -->` … `<!-- /generated: config-table -->`) lists `APP_DATABASE__*`, `APP_CACHE__*` and `APP_STORAGE__*` rows; `.env.example` in the template already wraps the same groups in `{%- if %}` blocks (lines 50–66, 108–131, 132–157), so the page gets the same treatment and the generator's output for a render equals the rendered page.
7. **Cross-links.** Twenty-two links go from pages that stay at the root to pages that move; nine go the other way (`supply-chain.md` → `roadmap.md`, `contributing.md`; `commands.md` → `getting-started.md`, `contributing.md`; `run-in-a-container.md` → `getting-started.md`; `outbound-http.md` → `roadmap.md`, `glossary.md`; `add-a-backend.md` → `why-a-template.md`; `architecture.md` → `roadmap.md`) plus `adr/README.md`'s rows for 0002, 0003 and 0017. MkDocs' `unrecognized_links: warn` under `--strict` fails a relative link to a page outside the site, so every cross-site link becomes an absolute URL.
8. **MkDocs reads `!ENV [NAME, default]`** natively (`site_url: !ENV [SITE_URL, "https://…"]`), and `mkdocs build --site-dir <path>` accepts a path relative to the working directory; `mkdocs build` cleans its own site directory only, so PyFr's site can be built first into `site/` and the reference service's second into `site/reference-service/`.
9. **The root's `dev` group has no MkDocs**; `mkdocs` and `mkdocs-material` are in the `docs` group. A generation test that builds a render's site with the root's MkDocs needs both groups in the test environment: the `test` recipe becomes `uv run --group dev --group docs pytest tests/`.
10. **Action pins** the generated `docs.yml` and documentation jobs need are all in the root's workflows at one ref each (`actions/configure-pages@v6`, `actions/upload-pages-artifact@v5`, `actions/deploy-pages@v5`, `lycheeverse/lychee-action@v2`), so `tests/test_regen.py::test_the_template_workflows_pin_what_the_root_workflows_pin` stays green.
11. **`mkdocs serve` and the service both default to port 8000** (`reference/commands.md`, "Two different servers, one port"); the generated project's `just docs` serves on 8001.
12. **The root's `links` CI job** runs `lycheeverse/lychee-action@v2` with `--config lychee.toml 'docs/**/*.md' README.md`; the template body's Markdown carries Jinja inside URLs, so lychee must check the rendered example's docs, not the template's.

## File structure

Template body (`{{cookiecutter.project_slug}}/`):
- Create: `mkdocs.yml`, `lychee.toml`, `docs/index.md`, `docs/contributing.md`, `docs/glossary.md`, `.github/workflows/docs.yml`
- Move in (`git mv` from `docs/`): `getting-started.md`, `runbook.md`, `guides/*.md` (4), `reference/*.md` (8), `explanation/architecture.md`, `explanation/layers.md`, `explanation/testing.md`, `adr/0001-…`, `adr/0004-…` … `adr/0016-…` (14), `adr/README.md` (then trimmed), `adr/template.md` (copied — both sites keep one)
- Move in (`git mv` from `scripts/` and `tests/`): `scripts/check_docs_updated.py`, `scripts/check_docs_freshness.py`, `scripts/check_doc_examples.py`, `tests/unit/test_check_docs_freshness.py`, `tests/unit/test_check_doc_examples.py`
- Modify: `pyproject.toml` (`docs` group), `justfile` (`docs-install`, `docs`, `docs-build`, `links`, `docs-freshness`; `docs-examples` path), `.github/workflows/ci.yml` (five documentation jobs), `.github/workflows/nightly.yml` (`links`), `.github/dependabot.yml` (`no-docs-needed` label), `README.md` (settings list), `scripts/generate_config_docs.py`

Root:
- Modify: `mkdocs.yml` (nav), `justfile` (`docs-build`, `docs-freshness`, `test`), `.github/workflows/docs.yml`, `.github/workflows/ci.yml` (`docs-freshness`, `docs-warnings`, `links` jobs), `lychee.toml`, `README.md`, `docs/index.md`, `docs/getting-started.md` (rewritten), `docs/contributing.md` (rewritten), `docs/glossary.md` (trimmed), `docs/roadmap.md`, `docs/adr/README.md` (trimmed), `docs/adr/0017-…` (one consequence), `tests/test_generation.py` (docs invariants, site builds, identity test)
- Rendered by `just regen`: `examples/reference-service/**` (docs, scripts, tests, workflows), `examples/reference-service/uv.lock`

---

### Task 1: The hygiene scripts move into the template

**Files:**
- Move: `scripts/check_docs_updated.py` → `{{cookiecutter.project_slug}}/scripts/check_docs_updated.py`; `scripts/check_docs_freshness.py` → `{{cookiecutter.project_slug}}/scripts/check_docs_freshness.py`; `scripts/check_doc_examples.py` → `{{cookiecutter.project_slug}}/scripts/check_doc_examples.py`; `tests/test_check_docs_freshness.py` → `{{cookiecutter.project_slug}}/tests/unit/test_check_docs_freshness.py`; `tests/test_check_doc_examples.py` → `{{cookiecutter.project_slug}}/tests/unit/test_check_doc_examples.py`
- Modify: the three scripts (defaults for a generated project; options for PyFr's root use); the two tests (`sys.path`); root `justfile` (`docs-freshness`); root `.github/workflows/ci.yml` (`docs-freshness`, `docs-warnings` jobs); `{{cookiecutter.project_slug}}/justfile` (`docs-examples`, new `docs-freshness`)

**Interfaces:**
- Produces: `check_docs_updated.py [--source PREFIX]... [--docs PATH]... [--exclude-docs PREFIX] BASE HEAD` (defaults `--source src/`, `--docs docs/ README.md mkdocs.yml`, no exclusion); `check_docs_freshness.py [--exclude PREFIX]... BASE HEAD` (default exclusion `docs/adr/`; `git diff --relative`); `check_doc_examples.py [DOCS_ROOT]` unchanged. Root callers pass `--source '{{cookiecutter.project_slug}}/src/' --docs docs/ --docs README.md --docs mkdocs.yml --docs '{{cookiecutter.project_slug}}/docs/' --exclude-docs docs/superpowers/` and `--exclude docs/superpowers/` respectively.

- [ ] **Step 1: Move the files**

```bash
git mv scripts/check_docs_updated.py scripts/check_docs_freshness.py scripts/check_doc_examples.py '{{cookiecutter.project_slug}}/scripts/'
git mv tests/test_check_docs_freshness.py tests/test_check_doc_examples.py '{{cookiecutter.project_slug}}/tests/unit/'
```

In both moved tests change `parents[1] / "scripts"` to `parents[2] / "scripts"` (they now sit one level deeper). Run `ruff format` on them under the template's rules is impossible (Jinja); instead, after Step 5's `just regen`, `(cd examples/reference-service && just lint)` proves the rendered copies are clean.

- [ ] **Step 2: `check_docs_updated.py` takes its trees as options**

Replace the module's constants and `main` so that:

```python
# A generated project's source lives at src/; PyFr's own root run names the
# template body instead (--source '{{cookiecutter.project_slug}}/src/').
DEFAULT_SOURCE_PREFIXES = ("src/",)
# What counts as having documented the change.
DEFAULT_DOCS_PATHS = ("docs/", "README.md", "mkdocs.yml")

LABEL = "no-docs-needed"
```

`source_changes(paths, prefixes)` and `touches_docs(paths, docs_paths, excluded_prefix)` take their configuration as arguments; `main` parses with `argparse`: `--source` (action `append`), `--docs` (action `append`), `--exclude-docs` (one prefix, default `None`), positional `base`, `head`. When `--source` / `--docs` are not given, the defaults apply. Keep the usage text and the failure message (list the source changes, say the label is the escape hatch), replacing `docs/       the documentation site` lines with the configured docs paths.

- [ ] **Step 3: `check_docs_freshness.py` works from any directory**

- `EXCLUDED_PREFIXES = ("docs/adr/",)` with its comment trimmed to the ADR paragraph; a new `--exclude` option (action `append`) adds prefixes; keep the two positional refs.
- In `changed_files`, run `["git", "diff", "--name-only", "--relative", f"{base}...{head}"]` with a comment: paths relative to the current directory, so the script serves a generated project from its root and the example from `examples/reference-service/` with the same `covers:` paths.
- Module docstring: "See docs/contributing.md" → "See the contributing page".

`check_doc_examples.py` needs no change.

- [ ] **Step 4: The callers**

Root `justfile`:

```just
# Documentation hygiene warnings for a pull request range. Never fails --
# see docs/contributing.md for why, and for what has to be true before
# these become hard failures. The script is the reference service's
# rendered copy: the template owns it (spec §9.1), and this is the one
# place PyFr's own pages are checked with it.
docs-freshness base="origin/main" head="HEAD":
    uv run --group docs python examples/reference-service/scripts/check_docs_freshness.py --exclude docs/superpowers/ {{base}} {{head}}
```

Root `.github/workflows/ci.yml`, `docs-freshness` job's step:

```yaml
        # The script is the reference service's rendered copy (the template
        # owns it); the options name PyFr's own trees: a change under the
        # template body's src/ must touch the root docs, the template's
        # docs, the README or mkdocs.yml.
        run: >-
          python3 examples/reference-service/scripts/check_docs_updated.py
          --source '{{cookiecutter.project_slug}}/src/'
          --docs docs/ --docs README.md --docs mkdocs.yml
          --docs '{{cookiecutter.project_slug}}/docs/'
          --exclude-docs docs/superpowers/
          "$BASE_SHA" HEAD
```

(`docs-warnings` still runs `just docs-freshness "$BASE_SHA" HEAD`; its comment's script path becomes `examples/reference-service/scripts/check_docs_freshness.py`.)

Template `justfile`, `docs-examples`: `python3 ../../scripts/check_doc_examples.py ../../docs` → `python3 scripts/check_doc_examples.py docs`, and add after it:

```just

# Documentation hygiene warnings for a pull request range: a stale
# `last_reviewed` date, or a `covers:` path that changed while its page did
# not. Never fails -- see the contributing page for what has to be true
# before these become hard failures.
docs-freshness base="origin/main" head="HEAD":
    uv run --group docs python scripts/check_docs_freshness.py {% raw %}{{base}} {{head}}{% endraw %}
```

(`--group docs` exists from Task 2; until then the recipe is inert — nothing calls it.)

- [ ] **Step 5: Regenerate, verify, commit**

```bash
just regen && git status --short
(cd examples/reference-service && uv sync -q && just lint && uv run pytest tests/unit/test_check_docs_freshness.py tests/unit/test_check_doc_examples.py -q)
just lint && just check && just precommit
uv run --group dev pre-commit run check-yaml --files .github/workflows/ci.yml
```

Expected: the five files appear under the example (renames); the two moved tests pass there; root `just check` passes (root `tests/` now holds the generation, golden, hooks and regen tests only). Prove the root call works: `just docs-freshness origin/main HEAD` prints its report (warnings or none) and exits 0; `python3 examples/reference-service/scripts/check_docs_updated.py --source '{{cookiecutter.project_slug}}/src/' --docs docs/ origin/main HEAD` exits 0 (this branch touches no template `src/`).

```bash
git add -A
git commit -m "refactor(template): move the documentation hygiene scripts into the template"
```

---

### Task 2: The pages move, and both sites build

**Files:**
- Create: `{{cookiecutter.project_slug}}/mkdocs.yml`, `{{cookiecutter.project_slug}}/lychee.toml`, `{{cookiecutter.project_slug}}/docs/index.md`
- Move (`git mv` from `docs/`): `getting-started.md`, `runbook.md`, `guides/add-a-backend.md`, `guides/add-an-endpoint.md`, `guides/outbound-http.md`, `guides/run-in-a-container.md`, `reference/commands.md`, `reference/configuration.md`, `reference/contract.md`, `reference/errors.md`, `reference/http-api.md`, `reference/logging.md`, `reference/observability.md`, `reference/supply-chain.md`, `explanation/architecture.md`, `explanation/layers.md`, `explanation/testing.md`, `adr/0001-four-layer-dependency-rule.md`, `adr/0004-…` through `adr/0016-…` (13 files), `adr/README.md`; copy `adr/template.md`
- Modify: root `mkdocs.yml` (nav), root `docs/adr/README.md` (new, trimmed), root `docs/index.md`, `docs/contributing.md`, `docs/glossary.md`, `docs/roadmap.md`, `docs/explanation/why-a-template.md`, `docs/adr/0002-…`, `0003-…`, `0017-…` (cross-links only), root `lychee.toml`, root `justfile` (`docs-build`, `test`), `{{cookiecutter.project_slug}}/pyproject.toml`, `{{cookiecutter.project_slug}}/justfile`, `{{cookiecutter.project_slug}}/.gitignore` (already ignores `site/`), `tests/test_generation.py` (site-build test)
- Regenerated: `examples/reference-service/**`, `examples/reference-service/uv.lock`

**Interfaces:**
- Produces: the template's `docs/` tree and `mkdocs.yml` nav that Tasks 3–7 edit; root `just docs-build` builds both sites; `tests/test_generation.py::test_the_two_extreme_renders_build_their_sites`; `render_site(root: Path) -> subprocess.CompletedProcess[str]` helper.

- [ ] **Step 1: The site-build test first**

Root `justfile`, `test` recipe:

```just
# The repository's own script tests. Both groups: the generation tests
# build a render's documentation site with the root's MkDocs.
test:
    uv run --group dev --group docs pytest tests/
```

Append to `tests/test_generation.py`:

```python
def build_site(root: Path) -> subprocess.CompletedProcess[str]:
    # The root's MkDocs over the render's own mkdocs.yml: no `uv sync` in
    # the render, so no network and no second toolchain. `site_url` reads
    # SITE_URL through `!ENV`; unset, the default applies.
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--config-file",
            str(root / "mkdocs.yml"),
            "--site-dir",
            str(root / "site"),
        ],
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize("answers", [EVERYTHING_ON, COMBINATIONS[-1]], ids=combination_id)
def test_the_two_extreme_renders_build_their_sites(cookies, answers) -> None:
    # Every page, every nav entry and every cross-reference must resolve
    # with everything on and with everything off; the six other
    # combinations are covered by the full-suite tests (PR 5).
    root = render(cookies, **answers)
    built = build_site(root)
    assert built.returncode == 0, built.stdout + built.stderr
    assert (root / "site" / "index.html").is_file()
```

Run: `uv run --group dev --group docs pytest tests/test_generation.py -q -k build_their_sites`
Expected: 2 FAIL (`mkdocs.yml` does not exist in the render).

- [ ] **Step 2: Move the pages**

```bash
cd '{{cookiecutter.project_slug}}' && mkdir -p docs/guides docs/reference docs/explanation docs/adr && cd ..
git mv docs/getting-started.md docs/runbook.md '{{cookiecutter.project_slug}}/docs/'
git mv docs/guides/*.md '{{cookiecutter.project_slug}}/docs/guides/'
git mv docs/reference/*.md '{{cookiecutter.project_slug}}/docs/reference/'
git mv docs/explanation/architecture.md docs/explanation/layers.md docs/explanation/testing.md '{{cookiecutter.project_slug}}/docs/explanation/'
git mv docs/adr/0001-*.md docs/adr/0004-*.md docs/adr/0005-*.md docs/adr/0006-*.md docs/adr/0007-*.md docs/adr/0008-*.md docs/adr/0009-*.md docs/adr/0010-*.md docs/adr/0011-*.md docs/adr/0012-*.md docs/adr/0013-*.md docs/adr/0014-*.md docs/adr/0015-*.md docs/adr/0016-*.md '{{cookiecutter.project_slug}}/docs/adr/'
git mv docs/adr/README.md '{{cookiecutter.project_slug}}/docs/adr/README.md'
cp docs/adr/template.md '{{cookiecutter.project_slug}}/docs/adr/template.md'
```

- [ ] **Step 3: Front matter and cross-links in the moved pages**

In every moved page's `covers:` list, strip the `examples/reference-service/` prefix and substitute `reference_service` → `{{ cookiecutter.package_name }}` (for example `src/{{ cookiecutter.package_name }}/config_check.py`). `reference/commands.md`'s `covers:` loses its root `justfile` entry (the root recipes leave this page in Task 7).

Links from a moved page to a page that stays at the root become absolute PyFr URLs (Verified Fact 7): `../roadmap.md#…` → `https://emadmokhtar.github.io/pyfr/roadmap/#…`; `../contributing.md#…` → `https://emadmokhtar.github.io/pyfr/contributing/#…`; `../glossary.md` stays as it is (the template gets its own glossary — a placeholder now, see Step 4; Task 7 writes it); `../getting-started.md#…` → `../getting-started.md#…` unchanged (it moved too); `../explanation/why-a-template.md#…` → `https://emadmokhtar.github.io/pyfr/explanation/why-a-template/#…`. In the moved `adr/README.md`, the rows for 0002, 0003 and 0017 link to `https://emadmokhtar.github.io/pyfr/adr/0002-cookiecutter-over-copier-and-cruft/` etc., with a sentence above the table: "Three decisions belong to PyFr, the template this project was generated from, and are recorded on its site: …".

Links from a root page to a moved page become absolute reference-service URLs: `reference/commands.md` → `https://emadmokhtar.github.io/pyfr/reference-service/reference/commands/`, `guides/…`, `runbook.md` → `…/reference-service/runbook/`, `explanation/architecture.md` → `…/reference-service/explanation/architecture/`, `adr/0004-…md` → `…/reference-service/adr/0004-golang-migrate-owns-the-schema/`. The root `adr/README.md` is recreated with the three root ADRs (0002, 0003, 0017) and one sentence pointing at the reference service's decisions page. Anchors (`#…`) are kept.

Root `lychee.toml`, `exclude`, add with its comment:

```toml
    # PyFr's own site, deployed by the same workflow that builds it: a link
    # to a page added in this branch resolves only after the deploy, and
    # `mkdocs build --strict` already proves every page and anchor exists.
    "^https://emadmokhtar\\.github\\.io/pyfr/",
```

- [ ] **Step 4: The template's site**

`{{cookiecutter.project_slug}}/mkdocs.yml`:

```yaml
site_name: {{ cookiecutter.project_name }}
site_description: {{ cookiecutter.description }}
# The project's own GitHub Pages site by default; PyFr's repository builds
# this same tree under its own site and sets SITE_URL to say so.
site_url: !ENV [SITE_URL, "https://{{ cookiecutter.github_org | lower }}.github.io/{{ cookiecutter.project_slug }}/"]
repo_url: https://github.com/{{ cookiecutter.github_org }}/{{ cookiecutter.project_slug }}
repo_name: {{ cookiecutter.github_org }}/{{ cookiecutter.project_slug }}
edit_uri: edit/main/docs/
{%- if cookiecutter.license == "Apache-2.0" %}
copyright: Licensed under the Apache License 2.0
{%- elif cookiecutter.license == "MIT" %}
copyright: Licensed under the MIT License
{%- elif cookiecutter.license == "MPL-2.0" %}
copyright: Licensed under the Mozilla Public License 2.0
{%- else %}
copyright: Copyright {{ cookiecutter.author_name }}. All rights reserved.
{%- endif %}

validation:
  # A reference that no longer resolves is a broken page, and `--strict`
  # turns each of these into a build failure rather than a warning nobody
  # reads.
  anchors: warn
  absolute_links: warn
  unrecognized_links: warn

# A skeleton to copy for the next decision record, not a page to read.
exclude_docs: |
  adr/template.md

theme:
  name: material
  features:
    - navigation.sections
    - navigation.top
    - navigation.tracking
    - content.code.copy
    - content.action.edit
    - search.highlight
    - toc.follow
  palette:
    - media: "(prefers-color-scheme: light)"
      scheme: default
      primary: deep orange
      accent: deep orange
      toggle:
        icon: material/weather-night
        name: Switch to dark mode
    - media: "(prefers-color-scheme: dark)"
      scheme: slate
      primary: deep orange
      accent: deep orange
      toggle:
        icon: material/weather-sunny
        name: Switch to light mode

markdown_extensions:
  - admonition
  - attr_list
  - tables
  - toc:
      permalink: true
  - pymdownx.details
  - pymdownx.superfences
  - pymdownx.tabbed:
      alternate_style: true
  # base_path reaches the project root so a page can include a file that
  # lives outside docs/ instead of duplicating it. check_paths turns a
  # missing include into a build error rather than a silently empty page.
  - pymdownx.snippets:
      base_path: ["."]
      check_paths: true

nav:
  - Home: index.md
  - Getting started: getting-started.md
  - Runbook: runbook.md
  - Guides:
      - Add an endpoint: guides/add-an-endpoint.md
      - Add a backend: guides/add-a-backend.md
      - Run in a container: guides/run-in-a-container.md
      - Outbound HTTP calls: guides/outbound-http.md
  - Reference:
      - Commands: reference/commands.md
      - Configuration: reference/configuration.md
      - HTTP API: reference/http-api.md
      - The API contract: reference/contract.md
      - Errors: reference/errors.md
      - Logging: reference/logging.md
      - Observability: reference/observability.md
      - Supply chain: reference/supply-chain.md
  - Decisions:
      - Overview: adr/README.md
      - 0001 Four-layer dependency rule: adr/0001-four-layer-dependency-rule.md
      - 0004 golang-migrate owns the schema: adr/0004-golang-migrate-owns-the-schema.md
      - 0005 In-memory adapters are a supported configuration: adr/0005-in-memory-adapters-are-a-supported-configuration.md
      - 0006 The cache is fail-open, always: adr/0006-the-cache-is-fail-open-always.md
      - 0007 Emit OpenTelemetry and stop there: adr/0007-emit-opentelemetry-and-stop.md
      - 0008 Standard output is the source of truth for logs: adr/0008-standard-output-is-the-source-of-truth-for-logs.md
      - 0009 RFC 9457 Problem Details for every error: adr/0009-rfc-9457-problem-details-for-every-error.md
      - 0010 The OpenAPI document is committed and drift-gated: adr/0010-the-openapi-document-is-committed-and-drift-gated.md
      - 0011 readyz reports optional dependencies without gating: adr/0011-readyz-reports-optional-dependencies-without-gating.md
      - 0012 mypy is strict on the inner layers only: adr/0012-mypy-is-strict-on-the-inner-layers-only.md
      - 0013 Redact by key name, in the shared processor chain: adr/0013-redaction-is-a-processor-in-the-shared-chain.md
      - 0014 Dependabot, and one pin per tool: adr/0014-dependabot-and-one-pin-per-tool.md
      - 0015 Images are published on release, under the repository's version: adr/0015-images-are-published-on-release-under-the-repository-version.md
      - 0016 Image scanning fails on fixed findings, and exemptions expire: adr/0016-image-scanning-fails-on-fixed-findings-and-exemptions-expire.md
  - Explanation:
      - Architecture: explanation/architecture.md
      - Layers and the dependency rule: explanation/layers.md
      - Testing strategy: explanation/testing.md
  - Project:
      - Contributing: contributing.md
      - Glossary: glossary.md
```

(`{%- elif %}` is a Jinja tag like the others; Task 4 makes the 0004 and 0006 entries conditional.)

`{{cookiecutter.project_slug}}/docs/index.md` (new; Task 7 expands it):

```markdown
---
last_reviewed: 2026-09-13
---

# {{ cookiecutter.project_name }}

{{ cookiecutter.description }}

This site documents the service: how to run it ([Getting started](getting-started.md)),
what to do when it misbehaves ([Runbook](runbook.md)), how to change it
(Guides), what it exposes (Reference), and why it is built the way it is
(Decisions, Explanation).

The service was generated from [PyFr](https://github.com/EmadMokhtar/pyfr),
a cookiecutter template for production-ready Python microservices; PyFr's
own site describes the template.
```

Placeholders for `docs/contributing.md` and `docs/glossary.md` in the template so the nav resolves (Task 7 writes them): each a front matter block, a title, and one sentence "Written in Task 7 of the M7 PR 4 plan." — **Task 7 must replace both**.

`{{cookiecutter.project_slug}}/lychee.toml`: the root file with these differences — the user agent's URL `+https://github.com/{{ cookiecutter.github_org }}/{{ cookiecutter.project_slug }}`; the edit-link exclusion `^https://github\\.com/{{ cookiecutter.github_org }}/{{ cookiecutter.project_slug }}/edit/`; the `docs/superpowers` exclusion and the `blob/main/docs/superpowers/` pattern removed; `exclude_path` = `["site", ".venv", "docs/adr/template.md"]`.

`{{cookiecutter.project_slug}}/pyproject.toml`, after the `dev` group:

```toml
# The documentation site (docs/, mkdocs.yml). Its own group so `uv sync`
# for the service does not install a static-site generator.
docs = [
    # Capped below 2.0: MkDocs 2.0 removes the plugin system entirely, with
    # no migration path, which would break mkdocs-material and the docs
    # build outright.
    "mkdocs>=1.6,<2",
    "mkdocs-material>=9.5,<10",
]
```

`{{cookiecutter.project_slug}}/justfile`, before the `docs-examples` recipe:

```just
# Install the documentation toolchain.
docs-install:
    uv sync --group docs

# Serve a live preview on http://127.0.0.1:8001, rebuilding on save. One
# above the service's default port, so `just dev` and this can run together.
docs:
    uv run --group docs mkdocs serve --dev-addr 127.0.0.1:8001

# Build the site into site/ with --strict, exactly as CI does.
docs-build:
    # --strict turns a warning into a failure: a link to a page that no
    # longer exists, a renamed heading anchor, or an unresolvable include
    # each fail the build rather than printing a warning nobody reads.
    uv run --group docs mkdocs build --strict

# Dead external links. Internal ones are already `mkdocs build --strict`'s job.
links:
    # Needs the lychee binary: `brew install lychee`, or run it in CI,
    # where the action provides it.
    lychee --config lychee.toml --no-progress 'docs/**/*.md' README.md
```

- [ ] **Step 5: The root's site**

Root `mkdocs.yml` nav becomes:

```yaml
nav:
  - Home: index.md
  - Getting started: getting-started.md
  - Decisions:
      - Overview: adr/README.md
      - 0002 cookiecutter over Copier and cruft: adr/0002-cookiecutter-over-copier-and-cruft.md
      - 0003 uv over pip and Poetry: adr/0003-uv-over-pip-and-poetry.md
      - 0017 The template is the source of truth: adr/0017-the-template-is-the-source-of-truth.md
  - Explanation:
      - Why a template, not a framework: explanation/why-a-template.md
  - Project:
      - Roadmap: roadmap.md
      - Contributing: contributing.md
      - Glossary: glossary.md
```

Root `justfile`, `docs-build`:

```just
# Build both sites into site/ with --strict, exactly as CI does: PyFr's own
# at the top, and the reference service's rendered site -- built from
# examples/reference-service/ with its own toolchain and its own
# mkdocs.yml -- under site/reference-service/. One deploy, two sites
# (spec §9.2). SITE_URL tells the second build where it will live; a
# generated project leaves it unset and gets its own Pages URL.
docs-build:
    # --strict turns a warning into a failure: a link to a page that no
    # longer exists, a renamed heading anchor, or an unresolvable include
    # each fail the build rather than printing a warning nobody reads.
    uv run mkdocs build --strict
    cd examples/reference-service && SITE_URL=https://emadmokhtar.github.io/pyfr/reference-service/ uv run --group docs mkdocs build --strict --site-dir ../../site/reference-service
```

- [ ] **Step 6: Regenerate, build, test, commit**

```bash
just regen && (cd examples/reference-service && uv lock && uv sync --group docs)
just docs-build && ls site/reference-service/index.html
uv run --group dev --group docs pytest tests/test_generation.py -q -k "build_their_sites or no_template_syntax"
just lint && just check && just precommit
(cd examples/reference-service && just check && just docs-build)
```

Expected: both builds succeed; the two site-build cases pass; everything green. Then check the move preserved the prose: `git diff -M --stat HEAD -- docs '{{cookiecutter.project_slug}}/docs'` shows renames with small per-file changes (front matter and links only); read `git diff -M HEAD -- '{{cookiecutter.project_slug}}/docs/runbook.md'` once to confirm.

```bash
git add -A
git commit -m "feat(template): give a generated project its own documentation site"
```

---

### Task 3: Identity in the moved pages

**Files:**
- Modify: every page under `{{cookiecutter.project_slug}}/docs/` that names the reference service, its package or its owner (the counts: `reference-service` ×~70, `reference_service` ×~20, `emadmokhtar` ×~15 across the moved pages)
- Modify: `tests/test_generation.py` (identity test)
- Regenerated: `examples/reference-service/docs/**`

- [ ] **Step 1: The test first**

Append to `tests/test_generation.py`:

```python
# The reference service's identity must never leak into a project with a
# different one. PyFr's own URLs are the exception: a generated project
# links back to the template it came from.
IDENTITY_LEAKS = ("reference-service", "reference_service", "Reference Service")
PYFR_URLS = ("github.com/EmadMokhtar/pyfr", "emadmokhtar.github.io/pyfr/")


def test_the_docs_carry_the_answers_not_the_reference_identity(cookies) -> None:
    root = render(cookies)  # default answers: my-service, my_service, your-org
    offenders = []
    for path in sorted((root / "docs").rglob("*.md")):
        text = path.read_text()
        for line in text.splitlines():
            stripped = line
            for url in PYFR_URLS:
                stripped = stripped.replace(url, "")
            if any(leak in stripped for leak in IDENTITY_LEAKS) or "emadmokhtar" in stripped.lower():
                offenders.append(f"{path.relative_to(root)}: {line.strip()[:80]}")
    assert offenders == []
```

Run: `uv run --group dev --group docs pytest tests/test_generation.py -q -k reference_identity`
Expected: FAIL with the offender list.

- [ ] **Step 2: Substitute, page by page**

Apply the Global Constraints' identity rules to every moved page. Use `grep -rn "reference-service\|reference_service\|Reference Service\|[Ee]madMokhtar\|emadmokhtar" '{{cookiecutter.project_slug}}/docs'` as the worklist and decide each hit: a project URL, image name, package path or service name becomes the substitution; "the reference service" becomes "the service"; a PyFr URL stays. Where a sentence only makes sense in PyFr's repository (e.g. "PyFr's reference service carries…", "`examples/reference-service/`"), reword minimally so it is true in a generated project — and list every such reword in your report, with before/after.

- [ ] **Step 3: Regenerate; the everything-on render must still read as before**

```bash
just regen
uv run --group dev --group docs pytest tests/test_generation.py -q -k "reference_identity or build_their_sites or no_template_syntax"
git diff --stat HEAD -- examples/reference-service/docs
```

Expected: tests pass; the example's docs diff against HEAD is **empty or near-empty** — for the reference answers every substitution renders back to the old text, so the only rendered changes are the rewords you listed. Paste `git diff HEAD -- examples/reference-service/docs` into the report.

```bash
just lint && just check && just precommit
git add -A
git commit -m "feat(template): render the project's identity into its documentation"
```

---

### Task 4: Backend conditionals in the docs

**Files:**
- Modify: `{{cookiecutter.project_slug}}/mkdocs.yml` (nav), `{{cookiecutter.project_slug}}/docs/reference/configuration.md`, `reference/commands.md`, `reference/observability.md`, `reference/supply-chain.md`, `runbook.md`, `guides/run-in-a-container.md`, `explanation/layers.md`, `adr/README.md`, `docs/index.md` (nothing yet), and any other moved page whose section documents a present component
- Modify: `tests/test_generation.py` (docs words in the invariant)
- Regenerated: `examples/reference-service/**`

**Interfaces:**
- Produces: `DOCS_BACKEND_PAGES` and the docs clause in `assert_invariant`.

- [ ] **Step 1: The invariant first**

In `tests/test_generation.py`, after `WORKFLOW_BACKEND_WORDS`, add:

```python
# Pages that document what the render HAS: a word of a pruned backend in
# them is a section that should have been conditional. Comparative prose
# elsewhere (an ADR weighing PostgreSQL against an in-memory store) is
# deliberately not policed.
DOCS_BACKEND_PAGES = (
    "docs/index.md",
    "docs/getting-started.md",
    "docs/runbook.md",
    "docs/reference/commands.md",
    "docs/reference/configuration.md",
    "docs/reference/observability.md",
    "docs/reference/supply-chain.md",
    "docs/guides/run-in-a-container.md",
    "docs/glossary.md",
    "mkdocs.yml",
)
DOCS_BACKEND_WORDS = {
    "database": ("postgres", "migrat", "schema.sql", "golang-migrate"),
    "cache": ("redis",),
    "object_storage": ("minio", " s3", "bucket"),
}
```

In `assert_invariant`, inside the `for key, spec in BACKEND.items():` loop, directly after the `assert (spec["env_prefix"] in env_example) == on, (key, "env")` line, add:

```python
        configuration = (root / "docs" / "reference" / "configuration.md").read_text()
        assert (spec["env_prefix"] in configuration) == on, (key, "configuration.md")
        if not on:
            for page in DOCS_BACKEND_PAGES:
                text = (root / page).read_text().lower()
                for word in DOCS_BACKEND_WORDS[key]:
                    assert word not in text, (key, page, word)
```

Run: `uv run --group dev --group docs pytest tests/test_generation.py -q -k carries_only`
Expected: the `none-*` cases fail, naming pages and words.

- [ ] **Step 2: Wrap the sections**

Work through the failures. For each page, wrap the smallest self-contained unit — a table row group, a paragraph, a `##`/`###` section, a nav entry — in the backend's `{%- if %}`, with the blank line inside the branch. Known units (from the heading maps; the failures will name the rest):

- `mkdocs.yml`: the nav entries for `0004 golang-migrate owns the schema` (database) and `0006 The cache is fail-open, always` (cache); `docs/adr/README.md`'s rows for 0004 and 0006 likewise.
- `reference/configuration.md`: the generated table's `APP_DATABASE__*`, `APP_CACHE__*`, `APP_STORAGE__*` rows (mirror `.env.example`'s three blocks); the paragraph after the table about leaving `APP_CACHE__DSN` / `APP_STORAGE__BUCKET` unset (cache / storage parts); `### The database URL carries no driver and no sslmode` (database); the `APP_DATABASE__DSN` mention under "Bad configuration stops the process" (database).
- `reference/commands.md`: `## The database` (database); `## The cache and the object store` — split into a cache part and a storage part, each conditional, and drop the heading's "and the object store" when storage is off (write two headings: `## The cache` and `## The object store`, each in its own block); in `## Tests and schema gates`, the schema-gate sentences (database); command-table rows naming `migrations`/`psql`/`redis-cli`/`minio-console`.
- `runbook.md`: `## A migration is dirty` (database); inside `## A dependency is down`, the PostgreSQL, Redis and MinIO paragraphs each in their block.
- `reference/observability.md`: `## Readiness reports the cache and the store…` — the cache sentences and the store sentences in their blocks (the heading becomes "Readiness reports optional dependencies, and gates on none"); `### The Redis panel shows latency, not pool usage` (cache).
- `reference/supply-chain.md`: every mention of the migrations image / `Dockerfile.migrations` / the `migrate/migrate` base (database).
- `guides/run-in-a-container.md`: migrations image and `migrate` service mentions (database); MinIO/Redis service mentions in the compose walkthrough.
- `explanation/layers.md`: `## What a port buys: the caching decorator` — keep the section (it explains ports) but its Redis-specific sentences go in a cache block; the anchor `#what-a-port-buys-the-caching-decorator` is linked from `configuration.md`'s cache row (inside the cache block, so it resolves whenever it is linked).
- `getting-started.md`: the seeded-orders and receipt walkthrough stays (the endpoints exist in every render); sentences naming PostgreSQL/Redis/MinIO containers in `## Run it` go in their blocks.

After every page: `just regen`, then rerun the matrix and the two site builds; iterate until green. Then prove the everything-on render is unchanged: `git diff HEAD -- examples/reference-service/docs examples/reference-service/mkdocs.yml` must show only the two-heading split in `commands.md` and the observability heading (list anything else in the report).

- [ ] **Step 3: Verify and commit**

```bash
uv run --group dev --group docs pytest tests -q
just lint && just check && just precommit
(cd examples/reference-service && just check && just docs-build)
git add -A
git commit -m "feat(template): prune each backend's documentation with the backend"
```

---

### Task 5: The configuration generator finds its page in a generated project

**Files:**
- Modify: `{{cookiecutter.project_slug}}/scripts/generate_config_docs.py:284-288,442,461`
- Modify: `docs/roadmap.md` (the caveat sentence), `{{cookiecutter.project_slug}}/README.md` (the caveat paragraph PR 3 added under "Continuous integration and releases")
- Regenerated: `examples/reference-service/**`

- [ ] **Step 1: The fix**

```python
_SERVICE_ROOT = Path(__file__).resolve().parents[1]

ENV_EXAMPLE = _SERVICE_ROOT / ".env.example"
CONFIGURATION_DOC = _SERVICE_ROOT / "docs" / "reference" / "configuration.md"
```

Delete `_REPOSITORY_ROOT`; at line ~442 `relative_to(_REPOSITORY_ROOT)` → `relative_to(_SERVICE_ROOT)`; the message at ~461 stays (`docs/reference/configuration.md` is now the project's own path). Read the file's module docstring and comments for any sentence that says the page lives at the repository root, and correct it.

- [ ] **Step 2: Prove it in the example and in a live render**

```bash
just regen
(cd examples/reference-service && uv run pytest tests/unit/test_config_docs.py -q && just config-docs-check)
scratch=$(mktemp -d) && uv run --group dev cookiecutter . --no-input --output-dir "$scratch" --default-config database=none cache=none object_storage=none && (cd "$scratch/my-service" && just gates && just test; echo "exit=$?") && rm -rf "$scratch"
```

Expected: the two tests pass in the example; `config-docs-check` clean; in the `none-none-none` live render `just gates` and `just test` exit 0 — **the two documented failures are gone**, and the generator's output for a pruned render equals the rendered page (the conditional blocks of Task 4 are right, or this step names the diff).

Then remove the caveats: in `docs/roadmap.md`, the sentence "Until the documentation site moves into the template, a generated project's `just check` fails … stay red until then." goes; in the template README, the paragraph "Until PyFr's next release moves the documentation site into the template, the `check` and `gates` jobs stay red: …" goes. `just regen`.

- [ ] **Step 3: Verify and commit**

```bash
just lint && just check && just precommit && (cd examples/reference-service && just check)
git add -A
git commit -m "fix(template): generate the configuration reference into the project's own docs"
```

---

### Task 6: Two sites, one deploy; the generated documentation jobs

**Files:**
- Modify: `.github/workflows/docs.yml` (root), `.github/workflows/ci.yml` (root `links` job)
- Create: `{{cookiecutter.project_slug}}/.github/workflows/docs.yml`
- Modify: `{{cookiecutter.project_slug}}/.github/workflows/ci.yml` (five jobs; `pull_request.types`), `{{cookiecutter.project_slug}}/.github/workflows/nightly.yml` (`links`), `{{cookiecutter.project_slug}}/.github/dependabot.yml` (labels), `{{cookiecutter.project_slug}}/README.md` (settings), `tests/test_generation.py` (`RAW_GUARDED_FILES`)
- Regenerated: `examples/reference-service/.github/**`

- [ ] **Step 1: Tests**

`RAW_GUARDED_FILES` gains `".github/workflows/docs.yml"`. Run the matrix — it passes vacuously until the file exists; `tests/test_regen.py::test_the_template_workflows_pin_what_the_root_workflows_pin` is the pin gate.

- [ ] **Step 2: PyFr's `docs.yml` builds both sites**

Root `.github/workflows/docs.yml`, `build` job: add an "Install just" step (`extractions/setup-just@v4`) after "Install uv", and replace the "Build the site" step with:

```yaml
      - name: Build both sites
        # `just docs-build` builds PyFr's site into site/ and the reference
        # service's rendered site into site/reference-service/ -- one
        # definition of the build, the same one a contributor runs.
        run: just docs-build
```

Its header comment gains one sentence: "The deploy carries two sites: PyFr's, and the reference service's own documentation under `reference-service/` — the site every generated project ships, rendered from the template (spec §9.2)."

Root `.github/workflows/ci.yml`, `links` job `args`: `--config lychee.toml --no-progress 'docs/**/*.md' README.md 'examples/reference-service/docs/**/*.md' examples/reference-service/README.md`, with a comment line: the template body's Markdown carries Jinja inside URLs, so the rendered example is what gets checked. Root `lychee.toml`, `exclude_path`: add `"{{cookiecutter.project_slug}}"` with the same comment, so `nightly.yml`'s `'**/*.md'` sweep skips the template body too.

- [ ] **Step 3: The generated `docs.yml`**

`{{cookiecutter.project_slug}}/.github/workflows/docs.yml` — the root file with: the header comment's reference `See docs/contributing.md, "One-time repository settings"` → `See README.md, "Continuous integration and releases"`; the build steps `Install uv` → `Install just` → `Install the documentation toolchain` (`uv sync --group docs`) → `Build the site` (`just docs-build`); `${{ steps.deployment.outputs.page_url }}` inside a raw region. Same `on:`, `permissions:`, `concurrency:`, `configure-pages@v6`, `upload-pages-artifact@v5` (`path: site`), `deploy-pages@v5`.

- [ ] **Step 4: The generated `ci.yml`, `nightly.yml`, `dependabot.yml`, README**

`ci.yml`: `on.pull_request` gains the root's `types: [opened, synchronize, reopened, labeled, unlabeled]` with the root's comment; add the root's `docs`, `docs-freshness`, `docs-warnings`, `links` and `docs-examples` jobs, each without `working-directory`, calling the project's own commands:
- `docs`: `uv sync --group docs` then `just docs-build` (comment: the site build with `--strict`; the drift check of the configuration reference runs in `just gates`).
- `docs-freshness`: `python3 scripts/check_docs_updated.py "$BASE_SHA" HEAD` (its defaults are this project's trees).
- `docs-warnings`: `uv sync --group docs` then `just docs-freshness "$BASE_SHA" HEAD`.
- `links`: `lycheeverse/lychee-action@v2`, `args: --config lychee.toml --no-progress 'docs/**/*.md' README.md`, `fail: true`.
- `docs-examples`: `just docs-examples` (the documented `curl` examples against a real running stack).
Raw regions around every `${{ }}` (`github.event.pull_request.labels.*.name`, `github.event.pull_request.base.sha`, `github.event_name` in `if:` strings need none — only `${{`). `nightly.yml`: the root's `links` job with `args: --config lychee.toml --no-progress '**/*.md'`.

`dependabot.yml`: every `labels:` becomes `["dependencies", "no-docs-needed"]`, and the header comment gains the root's sentence about the label ("Every PR carries `no-docs-needed`: a version bump is exactly the internal-only change ci.yml's docs-freshness job has that label for.").

README, "Continuous integration and releases": the table gains a row for `docs.yml` ("every push to `main`, or by hand" / "builds the documentation site with `mkdocs build --strict` and deploys it to GitHub Pages") and the `ci.yml` row's cell gains "; the documentation site build, the documentation-freshness gate, the external-link check and the documented examples"; the settings list grows to five with, first, "**Settings → Pages → Source = "GitHub Actions".** Without it `docs.yml`'s deploy job fails with an opaque error while its build job succeeds." and second "**A `no-docs-needed` label must exist**, or the documentation-freshness check has no escape hatch."; "Three settings" → "Five settings".

- [ ] **Step 5: Regenerate, check, commit**

```bash
just regen
uv run --group dev --group docs pytest tests -q
uv run --group dev pre-commit run check-yaml --files .github/workflows/docs.yml .github/workflows/ci.yml examples/reference-service/.github/workflows/*.yml examples/reference-service/.github/dependabot.yml
just lint && just check && just precommit
git add -A
git commit -m "feat(template): deploy a generated project's site, and both sites from pyfr's own workflow"
```

Expected: the invariant's `JUST_CALL` check confirms `docs-build`, `docs-freshness` and `docs-examples` exist in every render; the pin test stays green.

---

### Task 7: The root pages, and the project's own index, contributing and glossary

**Files:**
- Rewrite: `docs/index.md`, `docs/getting-started.md`, `docs/contributing.md`, `docs/glossary.md`, `README.md` (root)
- Modify: `docs/roadmap.md` (M7 row), `docs/adr/0017-…` (one consequence)
- Write: `{{cookiecutter.project_slug}}/docs/index.md` (expand), `{{cookiecutter.project_slug}}/docs/contributing.md`, `{{cookiecutter.project_slug}}/docs/glossary.md` (replacing Task 2's placeholders)
- Regenerated: `examples/reference-service/docs/**`

This task is prose. Every page keeps the site's voice (plain English, short sentences, definitions in place, no idioms) and its front matter (`last_reviewed: 2026-09-13`; `covers:` where a page tracks files). The reviewer checks each claim against the tree.

- [ ] **Step 1: The root pages**

`docs/index.md`: keep the opening; the status admonition says M7 is in progress with PRs 1–4 landed (the template renders, prunes, carries its own workflows and its own documentation site) and the full-suite tests still to come; add a section "The documentation a generated service ships" linking to `https://emadmokhtar.github.io/pyfr/reference-service/` — "the reference service's site, rendered from the template and deployed with this one; every generated project gets the same site about itself". Keep the section listing what a project gets.

`docs/getting-started.md` (about PyFr): "What you need" (uv; Docker for `just up`); "Generate a project" — `uvx cookiecutter gh:EmadMokhtar/pyfr`, then a table of the twelve prompts (name, meaning, default) copied from `cookiecutter.json`; "What the hook does" (git init, `uv sync`, `pre-commit install`, first commit — best effort, the message when a step fails); "Run it" — `cd <slug> && just up`, `just check`; "Where to go next" — the generated project's own site (`https://emadmokhtar.github.io/pyfr/reference-service/getting-started/` as the worked example), and the README's "Continuous integration and releases" for the repository settings.

`docs/contributing.md` (about PyFr): keep and reorder the existing sections — "Repository layout" (updated: `{{cookiecutter.project_slug}}/docs/` is the generated site; root `docs/` describes PyFr; `scripts/regen.py` is the only root script; the hygiene scripts live in the template and PyFr runs the example's copies), "Working on the template" (+ "Generated files", "Backends and pruning", "Dependabot and the template"), a new "Working on the documentation" that explains the two sites (which pages live where; `just docs-build` builds both; `SITE_URL`; cross-site links are absolute URLs; a moved page's `covers:` is project-relative), "Documentation ships with the change" (which script each CI job runs — the paths now under `examples/reference-service/scripts/`, with the options PyFr passes), "Conventional Commits are required", "One-time repository settings" (seven, unchanged), and a "Commands" table of the root justfile (moved here from the old `reference/commands.md`'s last section: `docs-install`, `docs`, `docs-build` (both sites), `links`, `test`, `precommit`, `regen`, `regen-check`, `adopt`, `audit`, `changelog`, `next-version`, `docs-freshness`, `check`). Drop the service sections that moved (`just security`, `.python-version`, the exec marker explanation goes to the template's contributing page).

`docs/glossary.md`: PyFr terms only — cookiecutter, template body, render, golden diff, `just regen`, `just adopt`, pruning, backend combination, the reference service, `.pyfr-answers.yml`, full-suite tests, Conventional Commits, Commitizen, Dependabot. Service terms (port, adapter, readiness tier, burn rate, SLO, Problem Details, …) move to the template's glossary.

`README.md` (root): "Try it in one command" becomes the cookiecutter command with two sentences on the prompts and the hook; "Documentation" links the PyFr site and the reference service's site; the status section says PRs 1–4 have landed and the full-suite tests remain; "What's in the box" and "Development" updated where they name moved pages (link to the reference-service site) or the old quick start. Keep the badge, credits and licence.

`docs/roadmap.md`, M7 row: append after the PR 3 sentence: "The fourth split the documentation: pages about the service moved into the template as a generated project's own MkDocs site — templatised, pruned per backend, built and deployed by its own `docs.yml` — the hygiene scripts moved with them, PyFr's `docs.yml` deploys both sites as one, and the configuration-reference lookup that kept a generated project's `check` and `gates` jobs red is fixed." and change "Still to come: …" to "Still to come: the full-suite tests."

`docs/adr/0017-…`, Consequences: add "- The documentation follows the same rule: pages about the service live in the template body and are rendered into the example's `docs/`; PyFr's own site links to that render as the documentation every generated project ships."

- [ ] **Step 2: The project's pages**

`{{cookiecutter.project_slug}}/docs/index.md`: Task 2's text plus a "What you get" list (the API with Problem Details, the four-layer architecture, OpenTelemetry, the readiness tiers, the container image(s), the workflows) — each item links to its page; nothing backend-specific outside a block.

`{{cookiecutter.project_slug}}/docs/contributing.md` (about the project): "Before you push" (`just check`, `just check-all`, `just security` — moved from the old root contributing.md's service paragraphs), "Documentation ships with the change" (the four hygiene mechanisms as they run in this project: `mkdocs build --strict`, `links`, the `<!-- exec -->` marker and `just docs-examples`, `last_reviewed`/`covers:` and `just docs-freshness`; the `no-docs-needed` label; the CI jobs by name), "Conventional Commits are required" (the hook, Commitizen from `uv.lock`, `just changelog` / `just next-version`), and a pointer to the README's "Continuous integration and releases" for the repository settings. Use `{{ cookiecutter.project_slug }}` where the project is named.

`{{cookiecutter.project_slug}}/docs/glossary.md`: the service terms from the old glossary, each in a backend block where it names one (the database terms, the cache terms, the object-store terms).

- [ ] **Step 3: Build, test, commit**

```bash
just regen
just docs-build && (cd examples/reference-service && just docs-build)
uv run --group dev --group docs pytest tests -q
just lint && just check && just precommit
just docs-freshness origin/main HEAD
git add -A
git commit -m "docs: describe pyfr at the root and the service on its own site"
```

---

### Task 8: Final verification

**Files:** none modified; this task reports.

- [ ] **Step 1: The root and the example**

```bash
uv run --group dev --group docs pytest tests -q
just lint && just check && just precommit
(cd examples/reference-service && just check && just docs-build && just lint)
git status --short
```

- [ ] **Step 2: Two live renders, now fully green**

```bash
scratch=$(mktemp -d)
uv run --group dev cookiecutter . --no-input --output-dir "$scratch/off" --default-config database=none cache=none object_storage=none
uv run --group dev cookiecutter . --no-input --output-dir "$scratch/on" --default-config
for tree in "$scratch/off/my-service" "$scratch/on/my-service"; do
  (cd "$tree" && ls .github/workflows docs && just check; echo "just check exit=$?"; just gates; echo "just gates exit=$?"; uv sync -q --group docs && just docs-build; echo "docs-build exit=$?")
done
rm -rf "$scratch"
```

Expected: `just check` exits 0 in both (no documented failures remain), `just gates` exits 0 (`config-docs-check` finds its page), `just docs-build` exits 0 in both. Record every output.

- [ ] **Step 3: Report**

`git log --oneline origin/main..HEAD`, the outputs above, and anything left undone.

---

## After the plan

The live smoke test again, with the user's go-ahead: generate, push to a scratch repository, enable Pages (Source = GitHub Actions), watch `CI` (now expected fully green), `Docs` (deploys the project's site) and `Release`.

## Self-review

- **Spec coverage.** §9.1 the split (Tasks 2, 3, 7), the hygiene scripts move and PyFr runs the example's copies (Task 1), the root `tests/` holds only PyFr's own tests (Task 1); §9.2 `mkdocs.yml` with `!ENV`, the `docs` group and recipes (Task 2), PyFr's `docs.yml` builds both and deploys one directory (Task 6), root pages link to `reference-service/` (Tasks 2, 7); §9.3 ADR 0017 exists since PR 1 — one consequence added (Task 7); §9.4 roadmap, README, index (Task 7; the "usable template"/**Done** wording waits for PR 5); §8's deferred jobs and `docs.yml` (Task 6); §14's configuration-reference risk (Tasks 4, 5); §10.1's tests extended (Tasks 2, 3, 4, 6).
- **Placeholders.** The prose tasks (3, 4, 7) give rules, worklists and the exact test that enforces them rather than the full text of thirty pages — the reviewer gate checks the pages; the mechanical tasks (1, 2, 5, 6) give exact code and YAML.
- **Type consistency.** `build_site` (Task 2) is used by the site-build test only; `DOCS_BACKEND_PAGES`/`DOCS_BACKEND_WORDS` (Task 4) live beside `WORKFLOW_BACKEND_WORDS`; `check_docs_updated.py`'s options (Task 1) are the ones the root `ci.yml` passes (Task 1) and the generated `ci.yml` omits (Task 6, defaults); `docs-freshness` recipe exists in the template from Task 1 and is called by the generated `ci.yml` in Task 6.
