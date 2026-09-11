# Repository-level commands. These operate on the documentation site.
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

# Build the site into site/ with --strict, exactly as CI does.
docs-build:
    # --strict turns a warning into a failure: a link to a page that no
    # longer exists, a renamed heading anchor, or an unresolvable include
    # each fail the build rather than printing a warning nobody reads.
    uv run mkdocs build --strict

# Dead external links. Internal ones are already `mkdocs build --strict`'s job.
links:
    # Needs the lychee binary: `brew install lychee`, or run it in CI,
    # where the action provides it.
    lychee --config lychee.toml --no-progress 'docs/**/*.md' README.md

# The repository's own script tests.
test:
    uv run --group dev pytest tests/

# Audit the documentation and release toolchain's lock the same way the
# reference service audits its own -- see that justfile's `audit` for the
# flags. Two locks, two audits, one CI job.
audit:
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
# these become hard failures.
docs-freshness base="origin/main" head="HEAD":
    uv run --group docs python scripts/check_docs_freshness.py {{base}} {{head}}

# Everything CI checks at the repository level.
check: docs-build test
