---
last_reviewed: 2026-09-11
---

# 0015. Publish images on release, under the repository's version

**Status:** Accepted
**Date:** 2026-09-11

## Context

M5 decided that the repository has one version, one changelog, and one
tag series, and that the reference service publishes nothing. M6 adds a
registry. The images could be tagged with the service's own `0.1.0`,
pushed on every merge, or pushed on release under the repository's tag.

## Decision

`release.yml` pushes `ghcr.io/emadmokhtar/pyfr-reference-service` and
`ghcr.io/emadmokhtar/pyfr-reference-service-migrations`, for
`linux/amd64` and `linux/arm64`, tagged with the release's `vX.Y.Z` after
`scan` has passed on the same commit's local images. `latest` is created
afterwards from that pushed index, and only once `scan-published` has
passed on the pushed digests for both platforms — the artifact people
pull is what gets verified, and `latest` never names an unscanned image.
Nothing is pushed from pull requests or from merges that
do not release — the `publish-images` job runs only `needs: release`
with `if: needs.release.outputs.released == 'true'`. The
`org.opencontainers.image.source` label — a static `LABEL` in each
Dockerfile — links each package to this repository.

## Alternatives considered

- **Never publish.** Rejected: nothing for the SBOM to describe, nothing
  for the nightly scan to re-check, and M7 would have no release path to
  templatise.
- **Publish on every merge.** Rejected: registry churn for images nothing
  consumes continuously — nobody deploys the reference service.
- **Tag with the service's own version.** Rejected: a second version
  series, which M5 already rejected for the same reason.

## Consequences

The first push creates private packages; a one-time repository setting
makes them public. The registry namespace, `ghcr.io/emadmokhtar`, is a
literal until M7 turns it into a template variable. `latest` moves with
every release, which is what the nightly scan wants — it checks whatever
is deployed now — and what a real deployment should never pin to, since
it gives no guarantee about which release it points at from one day to
the next.

Full reasoning: [the M6 plan's Design section](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/plans/2026-09-11-pyfr-m6-supply-chain.md).
