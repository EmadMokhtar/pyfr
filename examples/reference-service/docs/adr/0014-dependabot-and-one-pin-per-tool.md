---
last_reviewed: 2026-09-13
---

# 0014. Dependabot, and one pin per tool

**Status:** Accepted
**Date:** 2026-09-11

## Context

Spec 12 names Renovate. This repository already had tool revisions pinned
in `.pre-commit-config.yaml`, drifting behind `uv.lock`, and M5 pinned
Commitizen's version in two files with a comment asking that the copies
be kept equal by hand. Renovate's regex manager can rewrite a version
literal anywhere in a file; Dependabot cannot, but it is GitHub-native,
needs no installation, and supports every ecosystem this repository has:
`uv`, `github-actions`, `docker`, `docker-compose`, and `pre-commit`.

## Decision

We use Dependabot, and we remove every duplicated pin rather than
policing it. Tool versions live in `uv.lock` alone: the ruff, uv-lock,
and Commitizen pre-commit hooks are `repo: local` hooks that run the
locked tools, instead of hooks carrying their own separately pinned
`rev:`. Commitizen is a dev dependency, called as `uv run --locked cz`
from the `justfile`, `.github/workflows/release.yml` and the
commit-message hook — one dependency declaration, read by every caller.
Container image pins live in `compose.yaml` and the two
Dockerfiles only: the integration tests read image versions from there,
and so does `just o11y-gates`.

## Alternatives considered

- **Renovate, hosted or self-hosted.** Rejected: more capable — its regex
  manager reaches version literals Dependabot cannot — but it is one more
  thing to install, and self-hosted it is a credential to keep alive.
- **A "pins agree" gate over the duplicates.** Rejected: every Dependabot
  pull request that bumped one copy would leave the gate red until a
  human bumped the other by hand — the drift problem M5's comment already
  failed to prevent, with extra steps added on top of it rather than
  removed.

## Consequences

Two version literals remain outside Dependabot's reach, accepted
knowingly: `pip-audit==2.10.1`, pinned in the justfile — its advisory
data is fetched live, so a stale pinned binary still reports new
findings — and the `oasdiff` image pinned in
`scripts/check_contract_compatibility.py` as `tufin/oasdiff:v1.31.0`, a
pin that predates M6. ruff is pinned in `uv.lock` alone, and
Dependabot's `uv` entry keeps it current. That entry ignores
`pydantic-core`: each pydantic release pins one exact pydantic-core, and
pydantic-core publishes stable-numbered releases for pydantic betas too,
so a lone pydantic-core bump resolves to a beta pydantic. The pydantic
bump carries pydantic-core. Behind that, `pyproject.toml` sets
`tool.uv.prerelease = "explicit"`: uv resolves to a pre-release only
where a first-party requirement names one, so Dependabot's `uv lock`
fails outright rather than opening a pull request that installs a beta.
The permanently beta-versioned OpenTelemetry instrumentation packages
are named -- the direct ones by their own `0.65b0` floors, the transitive
ones by `constraint-dependencies` beside the setting.

Full reasoning: [the M6 plan's Design section](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/plans/2026-09-11-pyfr-m6-supply-chain.md).
