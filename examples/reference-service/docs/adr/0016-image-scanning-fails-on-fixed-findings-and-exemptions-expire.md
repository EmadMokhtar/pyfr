---
last_reviewed: 2026-09-11
---

# 0016. Scans fail on fixed HIGH and CRITICAL findings, and every exemption expires

**Status:** Accepted
**Date:** 2026-09-11

## Context

Spec 12 says Trivy fails on high-severity findings. Two facts complicate
that. A finding with no available fix is nothing a pull request can act
on — there is no patch or version bump that resolves it, so failing the
build on it blocks merges with no way to unblock them but waiting. And
the newest `migrate/migrate` release, v4.20.1, published 2026-09-09,
carries five HIGH findings in code paths `migrate up` never executes,
with no fix in any release. A gate that is red forever is a gate people
stop reading.

## Decision

`just scan` runs Trivy with
`--severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 --scanners vuln,secret`
over both images. A finding is exempted only through `.trivyignore.yaml`,
where every entry names the vulnerability, the path it applies to, a
reason, and an `expired_at` date about ninety days out; an expired entry
fails the scan again. There is no other allow-list and no skip flag in
any recipe or workflow.

## Alternatives considered

- **Fail on everything, including unfixed findings.** Rejected:
  permanently red on any Debian base, since some unfixed finding is
  essentially always present in a base image's package set.
- **Scan only our own layers.** Rejected: would have hidden
  `migrate/migrate` v4.19.0's CRITICAL finding in `pgx`, a dependency of
  the base image rather than of this repository's own code.
- **Exemptions with no expiry.** Rejected: the list only ever grows,
  since nothing prompts a re-check of whether a fix has since shipped.

## Consequences

Someone must renew or drop the five entries in `.trivyignore.yaml` by
2026-12-10; a Dependabot bump of the `migrate/migrate` base image is the
natural moment. `--ignore-unfixed` drops findings with no available fix
from the report entirely; `docker compose run --rm trivy image
--ignorefile /.trivyignore.yaml --show-suppressed <image>` lists them
(status `affected`).

Full reasoning: [the M6 plan's Design section](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/plans/2026-09-11-pyfr-m6-supply-chain.md).
