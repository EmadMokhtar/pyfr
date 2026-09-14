# Repository-level commands: the documentation site, the root's own tests,
# and the template's regeneration loop (regen, regen-check, adopt).
#
# The reference service has its own justfile with its own recipes; run those
# from examples/reference-service/. The two projects are never synced
# together — see docs/contributing.md.

default:
    @just --list

# Install the documentation toolchain.
docs-install:
    uv sync --group docs

# Serve a live preview on http://127.0.0.1:8000, rebuilding on save.
docs:
    uv run mkdocs serve

# Build both sites into site/ with --strict, exactly as CI does: PyFr's own
# at the top, and the reference service's rendered site -- built from
# examples/reference-service/ with its own toolchain and its own
# mkdocs.yml -- under site/reference-service/. One deploy, two sites
# (spec §9.2). The environment tells the second build where it will live
# and which repository it belongs to; a generated project leaves all four
# unset and gets its own Pages URL and its own repository. The edit link
# opens the TEMPLATE page, not the rendered one: the example is never
# edited by hand (ADR 0017). The braces in that path are percent-encoded
# so the URL is valid -- and so `just` does not read them as its own
# interpolation.
docs-build:
    # --strict turns a warning into a failure: a link to a page that no
    # longer exists, a renamed heading anchor, or an unresolvable include
    # each fail the build rather than printing a warning nobody reads.
    uv run mkdocs build --strict
    cd examples/reference-service && \
        SITE_URL=https://emadmokhtar.github.io/pyfr/reference-service/ \
        REPO_URL=https://github.com/EmadMokhtar/pyfr \
        REPO_NAME=EmadMokhtar/pyfr \
        EDIT_URI='edit/main/%7B%7Bcookiecutter.project_slug%7D%7D/docs/' \
        uv run --group docs mkdocs build --strict --site-dir ../../site/reference-service
    # The links between the two sites are absolute URLs on the Pages host,
    # which neither `--strict` resolves nor lychee checks (they exist only
    # after the deploy); this resolves each one against the site/ just built.
    # With --repo-root it also resolves every link into this repository's
    # tree on GitHub found in the built HTML against the checkout: the edit
    # links above, which lychee is told to skip, and the ADRs' links into
    # the design archive, which it skips as well.
    uv run --group dev python scripts/check_site_links.py --repo-root . --exclude docs/superpowers docs README.md examples/reference-service/docs examples/reference-service/README.md

# Dead external links. Internal ones are already `mkdocs build --strict`'s job.
links:
    # Needs the lychee binary: `brew install lychee`, or run it in CI,
    # where the action provides it.
    # The rendered example's docs are checked here too: the template
    # body's own Markdown carries Jinja inside its URLs, so the rendered
    # copy is what a link checker can actually read.
    lychee --config lychee.toml --no-progress 'docs/**/*.md' README.md 'examples/reference-service/docs/**/*.md' examples/reference-service/README.md

# The repository's own script tests. Both groups: the generation tests
# build a render's documentation site with the root's MkDocs.
test:
    uv run --group dev --group docs pytest tests/

# The full-suite tests: render three combinations for real -- the hook
# runs `uv sync` and `git init` -- and run each project's own
# `just check-all`. Slow (a few minutes per combination) and needs Docker
# and the network. CI runs them on every merge to main and nightly
# (.github/workflows/full-suite.yml), never on a pull request; `just test`
# deselects them. `combination` narrows the run to one test id:
# everything-on, everything-off or postgres-only.
test-full-suite combination="":
    uv run --group dev pytest -m full_suite -k "{{combination}}" tests/test_generated_service.py

# The repository's git hooks over every tracked file. The reference service's
# own precommit recipe skips itself when it finds it is nested inside this
# repository; this recipe is the one that covers that tree here.
precommit:
    uv run --group dev pre-commit run --all-files

# Regenerate examples/reference-service from the template with the answers in
# tests/reference-answers.yaml. The template is the source of truth; run this
# after every change to {{cookiecutter.project_slug}}/ and commit the result.
# The release runs this as `cz bump`'s pre-bump hook; the nested `uv run`
# here is not `--locked`, which is safe because Commitizen's uv provider
# rewrites pyproject.toml and uv.lock together, so the lock is consistent
# when the hook runs.
regen:
    uv run --group dev python scripts/regen.py

# The golden diff: render and compare, writing nothing. CI's `golden` job.
regen-check:
    uv run --group dev python scripts/regen.py --check

# Copy Dependabot's edits to the rendered example back into the template,
# then check. Only for line-for-line replacements (a pin bump); anything else
# fails with the file name and is made in the template by hand.
adopt:
    uv run --group dev python scripts/regen.py --adopt

# ruff over the root's own Python -- hooks/, scripts/, src/, tests/ --
# then mypy over the published package. ruff.toml's extend-exclude keeps
# both out of the template body; the example is linted with its own
# ruff.toml, by its own `just lint`.
lint: typecheck
    uv run --group dev ruff check .
    uv run --group dev ruff format --check .

# mypy --strict over src/pyfr_cli, the one package this repository
# publishes (pyproject.toml's [tool.mypy] names the files).
typecheck:
    uv run --group dev mypy

# Build the pyfr-cli wheel and run its console script from it, exactly as
# CI does (M8 spec, section 8.4). Needs the network: uvx resolves the
# wheel's dependencies into a throwaway environment.
wheel:
    #!/usr/bin/env bash
    set -euo pipefail
    rm -rf dist
    uv build --wheel
    uvx --from dist/pyfr_cli-*.whl pyfr --version

# Audit the documentation and release toolchain's lock the same way the
# reference service audits its own -- see that justfile's `audit` for the
# flags. Two locks, two audits, one CI job.
#
# A `#!`-shebang recipe with `pipefail`, not a plain line: the gate must
# be red when the producer fails, and without `pipefail` a failing
# `uv export` leaves pip-audit reading an empty stdin, which passes
# (verified: an empty stdin prints "No known vulnerabilities found" and
# exits 0).
audit:
    #!/usr/bin/env bash
    set -euo pipefail
    uv export --frozen --all-groups --format requirements.txt --no-emit-project \
        | uvx pip-audit==2.10.1 --requirement /dev/stdin --disable-pip --require-hashes --strict --progress-spinner off

# Preview the changelog entry the next release will write. Read-only.
changelog:
    uv run --locked --group dev cz changelog --dry-run --incremental

# Preview the version the next release will choose, without doing it.
next-version:
    # The release itself runs in CI (.github/workflows/release.yml); this is
    # for answering "what will merging this produce?" before merging.
    uv run --locked --group dev cz bump --dry-run

# Documentation hygiene warnings for a pull request range. Never fails --
# see docs/contributing.md for why, and for what has to be true before
# these become hard failures. The script is the reference service's
# rendered copy: the template owns it (spec §9.1), and this is the one
# place PyFr's own pages are checked with it.
docs-freshness base="origin/main" head="HEAD":
    uv run --group docs python examples/reference-service/scripts/check_docs_freshness.py --exclude docs/superpowers/ {{base}} {{head}}
    # The same script over the example's own pages, run inside the example:
    # a change to the template body regenerates them, so their `covers:`
    # coupling is checked in this repository too, not only in a project.
    cd examples/reference-service && uv run --group docs python scripts/check_docs_freshness.py {{base}} {{head}}

# Everything CI checks at the repository level.
check: docs-build typecheck test regen-check
