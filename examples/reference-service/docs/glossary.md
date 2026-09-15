---
last_reviewed: 2026-09-14
---

# Glossary

Terms used across this site, each in one line. Terms about the template
this project was generated from — the template body, the golden diff,
pruning, `just regen` — are in
[PyFr's glossary](https://emadmokhtar.github.io/pyfr/glossary/).

| Term | Meaning |
| --- | --- |
| ADR | Architecture Decision Record — a one-page note recording a decision, its context, and its consequences. |
| Adapter | A technology-specific implementation of a port, such as the in-memory order repository. |
| ASGI | Asynchronous Server Gateway Interface — the contract between a Python web server and an application; it lets tests call the app directly, with no network. |
| Cardinality | How many distinct values a field can take. A raw URL path has unbounded cardinality; a route template does not. |
| Circuit breaker | A guard around an outbound call. After repeated failures it stops calling the upstream for a while and fails fast, so a slow dependency cannot hold every request open. |
| Composition root | The single place where an application constructs and connects its dependencies. |
| Conventional Commits | A commit message format (`feat:`, `fix:`, `feat!:`) that machines can read to decide version bumps. |
| cookiecutter | The tool PyFr uses to turn its template plus a set of answers into this project. |
| Correlation identifier | One value bound to every log line a single request produces. |
| CVE | Common Vulnerabilities and Exposures — the public naming scheme for known vulnerabilities; `CVE-2026-56854` is one entry. |
| CycloneDX | The SBOM format Trivy writes — one JSON document listing every component in an image, with versions. |
| Dependabot | GitHub's own dependency-update service. Opens a pull request when a pinned version has a newer release. |
| Diátaxis | A documentation framework separating tutorials, how-to guides, reference, and explanation. |
| Drift gate | A build check that fails when a generated artifact no longer matches the code that produces it. |
| Entity | An object with an identity that persists through change, such as an `Order`. |
| Error budget | The amount of failure a service level objective permits — for example 0.1% of requests over 30 days. |
| Fail-open | The cache's rule: when Redis is unreachable, a read falls through to the repository and the request succeeds without the cache. The cache can never be the reason a request fails. |
| Frozen | Immutable after construction. Assigning to a field raises instead of changing the value. |
| GHCR | GitHub Container Registry — `ghcr.io`, where the release workflow pushes both images. |
| gitleaks | A scanner that blocks commits containing secrets. |
| golang-migrate | The migration tool that owns the schema: plain `.up.sql` and `.down.sql` files under `migrations/`, applied by the migrations image before the service starts. |
| Hypothesis | The property-based testing library used for domain invariants. |
| import-linter | The tool that enforces the dependency rule by reading the import graph. |
| just | A command runner. A `justfile` holds named recipes; `just <name>` runs one. |
| Liveness | "Is this process alive?" — the question `/healthz` answers, without checking dependencies. |
| Log agent | A platform process that reads containers' standard output and forwards it to a log store. |
| Migration | A versioned change to the database schema, as a pair of SQL files. `just migrate` applies the outstanding ones; `just migrate-new` writes a new pair. |
| MinIO | An S3-compatible object store that runs locally in compose, standing in for S3. |
| Multi-architecture image | One image tag that holds a build per CPU architecture (`amd64`, `arm64`), so every machine pulls the same tag and gets its own. |
| Mutation testing | Introducing small deliberate bugs to check whether the tests actually catch them. |
| mypy | The static type checker. Strict on `domain/` and `services/`, lenient elsewhere. |
| OCI image index | The manifest list behind a multi-architecture tag: one entry per platform, each pointing at that platform's image. OCI is the Open Container Initiative, which standardises image formats. |
| OpenTelemetry | The vendor-neutral standard for traces, metrics, and logs. |
| OTLP | OpenTelemetry Protocol — the wire format those signals are sent in. |
| Payment stub | A WireMock container in the compose stack that plays the payment upstream, answering from committed mappings. |
| pip-audit | A tool that checks pinned Python packages against the PyPI advisory database. Runs here over a `uv export`, without pip. |
| Port | An interface owned by the domain, describing what it needs without saying how. |
| Problem Details | RFC 9457 — the internet standard shape for a JSON error body. |
| Property-based testing | Generating many random inputs to check that a rule holds, rather than testing fixed examples. |
| Protocol | Python's structural interface — satisfied by having the right methods, with no inheritance. |
| Pydantic | The validation library. Used in the domain layer as a validation tool, not as a web framework. |
| `pyfr-cli` | The tool behind `just update` and `just update-check`, run from PyPI through `uvx`; nothing of it is installed in this project. |
| `.pyfr-update-ignore` | The paths `just update` never touches, in `.gitignore` syntax. Yours to grow as the project diverges from the template. |
| QEMU | A processor emulator. In CI it lets an `amd64` runner build the `arm64` side of a multi-architecture image. |
| Readiness | "Can this instance serve traffic right now?" — the question `/readyz` answers. |
| Readiness tier | Which of `/readyz`'s two maps a dependency is reported in. `checks` is gating: a failure returns 503 and takes the instance out of load balancing. `dependencies` is informational: reported, never changes the status. |
| Receipt store | The port for keeping one rendered receipt per order. Its adapter writes to S3-compatible object storage over aioboto3. |
| RED metrics | Rate, Errors, Duration — the three signals a request-serving service needs. |
| Redaction | Replacing a value with `[REDACTED]` before a log record is rendered. Done by field name, in the shared processor chain. |
| Repository | An interface for loading and saving entities, expressed in domain terms. |
| ruff | The linter and formatter. |
| S3-compatible | Any object store that speaks Amazon S3's API. The receipt store talks to one; locally that is MinIO. |
| SBOM | Software Bill of Materials — a machine-readable inventory of everything inside a built artifact. |
| Schema snapshot | `schema.sql`: the committed dump of the schema the migrations produce. `just schema-snapshot` regenerates it, and a gate fails when it drifts. |
| Semantic conventions | Agreed standard names for telemetry fields, so dashboards work across services and languages. |
| SemVer | Semantic Versioning — `MAJOR.MINOR.PATCH`, where a major bump means a breaking change. |
| SLI | Service Level Indicator — a measured number describing user-visible quality. |
| SLO | Service Level Objective — the target for an SLI over a window. |
| structlog | The structured logging library. A record is key/value data rendered at the end, not a pre-formatted string. |
| `template` branch | A branch holding pristine template output and nothing else, kept on `origin`; every update merges from it. Never delete it. |
| Testcontainers | A library that starts real dependencies in Docker for the duration of a test run. |
| Trivy | A scanner that finds known vulnerabilities in container images. |
| uv | A fast Python package and project manager. The only Python tool this project requires. |
| Value object | An object defined only by its values, with no identity, such as `Money`. |
| VCR / cassette | Recording real HTTP responses to a file and replaying them in later test runs. |
| Walking skeleton | A thin but complete end-to-end implementation, proving the architecture before features are added. |
