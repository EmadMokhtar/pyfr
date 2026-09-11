---
last_reviewed: 2026-09-10
---

# 0003. Use uv, not pip or Poetry

**Status:** Accepted
**Date:** 2026-08-28

## Context

Both the template and every service it generates need one answer to
dependency resolution, locking, virtual environments and running project
commands, decided once before anything else in the toolchain — the
`justfile`, the pre-commit hooks, the CI workflows — is written against
it.

## Decision

We use uv for everything Python: resolving and locking dependencies,
creating and managing virtual environments, running commands and pinned
tools, and pinning the Python interpreter itself. `uv.lock` is committed
at the root of the template and inside `examples/reference-service`.
There is no `requirements.txt` anywhere in the repository, and pip is
never invoked directly.

## Alternatives considered

- **pip with `pip-tools`.** Rejected: it is separate tools for resolving,
  locking and running, stitched together by hand, and it has no
  dependency-group concept. Splitting the service's runtime dependencies
  from the documentation toolchain's would be a manual convention rather
  than something the tool itself understands.
- **Poetry.** Rejected on two counts: slower dependency resolution, and
  its own non-standard sections in `pyproject.toml`. uv instead writes
  PEP 621 metadata — the standard `[project]` table other tools already
  know how to read — so nothing generated here locks a reader into a
  Poetry-specific reading of the manifest.

## Consequences

One tool covers locking, syncing, running and tool execution, and its
resolution is fast enough that `uv sync` is affordable in every CI job
rather than something to cache around. A contributor learns one command
surface instead of three.

The cost is a young tool sitting at the centre of the build: uv is newer
than pip or Poetry, with a shorter track record and a faster release
cadence, and every `just` recipe and CI job depends on it working
correctly. The one place a pip-named tool still appears is `pip-audit`
(spec D2), which runs through `uvx pip-audit` rather than a project
dependency — it audits the uv-resolved environment without reintroducing
pip as a package manager.

Full reasoning: [spec section 2](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
