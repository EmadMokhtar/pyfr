---
last_reviewed: 2026-09-11
covers:
  - examples/reference-service/Dockerfile
  - examples/reference-service/Dockerfile.migrations
  - examples/reference-service/.trivyignore.yaml
  - .github/dependabot.yml
  - .github/workflows/release.yml
  - .github/workflows/nightly.yml
---

# Supply chain

What ships is audited, scanned, inventoried and published — and every
dependency it was built from is updated by a machine, not by memory. This page
says what each check looks at, where it runs, and what to do when one is red.

Every `just` command below runs from `examples/reference-service/`, except
where a sentence says otherwise.

## What is checked, where

| Command | What it does | Where it runs |
| --- | --- | --- |
| `just audit` | [pip-audit](https://github.com/pypa/pip-audit) over every pinned version in `uv.lock`, against the PyPI advisory database. Nothing is resolved or installed: `uv export` writes the lock as a fully hashed requirements file, and pip-audit reads it with `--disable-pip --require-hashes`. The same recipe exists at the repository root for the documentation toolchain's own lock. | Every pull request, in CI's `security` job (both locks); every night, in `nightly.yml`. |
| `just scan` | [Trivy](https://trivy.dev/) over both images, for known vulnerabilities and embedded secrets. Fails on any HIGH or CRITICAL finding that has a fix. | Every pull request, on the freshly built images (`security`); on release, before the push (`release.yml`); every night, on the `latest` tag actually published. |
| `just scan-published VERSION` | The same scan over the two images just pushed under `VERSION`, for **both** platforms — the exact digests people will pull. | Release only, after the push and before `latest` is created. |
| `just sbom` | A [CycloneDX](https://cyclonedx.org/) software bill of materials per image, into `sbom/`. | Every pull request, from the local build, uploaded as the `sbom` workflow artifact; on release, from the published image reference after the push, attached to the GitHub Release. |
| `just build-multiarch` | Both images for `linux/amd64` and `linux/arm64`, with no output — proof that both architectures still build. | Every pull request, in CI's `build` job. |
| `just publish-images` | Both images, both architectures, pushed to GHCR (the GitHub Container Registry) under the version given — and only the version. | Release only, in `release.yml`'s `publish-images` job. |
| `just promote-latest VERSION` | Point `latest` at the version's already-pushed index, without rebuilding. | Release only, after `scan-published` has passed. |
| `just security` | `build-images`, then `audit`, `scan` and `sbom` — the same recipes as CI's `security` job, in the same order. CI adds the repository root's `just audit` as one more step. Needs Docker. | Locally, by hand. |

Two things follow from that table. `just security` is **not** part of
`just check-all`, because its result changes without a commit: an advisory is
published against a version that is already locked, and the same tree that
was green yesterday is red today. That is also why `nightly.yml` runs the audit
and the scan again every night, and scans the images last *published* rather
than freshly built ones — a CVE (a Common Vulnerabilities and Exposures
identifier, the public name for one known vulnerability) is announced against a
version somebody is already running.

Trivy runs from the `trivy` service in `compose.yaml`, under the `tools`
profile, rather than from a `docker run` line in the `justfile`. Its version is
then pinned in the one file Dependabot updates, with every other image pin. The
first run downloads the vulnerability database, which takes about a minute; a
named volume keeps it, so later runs take seconds — until `just down`, which
removes the `trivy-cache` volume with the others.

## The images

`release.yml` pushes two images on every release:

| Image | What it is |
| --- | --- |
| `ghcr.io/emadmokhtar/pyfr-reference-service` | The service — the two-stage build in `Dockerfile`. |
| `ghcr.io/emadmokhtar/pyfr-reference-service-migrations` | The schema and nothing else — `Dockerfile.migrations`, `FROM migrate/migrate:v4.20.1` with `migrations/` copied in. |

Each carries two tags: `vX.Y.Z`, the **repository's** version — the same
string as the git tag and the GitHub Release — and `latest`, which moves with
every release. The two are not written together: the version tag is pushed
first, the pushed digests are scanned for both platforms, and only then is
`latest` created from that same index — so `latest` never names an image
nobody scanned, while a version tag that failed that scan stays in the
registry as evidence, never promoted. Nothing is pushed from a pull request
or from a merge that does not release
([ADR 0015](../adr/0015-images-are-published-on-release-under-the-repository-version.md)).

Each tag is an OCI image index (a manifest list: one tag that points at one
image per platform) covering `linux/amd64` and `linux/arm64`, so an Apple
Silicon laptop and an `amd64` server pull the same tag and each gets its own
architecture.

```bash
docker pull ghcr.io/emadmokhtar/pyfr-reference-service:latest
```

Each image carries three OCI labels. `org.opencontainers.image.source` is a
static `LABEL` in each Dockerfile; it is what makes GHCR link the package to
this repository. `org.opencontainers.image.version` and
`org.opencontainers.image.revision` are added by `just publish-images`, because
the version and the commit are only known at publish time.

The migrations image is not a service. It runs once, before the new
application version takes traffic — as a Kubernetes init container or a
pre-deployment job — with the database URL supplied at run time, never baked
in. [Run in a container](../guides/run-in-a-container.md#pull-the-published-images-instead-of-building)
shows the command.

Two things to know before relying on the registry. The first push creates
private packages; making them public is a one-time setting listed in
[Contributing](../contributing.md#one-time-repository-settings). And `latest`
is for the nightly scan, which wants whatever is current — a real deployment
pins `vX.Y.Z`, because `latest` gives no guarantee about which release it
points at from one day to the next.

## Reading a scan failure

A failed `just scan` prints, per image, a `Total:` line and a table:

```
usr/local/bin/migrate (gobinary)
================================
Total: 1 (HIGH: 1, CRITICAL: 0)

┌─────────────────────┬────────────────┬──────────┬────────┬───────────────────┬───────────────┬───────┐
│       Library       │ Vulnerability  │ Severity │ Status │ Installed Version │ Fixed Version │ Title │
├─────────────────────┼────────────────┼──────────┼────────┼───────────────────┼───────────────┼───────┤
│ golang.org/x/crypto │ CVE-2026-56854 │ HIGH     │ fixed  │ v0.53.0           │ 0.55.0        │ ...   │
└─────────────────────┴────────────────┴──────────┴────────┴───────────────────┴───────────────┴───────┘
```

The heading above the table names the target: the operating-system layer
(`reference-service:ci (debian 13.6)`), a Python package set, or a single
binary such as `usr/local/bin/migrate`. `Status` is always `fixed` in a
failing scan, and that is by construction. The recipe runs with
`--ignore-unfixed`: a finding for which no fixed version exists yet is left out
of the report entirely, because nothing a pull request does can resolve it.
Every row you see therefore has a `Fixed Version`, and that column is the
whole of the answer. The `--show-suppressed` command further down runs with
neither the severity filter nor `--ignore-unfixed`, so its table lists the
unfixed findings too — their `Status` reads `affected` and their
`Fixed Version` is empty.

The recipe also scans for embedded secrets (`--scanners vuln,secret`). A
secret finding prints a different table, naming the file inside the image and
the rule that matched. The only fix is to take the secret out of the image;
nothing below applies to it.

**Fix by bumping.** For a Python package, in `examples/reference-service/`:

```bash
uv lock --upgrade-package <name>
```

then `just security` again, and commit `uv.lock`. Dependabot opens the same
bump weekly on its own; a red scan is the reason not to wait a week. For a
Debian package in the operating-system layer, a rebuild against the current
base image is usually enough — the `python:3.13-slim-trixie` tag moves as
Debian publishes fixes, so `docker pull python:3.13-slim-trixie` and then
`just security` again. For the Go binary inside the migrations image, only a
new `migrate/migrate` release can carry the fix; Dependabot's `docker` entry
proposes it when one exists.

**Exempt, only through `.trivyignore.yaml`.** When the fix is not reachable —
the finding is in code the image never executes, and no release carries the
patch yet — add an entry with all four fields:

```yaml
vulnerabilities:
  - id: CVE-2026-56854
    paths: ["usr/local/bin/migrate"]
    statement: "golang.org/x/crypto/ssh authentication bypass. migrate opens no ssh connection here. Fixed in x/crypto 0.55.0; not in any migrate release yet."
    expired_at: 2026-12-10
```

`paths` pins the entry to the one file it is about, so the same CVE appearing
somewhere else still fails. `statement` says why the finding does not apply,
and where the fix is. `expired_at` is the date the decision is re-taken: after
it, the finding fails the scan again until someone checks whether a fix has
shipped and either drops the entry or renews it. About ninety days out is the
convention. There is no other way to silence a finding — no `--skip` flag, no
allow-list in a recipe or a workflow
([ADR 0016](../adr/0016-image-scanning-fails-on-fixed-findings-and-exemptions-expire.md)).

To see what the file is currently hiding — a `Suppressed Vulnerabilities`
table after the findings, one row per entry with its statement:

```bash
docker compose run --rm trivy image --ignorefile /.trivyignore.yaml --show-suppressed reference-service-migrations:ci
```

The five entries in the file today all belong to the `migrate/migrate` Go
binary. A Dependabot bump of that base image is the moment to re-scan and drop
whichever have gone.

## The SBOM

An SBOM (software bill of materials) is a machine-readable inventory of
everything inside a built artifact. `just sbom` writes one per image, in
CycloneDX format:

| Where | What |
| --- | --- |
| `sbom/reference-service.cdx.json` and `sbom/reference-service-migrations.cdx.json` | Locally, after `just sbom` or `just security`. The directory is ignored by git. |
| The `sbom` workflow artifact | On every pull request, from the `security` job, generated from the local build. |
| The release assets | On every release, attached to the GitHub Release by `release.yml`, generated from the published image reference after the push. |

It is generated from an image, not from `uv.lock`, so it lists the Debian
packages as well as the Python ones — about 160 components for the service
image, `libc6` and `openssl` beside `fastapi` and `pydantic`.

Which image depends on where it runs. On a pull request it is the
single-architecture `:ci` image that `just build-images` produces. On a
release it is generated **after** the push, from the published reference —
`ghcr.io/emadmokhtar/pyfr-reference-service:vX.Y.Z` and its migrations
counterpart — so the document's subject is the image people pull, not a
local build that was never published (`just publish-images` rebuilds through
the buildx builder, so the local `:ci` image is a different image ID from
what reaches the registry). For the SBOM Trivy reads the manifest for the
runner's own platform, `amd64`, out of the index; the vulnerability scan that
precedes it (`just scan-published`) reads both. The `arm64` image is built
from the same commit, the same `uv.lock`, the same Dockerfile and the same
Debian package versions; it differs only in architecture, so its list of components is the
same list. One document per image is therefore enough.

To list what is in one:

```bash
jq -r '.components[].name' sbom/reference-service.cdx.json
```

or, with nothing but Python:

```bash
python3 -c "import json; print('\n'.join(c['name'] for c in json.load(open('sbom/reference-service.cdx.json'))['components']))"
```

## Dependency updates

[Dependabot](https://docs.github.com/en/code-security/dependabot) is GitHub's
own dependency-update service. `.github/dependabot.yml` configures it for the
five ecosystems this repository has:

| Ecosystem | What it updates |
| --- | --- |
| `uv` | Both lockfiles — the repository root's and the reference service's. |
| `github-actions` | The `uses:` versions in every workflow. |
| `docker` | The `FROM` lines in `Dockerfile` and `Dockerfile.migrations`. |
| `docker-compose` | Every `image:` in `compose.yaml` — PostgreSQL, Redis, MinIO, `mc`, WireMock, `otel-lgtm` and Trivy. |
| `pre-commit` | The `rev:` of the hook repositories that still have one: gitleaks, sqlfluff and pre-commit-hooks. |

Updates arrive weekly, as one grouped pull request per ecosystem, with a
Conventional Commits prefix (`build(deps)`, or `ci(deps)` for actions). Each
carries the `no-docs-needed` label, because a version bump is exactly the
internal-only change CI's documentation gate has that label for.

Dependabot has no way to update a version literal inside a `justfile`, a
workflow step or a test. So the rule is **one pin per tool, in the file
Dependabot updates**, and the duplicates were removed rather than policed. Tool
versions live in `uv.lock` alone: the ruff, uv-lock and Commitizen pre-commit
hooks are local hooks that run the locked tools, and Commitizen is a root dev
dependency that the root `justfile`, `release.yml` and the commit-message hook
all call through `uv run --locked --group dev cz`. Container image pins live in
`compose.yaml` and the two Dockerfiles alone: the integration tests and
`just o11y-gates` read their image names from there.

Two literals remain outside Dependabot's reach, knowingly: `pip-audit==2.10.1`
in both justfiles — its advisory data is fetched live, so a stale binary still
reports new findings — and the `tufin/oasdiff:v1.31.0` image in
`scripts/check_contract_compatibility.py`, a pin that predates this milestone.
See [ADR 0014](../adr/0014-dependabot-and-one-pin-per-tool.md).

## The hardened image

The runtime stage of `Dockerfile` is what ships, and it is deliberately
small in what it can do:

- **Non-root.** A system user `app`, created in the image, owns and runs
  everything under `/app`.
- **No build tools.** The first stage resolves and installs dependencies with
  uv; the second copies the finished virtual environment into a clean
  `python:3.13-slim-trixie` base and adds nothing else — no uv, no compiler,
  no shell utilities beyond the base image.
- **`uv sync --locked`.** Installs exactly the versions in `uv.lock`, and fails
  the build if the lock is out of date with `pyproject.toml`, rather than
  quietly resolving something new.
- **pip removed.** The runtime stage runs `python -m pip uninstall -y pip`
  against the base image's own interpreter. pip is not used at runtime — the
  virtual environment was built by uv — and the copy the base image ships was
  the only source of HIGH findings in the service image: its vendored
  `msgpack` and `pkg_resources`, both fixed upstream, both unreachable from
  anything this service runs. Removing pip removed the findings, and a tool
  nobody should run inside a production container.
- **Distribution security updates applied at build time.** The runtime stage
  runs `apt-get upgrade` before anything else, and the migrations image runs
  `apk upgrade`. The official `python:slim` and `migrate/migrate` tags are
  rebuilt on their own projects' schedules, not the distribution's, so a base
  tag can carry packages whose fixes have been in Debian or Alpine for weeks
  — the scan gate's first run on a pull request found twelve fixed findings
  in a base that had scanned clean the day before, once the vulnerability
  database caught up with a Debian point release. Upgrading at build time
  makes the image as current as the archive on the day it is built. The cost
  is that two builds days apart can differ in package versions; the SBOM
  records which versions a given image carries.

What it is **not** is distroless (a base image with no shell and no package
manager at all). That was considered and decided against: there is no
maintained, freely tag-pinnable Python 3.13 distroless image, and the start
command needs `sh` to expand `APP_HTTP_PORT` at run time. Scanning the slim
image on every pull request and every night is the standing mitigation — see
the [roadmap's exclusions](../roadmap.md#what-is-deliberately-excluded).
