# Glossary

Terms used across this site, each in one line.

| Term | Meaning |
| --- | --- |
| ADR | Architecture Decision Record — a one-page note recording a decision, its context, and its consequences. |
| Adapter | A technology-specific implementation of a port, such as a PostgreSQL repository. |
| ASGI | Asynchronous Server Gateway Interface — the contract between a Python web server and an application; it lets tests call the app directly, with no network. |
| Cardinality | How many distinct values a field can take. A raw URL path has unbounded cardinality; a route template does not. |
| Composition root | The single place where an application constructs and connects its dependencies. |
| Conventional Commits | A commit message format (`feat:`, `fix:`, `feat!:`) that machines can read to decide version bumps. |
| cookiecutter | The tool that turns a project template plus your answers into a new repository. |
| Copier | An alternative template tool with updates built in; considered and rejected. |
| cruft | A tool adding update support to cookiecutter templates; considered and rejected. |
| Correlation identifier | One value bound to every log line a single request produces. |
| Diátaxis | A documentation framework separating tutorials, how-to guides, reference, and explanation. |
| Drift gate | A build check that fails when a generated artifact no longer matches the code that produces it. |
| Entity | An object with an identity that persists through change, such as an `Order`. |
| Error budget | The amount of failure a service level objective permits — for example 0.1% of requests over 30 days. |
| Frozen | Immutable after construction. Assigning to a field raises instead of changing the value. |
| gitleaks | A scanner that blocks commits containing secrets. |
| Hypothesis | The property-based testing library used for domain invariants. |
| import-linter | The tool that enforces the dependency rule by reading the import graph. |
| Jinja | The placeholder language cookiecutter uses; `{{ }}` marks a substitution. |
| just | A command runner. A `justfile` holds named recipes; `just <name>` runs one. |
| Liveness | "Is this process alive?" — the question `/healthz` answers, without checking dependencies. |
| Log agent | A platform process that reads containers' standard output and forwards it to a log store. |
| Merge base | The most recent commit two branches share — the "before" state a three-way merge compares both sides against. |
| Mutation testing | Introducing small deliberate bugs to check whether the tests actually catch them. |
| mypy | The static type checker. Strict on `domain/` and `services/`, lenient elsewhere. |
| OpenTelemetry | The vendor-neutral standard for traces, metrics, and logs. |
| OTLP | OpenTelemetry Protocol — the wire format those signals are sent in. |
| Port | An interface owned by the domain, describing what it needs without saying how. |
| Problem Details | RFC 9457 — the internet standard shape for a JSON error body. |
| Property-based testing | Generating many random inputs to check that a rule holds, rather than testing fixed examples. |
| Protocol | Python's structural interface — satisfied by having the right methods, with no inheritance. |
| Pydantic | The validation library. Used in the domain layer as a validation tool, not as a web framework. |
| Readiness | "Can this instance serve traffic right now?" — the question `/readyz` answers. |
| RED metrics | Rate, Errors, Duration — the three signals a request-serving service needs. |
| Repository | An interface for loading and saving entities, expressed in domain terms. |
| ruff | The linter and formatter. |
| SBOM | Software Bill of Materials — a machine-readable inventory of everything inside a built artifact. |
| Semantic conventions | Agreed standard names for telemetry fields, so dashboards work across services and languages. |
| SemVer | Semantic Versioning — `MAJOR.MINOR.PATCH`, where a major bump means a breaking change. |
| SLI | Service Level Indicator — a measured number describing user-visible quality. |
| SLO | Service Level Objective — the target for an SLI over a window. |
| structlog | The structured logging library. A record is key/value data rendered at the end, not a pre-formatted string. |
| Testcontainers | A library that starts real dependencies in Docker for the duration of a test run. |
| Three-way merge | A merge using the merge base plus both sides, so a tool can tell "they changed it" apart from "you changed it". |
| Trivy | A scanner that finds known vulnerabilities in container images. |
| uv | A fast Python package and project manager. The only Python tool PyFr requires. |
| Value object | An object defined only by its values, with no identity, such as `Money`. |
| VCR / cassette | Recording real HTTP responses to a file and replaying them in later test runs. |
| Vendor branch | A branch holding pristine upstream output and nothing else, merged in to receive upstream changes. |
| Walking skeleton | A thin but complete end-to-end implementation, proving the architecture before features are added. |
