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

# Everything CI checks at the repository level.
check: docs-build
