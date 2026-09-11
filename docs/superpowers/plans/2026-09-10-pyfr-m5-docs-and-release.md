# PyFr M5 — Docs and Release Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Put the reference service under continuous integration for the first time, make the configuration reference a generated artifact of the settings model, record the decisions M0–M4 made, and give the repository automated versioned releases.

**Architecture:** Three independent strands that share one milestone. The **generated configuration reference** makes `settings.py` the single source of truth for 38 environment variables that are currently described by hand in three places, and adds a drift gate in the same shape as the existing `openapi.json` one. The **documentation hygiene** strand completes the four mechanisms spec 10.3 names, with the two subjective ones (review age, path coupling) emitting warnings rather than failures. The **release** strand adds Commitizen at the repository level, a `CHANGELOG.md` generated from the existing Conventional Commit history, and the three workflows — `ci.yml` grown from two jobs to eleven, plus `release.yml` and `nightly.yml`.

**Tech Stack:** Commitizen 4.18.0, `lychee` via `lycheeverse/lychee-action@v2`, PyYAML (already present transitively through MkDocs), GitHub Actions with `services:`-free Docker (testcontainers manages its own), and the existing `just` recipes as the only definition of what a gate is.

**Spec:** [`docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md`](../specs/2026-08-28-pyfr-cookiecutter-template-design.md) — sections 10.1 (two version numbers), 10.2 (the contract/version gate), 10.3 (documentation and hygiene), 10.4 (CI), 10.5 (pre-commit), 12.1, and the M5 row of section 13.

---

## Global Constraints

Every task's requirements implicitly include these. The first group is inherited from M0–M4 unchanged; the rest are new in M5.

- **Python `>=3.13`.** `.python-version` contains `3.13`.
- **uv for everything Python.** `uv sync`, `uv run`, `uv lock`. No `pip`, no `requirements.txt`, no `pipx`, no manually activated virtual environment. The one exception spec 10.4 allows is `pip-audit` through `uvx`, and that arrives in M6, not here.
- **Plain Python only.** M5 is still Phase A. No Jinja, no cookiecutter variables, no `{{ }}` templating in any Python, YAML or compose file. Templatisation is M7.
- **Package name is `reference_service`;** distribution name is `reference-service`. Service work happens under `examples/reference-service/`; documentation and release work happens at the repository root.
- **The two projects are never synced together.** The root `pyproject.toml` is the documentation and release toolchain. `examples/reference-service/pyproject.toml` is the service. A CI job runs in exactly one of them, named by `working-directory`.
- **The domain layer imports nothing but `pydantic`.**
- **mypy is strict on `domain/` and `services/`,** lenient elsewhere.
- **Line length 88.**
- **Conventional Commits** for every commit: `<type>[scope]: <description>`, imperative, lowercase, no trailing period. This constraint stops being only a convention in M5 — Commitizen now reads these commits to decide version numbers.
- **Unit tests never need Docker.** `just test` runs `tests/unit` and `tests/api` only.
- **`filterwarnings = ["error"]` stays.**
- **The committed contract is generated, never hand-edited.**
- **A secret never reaches a log line, a traceback, or an HTTP response body.** New in M5: nor a generated document. The configuration generator prints a field's *default*, and no field carrying a secret has one — but Task 2 asserts this rather than trusting it.
- **Every gate is defined in `just`, and CI calls the recipe.** This is the M5 form of the constraint every previous milestone carried as "no workflow files yet". A CI job that inlines a command instead of calling `just` creates a gate that passes locally and fails in CI, or worse the reverse. The workflow files added here are thin: checkout, install, `just <recipe>`.
- **A generated file is never hand-edited.** `.env.example` and the table region of `docs/reference/configuration.md` become artifacts of `settings.py`. The drift gate in Task 3 makes editing one a build failure.
- **Review dates and path coupling warn; they never fail.** Spec 10.3 is explicit about this, and the reason is operational: a large refactor trips path coupling across many pages at once, which lands exactly when a team is busiest. The switch to hard failure is documented in `contributing.md` (Task 17) and deliberately not taken here.
- **Architecture Decision Records are exempt from the review-date check.** An accepted ADR is a historical record of a decision taken on a date. It does not go stale, and asking someone to re-review it twice a year trains them to ignore the warning. Superseding a decision means writing a new ADR and marking the old one superseded — not editing it.
- **The release workflow versions the repository, not the reference service.** One `CHANGELOG.md`, one tag series (`v0.5.0`, …), sourced from the root `pyproject.toml`. The reference service stays at `0.1.0` and publishes nothing. See "What M5 deliberately does not include".

---

## What M5 deliberately does not include

| Left out | Owner |
|---|---|
| `catalog-info.yaml` (Backstage) | **Decided against here, not deferred.** Spec 13's M5 row justifies it as making "the README's existing integration claim true" — but the README rewrite in #14 and #15 removed that claim, so there is nothing left for it to make true. It is a registration file for a portal this repository does not have, describing a service nobody deploys. If Backstage ever matters it is template content, and M7 owns it |
| A weekly job re-recording VCR cassettes against a real upstream | **Decided against, superseding the M3 plan's deferral to M5.** `just test-record` records against the local WireMock stub in `ops/payment-stub/`, which is committed and deterministic. A scheduled re-record would produce an empty diff every week forever. The M3 plan already reached this conclusion in its own deferral row — "There is no real payment provider here to record". Written down as decided rather than carried forward as perpetually deferred |
| A separate `handle-a-dirty-migration` how-to guide (spec 6.4) | **Decided against.** The procedure lives in the runbook (Task 9), which is where someone under pressure looks. Two homes for one procedure guarantees one of them rots, and the runbook is the copy that gets read at 3am |
| Container image publishing from `release.yml` | M6. Spec 10.4's release workflow pushes images, but that is the *generated service's* release path; this repository releases itself, and the reference service is an example. `ci.yml` builds the image to prove the Dockerfile still works (Task 15) without pushing it |
| Multi-architecture builds, `trivy`, `pip-audit`, SBOM | M6, the supply-chain milestone. `ci.yml`'s job list here is spec 10.4's minus the `security` row |
| Automated dependency updates | M6 |
| The `tutorial/` directory from spec 10.3's tree | Never, as a separate directory. `getting-started.md` is the tutorial, and the site already deviates from the spec's tree by using `guides/` for `how-to/`. Churning the URL structure to match a diagram would break every external link for no reader's benefit |
| `record-cassettes` and `add-a-dashboard-panel` how-to guides (spec 10.3's tree) | Unscheduled. Neither is referenced by anything M5 writes. Add one when a reader needs it, not because a tree diagram lists it |
| Flipping path coupling and review dates to hard failures | Deliberately not taken — see Global Constraints. `contributing.md` documents the switch and what has to be true first |
| Publishing `docs/superpowers/` to the site | Never. `mkdocs.yml`'s `exclude_docs` already handles this, and `roadmap.md` explains why |
| A `pre-commit` hook running the configuration generator | Spec 10.5 caps pre-commit at roughly two seconds and excludes generation steps by name. The drift gate lives in `just gates` and CI, like the OpenAPI one |

---

## Verified Facts

Each was established by reading or running the installed code, not assumed. They exist so the implementer does not rediscover them.

**1. Installed versions: pydantic 2.13.4, pydantic-settings 2.15.0, PyYAML 6.0.3, Commitizen 4.18.0.**

PyYAML arrives transitively through MkDocs, so the documentation job already has it after `uv sync --group docs` — Task 4's frontmatter reader needs no new dependency. Commitizen 4.18.0 is already pinned in `.pre-commit-config.yaml`; Task 10 pins the same version in the release workflow so the two cannot drift.

**2. `FieldInfo.default` is `PydanticUndefined` for every field that uses `default_factory`, even though the field is not required.**

Verified on the real model:

```
log:      default=PydanticUndefined  factory=<class 'LogSettings'>       required=False
otel:     default=PydanticUndefined  factory=<class 'OtelSettings'>      required=False
database: default=None               factory=None                        required=False
```

`Settings.log`, `Settings.otel`, `PaymentSettings.http` and `LogSettings.levels` all take this path. A generator that reads `.default` alone renders `PydanticUndefined` into the documentation for `APP_LOG__LEVELS`, or worse decides the field is required. Read `default_factory` first and call it; only then fall back to `.default`.

**3. `annotation is SecretStr` is False for `SecretStr | None`.**

`PaymentSettings.api_key` is `SecretStr | None`, and the identity check that works for `StorageSettings.access_key_id` (a bare `SecretStr`) fails for it. Secret detection must unwrap the union first. Getting this wrong publishes `APP_PAYMENT__API_KEY` as an ordinary string field in the reference table — the exact opposite of what the `SecretStr` annotation exists to achieve.

**4. Optional sub-models are unions, and recursion must unwrap them.**

`Settings.database` has annotation `DatabaseSettings | None`, and `typing.get_args` returns `(DatabaseSettings, NoneType)`. `database`, `payment`, `cache` and `storage` are all shaped this way; `log` and `otel` are bare model classes. The walker must handle both.

**5. Constraints live in `FieldInfo.metadata` as `annotated_types` objects.**

`pool_size` carries `[Ge(ge=1)]`, the timeouts carry `[Gt(gt=0)]`, and `StorageSettings.bucket` carries a `StringConstraints(...)` with `pattern='^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$'`. These are what render "integer, ≥ 1" and "float, > 0" in the existing hand-written table, so the generator can reproduce that column exactly.

**6. The model has 38 environment variables across 8 models.**

Three on `Settings` itself, then `LogSettings` 2, `OtelSettings` 5, `DatabaseSettings` 3, `PaymentSettings` 7 plus `HttpClientSettings` 6 nested beneath it at `APP_PAYMENT__HTTP__*`, `CacheSettings` 5, `StorageSettings` 7. The double nesting is real and only occurs there.

**7. `cz changelog` generates a usable initial changelog from this repository's existing history.**

Run with a temporary `.cz.toml` at the repository root, `cz changelog --dry-run --unreleased-version v0.5.0` produced a correctly grouped Feat/Fix changelog covering every commit back to the first. Nobody needs to hand-write it.

**One artifact to expect:** the line `add the m0 walking skeleton reference service` appears **twice**, because two commits carry that message. This is a true record of the history, not a bug in the generation. Leave it. Editing generated output to look tidier is how a changelog stops being trustworthy.

**8. `mkdocs build --strict` accepts `last_reviewed` and `covers` frontmatter with no warning.**

Verified by adding both keys to `docs/glossary.md` and building: `Documentation built in 0.39 seconds`, no warnings, exit 0. MkDocs stores unrecognised frontmatter keys in `page.meta` and does not validate them.

**9. No page in `docs/` currently has any frontmatter.** All 20 published pages need it added. The count excludes `docs/superpowers/`, which `mkdocs.yml` excludes from the site.

**10. There are no git tags in this repository, and no `CHANGELOG.md` anywhere.**

`git tag -l` is empty. So the first Commitizen run has no base to compute a bump from, which is why Task 10 bootstraps the version explicitly rather than letting `cz bump` guess.

**11. `just check-all` is already documented as CI's job list.**

The `justfile` comment above it reads "What CI will run at M5", and `examples/reference-service/README.md:57` says the same. It expands to `check` (which is `lint typecheck imports test precommit` plus a `git diff --exit-code`) then `test-integration`, `gates`, `o11y-gates` and `contract-gates`. Tasks 13–15 wire exactly these and add nothing that is not already a recipe.

**12. `just o11y-gates` needs Docker and pulls `grafana/otel-lgtm:0.32.1`.**

It runs `promtool` out of that image against `ops/prometheus/rules/`. It needs no compose stack and no network beyond the image pull, so it is a fast job — but it is not a pure-Python one, and it cannot share a runner step with the lint jobs.

**13. `just check`'s `precommit` step runs `pre-commit` over `git ls-files` and then `git diff --exit-code`.**

Several hooks mutate files. The `git diff --exit-code` after them is what turns a silent mutation into a loud failure. In CI this needs the full file list to exist, which it does after a normal checkout — but it also means the CI job must not have modified the tree beforehand. Do not add a step that writes into the working tree before `just check` runs.

**14. `check_contract_compatibility.py` already asks M5 to replace half of it.**

Its module docstring says: "M5 replaces the version comparison here with the Conventional Commits range check, once tags and Commitizen exist. The oasdiff half stays." Task 11 does exactly that, and `docs/reference/contract.md:146` has a section titled "What M5 replaces here" that must be updated in the same change.

**15. `just test-record` records against a local WireMock stub, not a real provider.**

The recipe runs `docker compose up -d --wait payment-stub` before `pytest tests/recorded --record-mode=once`. The stub's mappings are committed under `ops/payment-stub/mappings/`. This is the fact behind dropping the weekly re-record job.

**16. `pytest` deselects the `integration` and `contract` markers by default.**

`addopts` contains `-m 'not integration and not contract'`. So `just test` in a CI job needs no Docker, and the container tiers must be selected back in by their own recipes. This is what lets Tasks 13 and 14 split cleanly between fast runners and Docker runners.

**17. The README makes no Backstage claim.** Grepping `README.md`, `examples/reference-service/README.md` and every published page for "backstage" and "catalog" returns nothing. This is the fact behind dropping `catalog-info.yaml`.

**18. mkdocs-material prints a loud multi-line warning about MkDocs 2.0 on every build.**

It is expected output, not a failure — the root `pyproject.toml` already caps `mkdocs>=1.6,<2` with a comment explaining why. Do not "fix" it, and do not let it be mistaken for a broken build when reading CI logs.

**19. A push made with the default `GITHUB_TOKEN` does not trigger other workflows.**

This is a documented GitHub Actions behaviour that exists to prevent infinite loops. It means the bump commit `release.yml` pushes will **not** re-trigger `docs.yml` or `ci.yml`. That is the correct outcome here — both already ran on the merge commit — but it looks like a broken trigger to whoever investigates later, so Task 12 states it in a comment in the workflow itself.

---

## File Structure

**Created at the repository root:**

| Path | Responsibility |
|---|---|
| `CHANGELOG.md` | Generated by Commitizen from Conventional Commits. Never hand-edited |
| `scripts/check_docs_freshness.py` | Reads `last_reviewed` and `covers:` frontmatter from every published page; emits GitHub Actions warnings. Never fails the build |
| `scripts/check_doc_examples.py` | Extracts fenced blocks marked `<!-- exec -->` and runs them against a live service |
| `lychee.toml` | External link checker configuration: exclusions, retries, timeouts |
| `.github/workflows/release.yml` | Commitizen bump, tag, push, GitHub Release |
| `.github/workflows/nightly.yml` | Mutation testing and the full external-link sweep |
| `docs/runbook.md` | On-call: dirty migration, dependency down, high burn rate, rollback |
| `docs/adr/README.md` | Index of decision records and how to add one |
| `docs/adr/template.md` | The shape a new ADR copies |
| `docs/adr/0001-…` … `0012-…` | Twelve backfilled records |

**Created under `examples/reference-service/`:**

| Path | Responsibility |
|---|---|
| `scripts/generate_config_docs.py` | Walks `Settings`, emits the configuration table and `.env.example` |
| `tests/unit/test_config_docs.py` | Unit tests for the walker's rendering, plus the drift assertion |

**Modified:**

| Path | Change |
|---|---|
| `examples/reference-service/src/reference_service/settings.py` | `Field(description=...)` on all 38 leaf fields and a docstring on each sub-model |
| `examples/reference-service/.env.example` | Becomes generated output |
| `examples/reference-service/justfile` | New `config-docs` and `config-docs-check` recipes; `gates` calls the check |
| `examples/reference-service/scripts/check_contract_compatibility.py` | Version comparison replaced by the Conventional Commits range check |
| `docs/reference/configuration.md` | Table replaced by a generated region between markers |
| `docs/reference/contract.md:146` | "What M5 replaces here" rewritten to describe what now exists |
| `docs/guides/outbound-http.md:191,227` | Two M5 forward-references resolved to real links |
| `docs/contributing.md` | The hygiene switch, the release process, new one-time repository settings |
| `docs/roadmap.md` | M5 row to **Done**; the deliberately-excluded table gains the two dropped items |
| `mkdocs.yml` | Nav gains Decisions and Runbook |
| All 20 published `docs/**/*.md` | Frontmatter added |
| `pyproject.toml` (root) | `[tool.commitizen]`, version bootstrapped to `0.5.0` |
| `.github/workflows/ci.yml` | Two jobs become eleven |

---

## Part A — The generated configuration reference

### Task 1: The settings walker

The introspection core, on its own, with no rendering. It exists first because Task 2's "every field has a description" test needs something to enumerate fields with, and because every trap in Verified Facts 2–5 lives here rather than in the renderers.

**Files:**
- Create: `examples/reference-service/scripts/generate_config_docs.py`
- Test: `examples/reference-service/tests/unit/test_config_docs.py`

**Interfaces:**
- Consumes: `reference_service.settings.Settings`.
- Produces: `walk_settings() -> list[ConfigGroup]`, plus the frozen dataclasses `ConfigVariable(name, type_label, default_label, description, secret, required_in_group)` and `ConfigGroup(path, doc, optional, variables)`. Task 3's renderers consume these and nothing else.

- [ ] **Step 1: Write the failing test**

Create `examples/reference-service/tests/unit/test_config_docs.py`:

```python
"""The settings walker, which turns the model into documentable variables.

These tests pin the four introspection traps the plan records as Verified
Facts 2 to 5. Each one, got wrong, produces documentation that is confidently
incorrect rather than obviously broken -- which is the worse failure.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# scripts/ is not an installed package; the generator is a build tool that
# lives beside the code it reads.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from generate_config_docs import ConfigGroup, ConfigVariable, walk_settings  # noqa: E402


@pytest.fixture(scope="module")
def groups() -> list[ConfigGroup]:
    return walk_settings()


@pytest.fixture(scope="module")
def by_name(groups: list[ConfigGroup]) -> dict[str, ConfigVariable]:
    return {
        variable.name: variable
        for group in groups
        for variable in group.variables
    }


def test_walks_every_environment_variable(by_name: dict[str, ConfigVariable]) -> None:
    """38 variables across 8 models -- see the plan's Verified Fact 6."""
    assert len(by_name) == 38


def test_top_level_fields_carry_no_group_prefix(by_name: dict[str, ConfigVariable]) -> None:
    assert "APP_ENVIRONMENT" in by_name
    assert "APP_SERVICE_NAME" in by_name
    assert "APP_HTTP_PORT" in by_name


def test_nested_models_use_the_double_underscore_delimiter(
    by_name: dict[str, ConfigVariable],
) -> None:
    assert "APP_LOG__LEVEL" in by_name
    assert "APP_CACHE__TTL_SECONDS" in by_name


def test_doubly_nested_models_repeat_the_delimiter(
    by_name: dict[str, ConfigVariable],
) -> None:
    """PaymentSettings.http is the only double nesting in the model."""
    assert "APP_PAYMENT__HTTP__CONNECT_TIMEOUT_SECONDS" in by_name


def test_optional_submodels_are_unwrapped_not_skipped(
    by_name: dict[str, ConfigVariable],
) -> None:
    """Verified Fact 4: `DatabaseSettings | None` must be recursed into.

    A walker that only recurses into bare BaseModel annotations silently
    documents 10 variables instead of 38.
    """
    assert "APP_DATABASE__DSN" in by_name
    assert "APP_STORAGE__BUCKET" in by_name


def test_default_factory_fields_do_not_leak_the_undefined_sentinel(
    by_name: dict[str, ConfigVariable],
) -> None:
    """Verified Fact 2: `.default` is PydanticUndefined when a factory is set."""
    levels = by_name["APP_LOG__LEVELS"]
    assert "PydanticUndefined" not in levels.default_label
    assert levels.default_label == "{}"


def test_secret_fields_are_flagged(by_name: dict[str, ConfigVariable]) -> None:
    assert by_name["APP_STORAGE__ACCESS_KEY_ID"].secret is True
    assert by_name["APP_STORAGE__SECRET_ACCESS_KEY"].secret is True


def test_secret_inside_a_union_is_flagged(by_name: dict[str, ConfigVariable]) -> None:
    """Verified Fact 3: `SecretStr | None` fails an identity check.

    Getting this wrong publishes the payment API key as an ordinary string
    field, which is precisely what the SecretStr annotation exists to prevent.
    """
    assert by_name["APP_PAYMENT__API_KEY"].secret is True


def test_ordinary_fields_are_not_flagged_as_secret(
    by_name: dict[str, ConfigVariable],
) -> None:
    assert by_name["APP_SERVICE_NAME"].secret is False


def test_constraints_reach_the_type_label(by_name: dict[str, ConfigVariable]) -> None:
    """Verified Fact 5: annotated_types objects in FieldInfo.metadata."""
    assert by_name["APP_CACHE__POOL_SIZE"].type_label == "integer, ≥ 1"
    assert by_name["APP_CACHE__TTL_SECONDS"].type_label == "integer, ≥ 1"
    assert (
        by_name["APP_CACHE__CONNECT_TIMEOUT_SECONDS"].type_label == "float, > 0"
    )


def test_bounded_integers_render_as_a_range(by_name: dict[str, ConfigVariable]) -> None:
    assert by_name["APP_HTTP_PORT"].type_label == "integer, 1–65535"


def test_literals_render_as_alternatives(by_name: dict[str, ConfigVariable]) -> None:
    assert (
        by_name["APP_ENVIRONMENT"].type_label
        == "`local` | `staging` | `production`"
    )


def test_network_types_render_by_name(by_name: dict[str, ConfigVariable]) -> None:
    assert by_name["APP_DATABASE__DSN"].type_label == "PostgreSQL URL"
    assert by_name["APP_CACHE__DSN"].type_label == "Redis URL"
    assert by_name["APP_PAYMENT__BASE_URL"].type_label == "URL"


def test_secret_type_label_says_secret(by_name: dict[str, ConfigVariable]) -> None:
    assert by_name["APP_STORAGE__ACCESS_KEY_ID"].type_label == "secret"


def test_required_field_in_an_optional_group_is_marked(
    by_name: dict[str, ConfigVariable],
) -> None:
    """The rule the hand-written table states for every APP_STORAGE__ field."""
    assert by_name["APP_STORAGE__BUCKET"].required_in_group is True
    assert by_name["APP_STORAGE__REGION"].required_in_group is False


def test_optional_groups_are_marked_optional(groups: list[ConfigGroup]) -> None:
    by_path = {group.path: group for group in groups}
    assert by_path[("storage",)].optional is True
    assert by_path[("database",)].optional is True
    assert by_path[("log",)].optional is False


def test_groups_are_returned_in_declaration_order(
    groups: list[ConfigGroup],
) -> None:
    """Rendering order is model order, so the diff of a regeneration is small."""
    assert [group.path for group in groups] == [
        (),
        ("log",),
        ("otel",),
        ("database",),
        ("payment",),
        ("payment", "http"),
        ("cache",),
        ("storage",),
    ]
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_config_docs.py -q`
Expected: collection error — `ModuleNotFoundError: No module named 'generate_config_docs'`.

- [ ] **Step 3: Write the walker**

Create `examples/reference-service/scripts/generate_config_docs.py`:

```python
"""Generate the configuration reference and .env.example from the model.

`settings.py` is the single source of truth for every environment variable
this service reads. Before M5 the same 38 variables were described three
times by hand -- in the model's own comments, in .env.example, and in the
documentation table -- in three voices, with nothing keeping the three in
agreement. This script deletes two of those copies.

Run `just config-docs` to regenerate both outputs. `just gates` fails if
either has drifted, exactly as it does for the committed OpenAPI document.

Not an installed module: it is a build tool that reads the package beside
it, so it lives in scripts/ and is imported by path.
"""

from __future__ import annotations

import types
import typing
from dataclasses import dataclass
from typing import Any

import annotated_types
from pydantic import BaseModel, SecretStr
from pydantic.fields import FieldInfo
from pydantic_core import PydanticUndefined

from reference_service.settings import Settings

ENV_PREFIX = "APP_"
NESTED_DELIMITER = "__"

# Pydantic network types render by what they mean to whoever sets the
# variable, not by their Python class name. `PostgresDsn` tells a reader
# nothing that "PostgreSQL URL" does not tell them better.
_NETWORK_TYPE_LABELS = {
    "PostgresDsn": "PostgreSQL URL",
    "RedisDsn": "Redis URL",
    "HttpUrl": "URL",
    "AnyUrl": "URL",
}

_SCALAR_TYPE_LABELS = {
    bool: "boolean",
    int: "integer",
    float: "float",
    str: "string",
}


@dataclass(frozen=True)
class ConfigVariable:
    """One environment variable, as the documentation needs to describe it."""

    name: str
    type_label: str
    default_label: str
    description: str
    secret: bool
    # True when the field has no default AND its group is optional -- the
    # "unset, required once any APP_STORAGE__* variable is set" case. A
    # required field in a non-optional group is simply required.
    required_in_group: bool


@dataclass(frozen=True)
class ConfigGroup:
    """A settings sub-model, with the variables it contributes."""

    # () for Settings itself, ("cache",), ("payment", "http").
    path: tuple[str, ...]
    # The sub-model's docstring, used as the group header in .env.example.
    doc: str
    # True when the whole group may be absent -- `X | None = None`.
    optional: bool
    variables: tuple[ConfigVariable, ...]


def _unwrap_optional(annotation: Any) -> tuple[Any, bool]:
    """Return the non-None member of `X | None`, and whether it was one.

    Verified Facts 3 and 4 both reduce to this: optional sub-models and
    optional secrets are unions, and every check downstream -- "is this a
    BaseModel", "is this a SecretStr" -- fails against the union itself.
    """
    origin = typing.get_origin(annotation)
    if origin is typing.Union or origin is types.UnionType:
        members = [
            argument
            for argument in typing.get_args(annotation)
            if argument is not type(None)
        ]
        if len(members) == 1:
            return members[0], True
    return annotation, False


def _is_model(annotation: Any) -> bool:
    return isinstance(annotation, type) and issubclass(annotation, BaseModel)


def _render_default(info: FieldInfo) -> str:
    """The default, as a reader should see it written in a file.

    Verified Fact 2 is the whole reason this is not `str(info.default)`:
    a field declared with `default_factory` reports `PydanticUndefined` as
    its default while reporting itself as not required, so the naive
    version writes the sentinel's repr into the published documentation.
    """
    if info.default_factory is not None:
        produced = info.default_factory()  # type: ignore[call-arg]
        if isinstance(produced, BaseModel):
            # A sub-model default is not a value anyone sets; the group's
            # own variables carry the real defaults.
            return ""
        if isinstance(produced, dict):
            # Rendered as the JSON a reader would actually write.
            return "{}" if not produced else repr(produced)
        return str(produced)
    if info.default is PydanticUndefined or info.default is None:
        return "unset"
    if isinstance(info.default, bool):
        return "true" if info.default else "false"
    return str(info.default)


def _constraint_label(base: str, metadata: list[Any]) -> str:
    """Fold annotated_types constraints into the base type's label.

    Verified Fact 5: `Field(default=10, ge=1)` puts `Ge(ge=1)` here, and
    these are what the hand-written table rendered as "integer, ≥ 1".
    """
    minimum: Any = None
    maximum: Any = None
    exclusive_minimum: Any = None
    for item in metadata:
        if isinstance(item, annotated_types.Ge):
            minimum = item.ge
        elif isinstance(item, annotated_types.Le):
            maximum = item.le
        elif isinstance(item, annotated_types.Gt):
            exclusive_minimum = item.gt

    if minimum is not None and maximum is not None:
        return f"{base}, {minimum}–{maximum}"
    if minimum is not None:
        return f"{base}, ≥ {minimum}"
    if exclusive_minimum is not None:
        return f"{base}, > {exclusive_minimum}"
    return base


def _render_type(info: FieldInfo) -> str:
    """A human label for the annotation, constraints folded in.

    An explicit `json_schema_extra={"type_label": ...}` always wins. That
    escape hatch exists for the handful of fields whose real constraint is
    a regular expression: deriving "string, 3–63 chars" from
    `^[a-z0-9][a-z0-9.-]{1,61}[a-z0-9]$` is not a job for a generator.
    """
    extra = info.json_schema_extra
    if isinstance(extra, dict) and "type_label" in extra:
        return str(extra["type_label"])

    annotation, _ = _unwrap_optional(info.annotation)

    if annotation is SecretStr:
        return "secret"

    name = getattr(annotation, "__name__", "")
    if name in _NETWORK_TYPE_LABELS:
        return _NETWORK_TYPE_LABELS[name]

    origin = typing.get_origin(annotation)
    if origin is typing.Literal:
        return " | ".join(f"`{value}`" for value in typing.get_args(annotation))
    if origin is dict:
        return "JSON object"

    base = _SCALAR_TYPE_LABELS.get(annotation, name or "string")
    return _constraint_label(base, list(info.metadata))


def _is_secret(info: FieldInfo) -> bool:
    """Verified Fact 3: unwrap before comparing, or `SecretStr | None` slips."""
    annotation, _ = _unwrap_optional(info.annotation)
    return annotation is SecretStr


def _variable_name(path: tuple[str, ...], field_name: str) -> str:
    parts = (*path, field_name)
    return ENV_PREFIX + NESTED_DELIMITER.join(part.upper() for part in parts)


def _walk_model(
    model: type[BaseModel],
    path: tuple[str, ...],
    optional: bool,
    groups: list[ConfigGroup],
) -> None:
    """Append this model's group, then recurse into its sub-models.

    Depth-first in declaration order, so the generated files diff minimally
    against a model whose fields were reordered rather than rewritten.
    """
    variables: list[ConfigVariable] = []
    nested: list[tuple[str, type[BaseModel], bool]] = []

    for field_name, info in model.model_fields.items():
        annotation, was_optional = _unwrap_optional(info.annotation)
        if _is_model(annotation):
            nested.append((field_name, annotation, was_optional))
            continue
        variables.append(
            ConfigVariable(
                name=_variable_name(path, field_name),
                type_label=_render_type(info),
                default_label=_render_default(info),
                description=info.description or "",
                secret=_is_secret(info),
                required_in_group=info.is_required() and optional,
            )
        )

    groups.append(
        ConfigGroup(
            path=path,
            doc=(model.__doc__ or "").strip(),
            optional=optional,
            variables=tuple(variables),
        )
    )

    for field_name, sub_model, was_optional in nested:
        _walk_model(sub_model, (*path, field_name), was_optional, groups)


def walk_settings() -> list[ConfigGroup]:
    """Every environment variable the service reads, grouped by sub-model."""
    groups: list[ConfigGroup] = []
    _walk_model(Settings, (), optional=False, groups=groups)
    return groups
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_config_docs.py -q`
Expected: PASS.

Two failures are likely on the first run, and both are the generator being right rather than the test being wrong:

- `test_groups_are_returned_in_declaration_order` fails if you recursed inline instead of collecting `nested` first. The two-pass order above puts `("payment",)` before `("payment", "http")` and after `("database",)`; an inline recursion interleaves them.
- `test_constraints_reach_the_type_label` fails for `APP_HTTP_PORT` if `Le` is not read — `Field(default=8000, ge=1, le=65535)` needs both bounds to render `integer, 1–65535`.

- [ ] **Step 5: Check types and lint**

Run: `cd examples/reference-service && uv run mypy && uv run ruff check . && uv run ruff format --check .`
Expected: clean. `scripts/` is outside the strict-mypy trees, so the `Any` in the annotation helpers is fine.

- [ ] **Step 6: Commit**

```bash
git add examples/reference-service/scripts/generate_config_docs.py \
        examples/reference-service/tests/unit/test_config_docs.py
git commit -m "feat(reference-service): add a settings walker for generated config docs"
```

---

### Task 2: Descriptions on every field

The walker now enumerates 38 variables with empty descriptions. This task fills them from `docs/reference/configuration.md`, which holds the best-written copy of the three, and adds the test that keeps a future field from arriving undocumented.

**Files:**
- Modify: `examples/reference-service/src/reference_service/settings.py`
- Modify: `examples/reference-service/tests/unit/test_config_docs.py`

**Interfaces:**
- Consumes: `walk_settings()` from Task 1.
- Produces: a `Settings` model where every leaf field has a non-empty `description`, and every sub-model has a docstring. Task 3 renders both.

**The rule for what goes where.** A `description` addresses whoever *sets* the variable. A Python comment addresses whoever *reads the code*. Move the first, keep the second. `LogSettings.model_config`'s comment explaining why `frozen=True` is not inherited stays exactly where it is — it is meaningless to an operator and essential to a maintainer. `sample_ratio`'s explanation that sampling is parent-based moves, because it changes what value someone chooses.

- [ ] **Step 1: Write the failing test**

Append to `examples/reference-service/tests/unit/test_config_docs.py`:

```python
def test_every_variable_has_a_description(by_name: dict[str, ConfigVariable]) -> None:
    """A new setting must not be able to arrive undocumented.

    This is the gate that makes `Field(description=...)` the single source
    of truth rather than a convention people remember unevenly. Without it,
    the generated table quietly grows a row with an empty Meaning column.
    """
    undocumented = sorted(
        name
        for name, variable in by_name.items()
        if not variable.description.strip()
    )
    assert undocumented == [], (
        f"{len(undocumented)} setting(s) have no Field(description=...): "
        f"{undocumented}"
    )


def test_every_group_has_a_docstring(groups: list[ConfigGroup]) -> None:
    """Group docstrings become the section headers in .env.example."""
    undocumented = sorted(
        "".join(group.path) or "Settings" for group in groups if not group.doc
    )
    assert undocumented == []


def test_no_secret_field_has_a_default(by_name: dict[str, ConfigVariable]) -> None:
    """A credential with a default is a credential committed to the repository.

    The generator prints defaults into two published files. Today no secret
    has one; this asserts it rather than trusting it, because the day one
    does, the leak is silent and permanent.
    """
    leaked = sorted(
        name
        for name, variable in by_name.items()
        if variable.secret and variable.default_label != "unset"
    )
    assert leaked == []
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_config_docs.py -q`
Expected: `test_every_variable_has_a_description` FAILS listing all 38 names; `test_every_group_has_a_docstring` FAILS listing the groups with no docstring. `test_no_secret_field_has_a_default` should already PASS — it is a regression guard, not a red test.

- [ ] **Step 3: Add descriptions and docstrings**

Work through `settings.py` top to bottom. Source each description from the matching row of `docs/reference/configuration.md`, which is the richest of the three existing copies. Keep the markdown — links and bold survive into the table, and Task 3 strips them for `.env.example`.

The five shapes you will need:

```python
class LogSettings(BaseModel):
    """Logging. Structured JSON everywhere except a local environment."""

    model_config = ConfigDict(frozen=True)

    level: LogLevel = Field(default="info", description="The root log level.")
    # Still a genuinely mutable dict despite `frozen=True`: frozen refuses
    # reassigning the `levels` field itself, but not mutating the dict
    # object already held there. See the module docstring.
    levels: dict[str, LogLevel] = Field(
        default_factory=dict,
        description=(
            "Per-logger overrides, as JSON. Silencing a chatty library is "
            "configuration, not a code change."
        ),
    )
```

A field that had no `Field(...)` call gains one. A field that already has constraints keeps them and gains the keyword:

```python
    sample_ratio: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description=(
            "Fraction of *new* traces recorded, 0.0 to 1.0. Sampling is "
            "parent-based, so a request arriving with a sampled parent is "
            "always recorded whatever this says."
        ),
    )
```

A required field with no default takes `Field(...)` as its whole assignment:

```python
    dsn: PostgresDsn = Field(
        description=(
            "Where to store orders. **Leave it unset to run with no database "
            "at all** — the service starts on an in-memory repository and "
            "serves normally."
        ),
    )
```

The one field needing the `type_label` escape hatch is `StorageSettings.bucket`, whose constraint is a regular expression:

```python
    bucket: Annotated[str, StringConstraints(pattern=_BUCKET_NAME_PATTERN)] = Field(
        json_schema_extra={"type_label": "string, 3–63 chars"},
        description=(
            "The S3 bucket receipts are stored in. Checked against Amazon's "
            "naming rule (lowercase, digits, hyphens, dots) at startup, so a "
            "typo like a capital letter fails as exit 78, not as the first "
            "failed `PutObject`."
        ),
    )
```

And each sub-model gains a one-line docstring, which becomes its `.env.example` header:

```python
class CacheSettings(BaseModel):
    """Redis. Optional: leave the whole block unset to run with no cache."""
```

Do the same for `OtelSettings`, `DatabaseSettings`, `HttpClientSettings`, `PaymentSettings`, `StorageSettings`, and `Settings` itself.

**Two things not to do.** Do not delete the comments explaining *why* a value is what it is to a maintainer — `CacheSettings`'s paragraph on why both timeouts are sub-second is engineering rationale, and it stays as a comment above the fields even though a shorter version of it also becomes the description. And do not reword `DatabaseSettings.dsn`'s comment about golang-migrate never reading the setting; it answers a question only a maintainer asks.

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_config_docs.py -q`
Expected: PASS, all groups and all 38 variables documented.

- [ ] **Step 5: Run the full unit suite**

Run: `cd examples/reference-service && uv run pytest -q`
Expected: PASS. Settings tests are sensitive to this change — adding `Field(...)` to a previously bare field can alter a validation error's shape. If `tests/unit/test_settings.py` fails on an error message, the description is not at fault; check you have not accidentally changed a default or a constraint while restructuring the assignment.

- [ ] **Step 6: Check types and lint**

Run: `cd examples/reference-service && uv run mypy && uv run ruff check . && uv run ruff format --check .`
Expected: clean. `settings.py` is not in the strict trees, but it is still type-checked.

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service/src/reference_service/settings.py \
        examples/reference-service/tests/unit/test_config_docs.py
git commit -m "feat(reference-service): describe every setting on the model itself"
```

---

### Task 3: Render, regenerate and gate

Two renderers, two regenerated files, and the drift gate that makes them stay honest.

**Files:**
- Modify: `examples/reference-service/scripts/generate_config_docs.py`
- Modify: `examples/reference-service/tests/unit/test_config_docs.py`
- Modify: `examples/reference-service/justfile`
- Modify: `examples/reference-service/.env.example` (becomes generated)
- Modify: `docs/reference/configuration.md` (table becomes a generated region)

**Interfaces:**
- Consumes: `walk_settings()`, `ConfigGroup`, `ConfigVariable`.
- Produces: `render_markdown_table() -> str`, `render_env_example() -> str`, `write_outputs() -> None`, `check_outputs() -> list[str]` returning the paths that are stale. Task 15's CI job calls `just config-docs-check`, never the module.

- [ ] **Step 1: Write the failing tests**

Append to `examples/reference-service/tests/unit/test_config_docs.py`:

```python
from generate_config_docs import (  # noqa: E402
    CONFIGURATION_DOC,
    ENV_EXAMPLE,
    MARKER_BEGIN,
    MARKER_END,
    check_outputs,
    render_env_example,
    render_markdown_table,
)


def test_markdown_table_has_a_header_and_one_row_per_variable() -> None:
    table = render_markdown_table()
    lines = [line for line in table.splitlines() if line.startswith("|")]
    # header + separator + 38 rows
    assert len(lines) == 40
    assert lines[0].startswith("| Variable |")


def test_markdown_rows_carry_the_variable_type_and_default() -> None:
    row = next(
        line
        for line in render_markdown_table().splitlines()
        if line.startswith("| `APP_CACHE__TTL_SECONDS`")
    )
    assert "integer, ≥ 1" in row
    assert "`300`" in row


def test_markdown_never_emits_a_raw_newline_inside_a_row() -> None:
    """A description with a line break silently breaks the table.

    Descriptions are written as wrapped Python strings; if one ever gains a
    literal newline, the row after it renders as body text and the table
    ends early -- with no error anywhere.
    """
    for line in render_markdown_table().splitlines():
        if line.startswith("| `APP_"):
            assert line.rstrip().endswith("|")


def test_markdown_marks_a_required_field_in_an_optional_group() -> None:
    row = next(
        line
        for line in render_markdown_table().splitlines()
        if line.startswith("| `APP_STORAGE__BUCKET`")
    )
    assert "required once any" in row


def test_env_example_strips_markdown_links() -> None:
    """`.env.example` is read in an editor, not rendered.

    A description carrying `[Outbound HTTP calls](../guides/outbound-http.md)`
    must appear as its text, not its source.
    """
    rendered = render_env_example()
    assert "](" not in rendered
    assert "**" not in rendered


def test_env_example_comments_every_prose_line() -> None:
    for line in render_env_example().splitlines():
        if line and not line.startswith("#"):
            assert "=" in line, f"uncommented prose line: {line!r}"


def test_env_example_comments_out_variables_with_no_default() -> None:
    """An unset optional variable must not become an empty assignment.

    `APP_DATABASE__DSN=` is not the same as absent: it is a malformed URL,
    and the service would exit 78 on a file that is supposed to be a
    working starting point.
    """
    rendered = render_env_example()
    assert "# APP_DATABASE__DSN=" in rendered
    assert "\nAPP_DATABASE__DSN=" not in rendered


def test_env_example_sets_variables_that_have_defaults() -> None:
    rendered = render_env_example()
    assert "\nAPP_HTTP_PORT=8000" in rendered
    assert "\nAPP_LOG__LEVEL=info" in rendered


def test_committed_outputs_are_current() -> None:
    """The drift gate, as a test as well as a recipe.

    Running it here means a stale file fails the fast unit loop rather than
    waiting for CI -- the same arrangement the OpenAPI contract has.
    """
    stale = check_outputs()
    assert stale == [], (
        f"stale generated file(s): {stale}. Run `just config-docs` and "
        f"commit the result."
    )


def test_configuration_doc_keeps_its_generated_markers() -> None:
    text = CONFIGURATION_DOC.read_text(encoding="utf-8")
    assert text.count(MARKER_BEGIN) == 1
    assert text.count(MARKER_END) == 1
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_config_docs.py -q`
Expected: `ImportError: cannot import name 'render_markdown_table'`.

- [ ] **Step 3: Write the renderers**

Append to `examples/reference-service/scripts/generate_config_docs.py`:

```python
import re
import sys
from pathlib import Path

_SERVICE_ROOT = Path(__file__).resolve().parents[1]
_REPOSITORY_ROOT = _SERVICE_ROOT.parents[1]

ENV_EXAMPLE = _SERVICE_ROOT / ".env.example"
CONFIGURATION_DOC = _REPOSITORY_ROOT / "docs" / "reference" / "configuration.md"

MARKER_BEGIN = "<!-- generated: config-table. Run `just config-docs`. -->"
MARKER_END = "<!-- /generated: config-table -->"

_ENV_HEADER = """\
# Copy to .env for local development. Never commit .env itself.
#
# GENERATED FILE -- do not edit. Every line below comes from
# src/reference_service/settings.py. Change a description there and run
# `just config-docs`; `just gates` fails if this file has drifted.
"""

# Markdown that means something to a rendered page and nothing to someone
# reading a dotfile in an editor.
_MARKDOWN_LINK = re.compile(r"\[([^\]]+)\]\([^)]+\)")
_MARKDOWN_EMPHASIS = re.compile(r"\*\*([^*]+)\*\*|\*([^*]+)\*|`([^`]+)`")


def _plain_text(description: str) -> str:
    """Markdown reduced to what it says, for a file nobody renders."""
    text = _MARKDOWN_LINK.sub(r"\1", description)
    return _MARKDOWN_EMPHASIS.sub(
        lambda match: match.group(1) or match.group(2) or match.group(3), text
    )


def _default_cell(variable: ConfigVariable) -> str:
    if variable.required_in_group:
        group = variable.name.rsplit(NESTED_DELIMITER, 1)[0]
        return f"unset, required once any `{group}{NESTED_DELIMITER}*` is set"
    if variable.default_label in {"", "unset"}:
        return "unset"
    return f"`{variable.default_label}`"


def render_markdown_table() -> str:
    """The published reference table, one row per environment variable."""
    rows = [
        "| Variable | Type | Default | Meaning |",
        "| --- | --- | --- | --- |",
    ]
    for group in walk_settings():
        for variable in group.variables:
            # Descriptions are wrapped Python strings; a stray newline would
            # end the table silently, so collapse whitespace unconditionally.
            meaning = " ".join(variable.description.split())
            rows.append(
                f"| `{variable.name}` | {variable.type_label} | "
                f"{_default_cell(variable)} | {meaning} |"
            )
    return "\n".join(rows)


def _wrap_comment(text: str, width: int = 76) -> list[str]:
    """Prose as `#` lines, wrapped so the file stays readable in an editor."""
    words = text.split()
    lines: list[str] = []
    current = "#"
    for word in words:
        candidate = f"{current} {word}"
        if len(candidate) > width and current != "#":
            lines.append(current)
            current = f"# {word}"
        else:
            current = candidate
    if current != "#":
        lines.append(current)
    return lines


def render_env_example() -> str:
    """A working starting point, with every variable documented in place."""
    blocks: list[str] = [_ENV_HEADER]
    for group in walk_settings():
        section: list[str] = []
        if group.doc:
            section.extend(_wrap_comment(_plain_text(group.doc)))
        for variable in group.variables:
            section.extend(_wrap_comment(_plain_text(variable.description)))
            value = variable.default_label
            if variable.default_label in {"", "unset"}:
                # Commented out, not left empty: `APP_DATABASE__DSN=` is a
                # malformed URL, and the service exits 78 on it. Absent is
                # the supported configuration; empty is a broken one.
                section.append(f"# {variable.name}=")
            else:
                section.append(f"{variable.name}={value}")
        blocks.append("\n".join(section))
    return "\n\n".join(blocks) + "\n"


def _configuration_doc_with_table(existing: str, table: str) -> str:
    """Replace only the region between the markers, keeping the prose."""
    begin = existing.index(MARKER_BEGIN) + len(MARKER_BEGIN)
    end = existing.index(MARKER_END)
    return existing[:begin] + "\n\n" + table + "\n\n" + existing[end:]


def _rendered_outputs() -> dict[Path, str]:
    return {
        ENV_EXAMPLE: render_env_example(),
        CONFIGURATION_DOC: _configuration_doc_with_table(
            CONFIGURATION_DOC.read_text(encoding="utf-8"), render_markdown_table()
        ),
    }


def write_outputs() -> None:
    for path, content in _rendered_outputs().items():
        path.write_text(content, encoding="utf-8")


def check_outputs() -> list[str]:
    """Paths whose committed content differs from what the model produces."""
    return [
        str(path.relative_to(_REPOSITORY_ROOT))
        for path, content in _rendered_outputs().items()
        if path.read_text(encoding="utf-8") != content
    ]


if __name__ == "__main__":
    if "--check" in sys.argv:
        stale = check_outputs()
        if stale:
            sys.stderr.write(
                "These generated files are stale:\n"
                + "".join(f"  {path}\n" for path in stale)
                + "Run `just config-docs` and commit the result.\n"
            )
            raise SystemExit(1)
        print("configuration documentation is current")
    else:
        write_outputs()
        print("regenerated .env.example and docs/reference/configuration.md")
```

- [ ] **Step 4: Add the markers to the documentation page**

In `docs/reference/configuration.md`, replace the whole `## Variables` table — the header row, the separator, and all 38 data rows — with the two markers, leaving every paragraph before and after it untouched:

```markdown
## Variables

<!-- generated: config-table. Run `just config-docs`. -->
<!-- /generated: config-table -->
```

Add a sentence above the markers so a reader who lands on the page knows why editing it will not stick:

```markdown
This table is generated from the settings model. To change a description,
edit `Field(description=...)` in
`examples/reference-service/src/reference_service/settings.py` and run
`just config-docs`.
```

- [ ] **Step 5: Add the recipes**

In `examples/reference-service/justfile`, after the `openapi` recipe, so the two generated-artifact recipes sit together:

```just
# Regenerate .env.example and the published configuration table from the
# settings model, then commit the result. Read the diff first: it is your
# configuration change, in full.
config-docs:
    uv run python scripts/generate_config_docs.py

# Fail if either generated file has drifted from the model.
config-docs-check:
    uv run python scripts/generate_config_docs.py --check
```

And add it to the gates, beside the schema and migration gates:

```just
gates:
    uv run pytest tests/unit/test_migration_files.py
    uv run pytest -m integration -k "schema_gates or schema_drift"
    just config-docs-check
```

- [ ] **Step 6: Regenerate both files**

Run: `cd examples/reference-service && just config-docs`
Expected: `regenerated .env.example and docs/reference/configuration.md`.

Now **read the diff**. This is the step where a description that lost a nuance in the move shows up:

Run: `git diff docs/reference/configuration.md examples/reference-service/.env.example`

Compare the generated table against `git show HEAD:docs/reference/configuration.md` row by row. Every row should carry the same meaning as the hand-written one. Where it does not, the fix goes in `settings.py`, never in the output.

- [ ] **Step 7: Run the tests to verify they pass**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_config_docs.py -q`
Expected: PASS, including `test_committed_outputs_are_current`.

- [ ] **Step 8: Verify the drift gate actually catches drift**

A gate nobody has seen fail is not known to work:

```bash
cd examples/reference-service
printf '\n# hand-edited\n' >> .env.example
just config-docs-check; echo "exit: $?"
git checkout .env.example
```

Expected: the command prints `These generated files are stale:` naming `examples/reference-service/.env.example`, and `exit: 1`.

- [ ] **Step 9: Verify the site still builds**

Run: `cd ../.. && uv run mkdocs build --strict`
Expected: built, no warnings. A malformed generated table shows up here as a broken page rather than an error.

- [ ] **Step 10: Commit**

```bash
git add examples/reference-service/scripts/generate_config_docs.py \
        examples/reference-service/tests/unit/test_config_docs.py \
        examples/reference-service/justfile \
        examples/reference-service/.env.example \
        docs/reference/configuration.md
git commit -m "feat(reference-service): generate the configuration reference from the model"
```

---

## Part B — Documentation hygiene

Spec 10.3 names four mechanisms. `mkdocs build --strict` already exists and needs no work. These three tasks add the other three.

### Task 4: Review dates and path coupling

The two subjective checks, both emitting warnings and never failing. Read the Global Constraint on this before starting: making them fail is not a stricter version of this task, it is a different decision, and it is documented as not-taken.

**Files:**
- Create: `scripts/check_docs_freshness.py`
- Create: `tests/test_check_docs_freshness.py` (repository root — the first root-level test)
- Modify: all 20 published pages under `docs/`
- Modify: `pyproject.toml` (root) — a `dev` dependency group for pytest
- Modify: `justfile` (root)

**Interfaces:**
- Consumes: `git diff --name-only <base>...<head>`, and YAML frontmatter on each page.
- Produces: `scripts/check_docs_freshness.py <base> <head>` printing `::warning file=…::…` lines and always exiting 0. Task 15 wires it into `ci.yml`.

**How the two checks differ from `check_docs_updated.py`.** That script is the blunt version: *some* source changed and *no* documentation did, so fail. This is the precise version: *this specific page* claims to cover *this specific path*, that path changed, and the page did not. The blunt one stays as the hard gate. This one is the targeted warning beside it. Task 17 documents the conditions for retiring the blunt one.

- [ ] **Step 1: Write the failing test**

Create `tests/test_check_docs_freshness.py` at the repository root:

```python
"""The documentation freshness and path-coupling warnings.

These never fail a build, which makes them easy to get silently wrong --
a check that always prints nothing looks identical to a check that has
nothing to report. These tests pin the difference.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_docs_freshness import (  # noqa: E402
    MAX_REVIEW_AGE_DAYS,
    Page,
    parse_frontmatter,
    stale_pages,
    uncovered_changes,
)


def test_parse_frontmatter_reads_both_keys() -> None:
    text = (
        "---\n"
        "last_reviewed: 2026-09-10\n"
        "covers:\n"
        "  - examples/reference-service/src/reference_service/settings.py\n"
        "---\n\n"
        "# Title\n"
    )
    meta = parse_frontmatter(text)
    assert meta["last_reviewed"] == dt.date(2026, 9, 10)
    assert meta["covers"] == [
        "examples/reference-service/src/reference_service/settings.py"
    ]


def test_parse_frontmatter_on_a_page_with_none() -> None:
    """Every page had no frontmatter before this task; absence is not an error."""
    assert parse_frontmatter("# Title\n\nBody.\n") == {}


def test_parse_frontmatter_ignores_a_horizontal_rule() -> None:
    """`---` mid-document is a rule, not a frontmatter fence."""
    assert parse_frontmatter("# Title\n\n---\n\nBody.\n") == {}


def test_a_page_reviewed_today_is_not_stale() -> None:
    today = dt.date(2026, 9, 10)
    page = Page(path="docs/index.md", last_reviewed=today, covers=[])
    assert stale_pages([page], today=today) == []


def test_a_page_past_the_maximum_age_is_stale() -> None:
    today = dt.date(2026, 9, 10)
    page = Page(
        path="docs/index.md",
        last_reviewed=today - dt.timedelta(days=MAX_REVIEW_AGE_DAYS + 1),
        covers=[],
    )
    assert [entry.path for entry in stale_pages([page], today=today)] == [
        "docs/index.md"
    ]


def test_a_page_with_no_review_date_is_not_reported_as_stale() -> None:
    """Missing is a different problem from old, and reported separately.

    Conflating them means the day someone adds a page with no frontmatter,
    it is reported as 'last reviewed 2000-01-01' -- a date that never
    existed, in a warning nobody can act on.
    """
    today = dt.date(2026, 9, 10)
    page = Page(path="docs/index.md", last_reviewed=None, covers=[])
    assert stale_pages([page], today=today) == []


def test_a_covered_path_that_changed_without_the_page_is_reported() -> None:
    page = Page(
        path="docs/reference/configuration.md",
        last_reviewed=None,
        covers=["examples/reference-service/src/reference_service/settings.py"],
    )
    changed = {"examples/reference-service/src/reference_service/settings.py"}
    assert uncovered_changes([page], changed) == [
        (
            "docs/reference/configuration.md",
            "examples/reference-service/src/reference_service/settings.py",
        )
    ]


def test_a_covered_path_that_changed_with_the_page_is_not_reported() -> None:
    page = Page(
        path="docs/reference/configuration.md",
        last_reviewed=None,
        covers=["examples/reference-service/src/reference_service/settings.py"],
    )
    changed = {
        "examples/reference-service/src/reference_service/settings.py",
        "docs/reference/configuration.md",
    }
    assert uncovered_changes([page], changed) == []


def test_a_covers_entry_matches_a_directory_prefix() -> None:
    """`covers: [src/api/]` must match every file beneath it.

    Requiring one entry per file would make the frontmatter unmaintainable
    and guarantee it goes stale -- which is the thing being prevented.
    """
    page = Page(
        path="docs/reference/http-api.md",
        last_reviewed=None,
        covers=["examples/reference-service/src/reference_service/api/"],
    )
    changed = {"examples/reference-service/src/reference_service/api/orders.py"}
    assert uncovered_changes([page], changed) == [
        (
            "docs/reference/http-api.md",
            "examples/reference-service/src/reference_service/api/",
        )
    ]


def test_an_unrelated_change_reports_nothing() -> None:
    page = Page(
        path="docs/reference/http-api.md",
        last_reviewed=None,
        covers=["examples/reference-service/src/reference_service/api/"],
    )
    assert uncovered_changes([page], {"README.md"}) == []
```

- [ ] **Step 2: Add pytest to the root project**

The repository root has no test runner yet. In the root `pyproject.toml`:

```toml
[dependency-groups]
docs = [
    # Capped below 2.0: MkDocs 2.0 removes the plugin system entirely, with
    # no migration path, which would break mkdocs-material and the docs
    # build outright.
    "mkdocs>=1.6,<2",
    "mkdocs-material>=9.5,<10",
]
# The repository's own scripts have tests. The service's suite is entirely
# separate and lives under examples/reference-service/.
dev = [
    "pytest>=8.3",
]

[tool.pytest.ini_options]
addopts = "-q --strict-markers --strict-config"
testpaths = ["tests"]
```

- [ ] **Step 3: Run the test to verify it fails**

Run: `uv run --group dev pytest tests/ -q`
Expected: collection error — `ModuleNotFoundError: No module named 'check_docs_freshness'`.

- [ ] **Step 4: Write the script**

Create `scripts/check_docs_freshness.py`:

```python
#!/usr/bin/env python3
"""Warn about documentation that has gone unreviewed, or unreviewed code.

Two checks, both advisory, neither able to fail a build:

  last_reviewed:  a page nobody has looked at in MAX_REVIEW_AGE_DAYS
  covers:         a path a page claims to describe changed, and the page
                  did not

The precise counterpart to scripts/check_docs_updated.py, which is the
blunt version of the second check and IS a hard gate. This one names the
page and the path; that one only knows that source moved and prose did not.

Both stay for now. See docs/contributing.md for what has to be true before
these warnings become failures -- the switch is deliberate and not taken
here, because a large refactor trips path coupling across many pages at
once, which lands exactly when a team is busiest.

Needs PyYAML, which arrives transitively with MkDocs, so this runs in the
documentation job after `uv sync --group docs` rather than as a bare
python3 script the way check_docs_updated.py does.
"""

from __future__ import annotations

import datetime as dt
import subprocess
import sys
from collections.abc import Iterable, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

DOCS_ROOT = Path("docs")

# Excluded from the review-date check, for different reasons each.
#
# superpowers/ is an archive of design specs and implementation plans; it
# is not published (mkdocs.yml excludes it) and it goes out of date by
# design once a milestone lands.
#
# adr/ is history. An accepted decision record does not go stale: it
# records what was decided, when, and why. Asking someone to re-review one
# twice a year trains them to ignore the warning, and superseding a
# decision means writing a NEW record, never editing the old one.
EXCLUDED_PREFIXES = ("docs/superpowers/", "docs/adr/")

# Six months. Long enough that an actively maintained page is never
# flagged, short enough that a page nobody has opened in a release cycle
# is. Not tuned against anything -- adjust it once there is evidence.
MAX_REVIEW_AGE_DAYS = 180


@dataclass(frozen=True)
class Page:
    """A published page and the two hygiene claims its frontmatter makes."""

    path: str
    last_reviewed: dt.date | None
    covers: list[str] = field(default_factory=list)


def parse_frontmatter(text: str) -> dict[str, Any]:
    """The YAML block between the leading `---` fences, or an empty dict.

    Deliberately strict about the opening fence being the FIRST line: a
    `---` used as a horizontal rule mid-page is ordinary Markdown, and
    treating it as frontmatter would swallow the prose after it.
    """
    if not text.startswith("---\n"):
        return {}
    end = text.find("\n---", 4)
    if end == -1:
        return {}
    loaded = yaml.safe_load(text[4:end])
    return loaded if isinstance(loaded, dict) else {}


def load_pages(root: Path = DOCS_ROOT) -> list[Page]:
    """Every published page, with whatever frontmatter it carries."""
    pages: list[Page] = []
    for path in sorted(root.rglob("*.md")):
        as_posix = path.as_posix()
        if as_posix.startswith(EXCLUDED_PREFIXES):
            continue
        meta = parse_frontmatter(path.read_text(encoding="utf-8"))
        reviewed = meta.get("last_reviewed")
        covers = meta.get("covers") or []
        pages.append(
            Page(
                path=as_posix,
                # yaml.safe_load already produces a date for an unquoted
                # ISO-8601 value; anything else is malformed and treated as
                # absent rather than crashing an advisory check.
                last_reviewed=reviewed if isinstance(reviewed, dt.date) else None,
                covers=[str(entry) for entry in covers],
            )
        )
    return pages


def stale_pages(pages: Iterable[Page], today: dt.date) -> list[Page]:
    """Pages whose review date is older than the maximum age.

    A page with NO review date is not stale -- it is undeclared, which is a
    different problem reported by its own warning. Conflating the two
    produces warnings citing dates that never existed.
    """
    cutoff = today - dt.timedelta(days=MAX_REVIEW_AGE_DAYS)
    return [
        page
        for page in pages
        if page.last_reviewed is not None and page.last_reviewed < cutoff
    ]


def undeclared_pages(pages: Iterable[Page]) -> list[Page]:
    """Published pages carrying no `last_reviewed` at all."""
    return [page for page in pages if page.last_reviewed is None]


def uncovered_changes(
    pages: Iterable[Page], changed: set[str]
) -> list[tuple[str, str]]:
    """(page, covered path) pairs where the path moved and the page did not.

    A `covers:` entry ending in `/` matches every file beneath it. Listing
    files one by one would make the frontmatter unmaintainable, and
    unmaintainable frontmatter goes stale -- which is the failure this
    whole mechanism exists to catch.
    """
    findings: list[tuple[str, str]] = []
    for page in pages:
        if page.path in changed:
            continue
        for covered in page.covers:
            if any(
                path == covered
                or (covered.endswith("/") and path.startswith(covered))
                for path in changed
            ):
                findings.append((page.path, covered))
    return findings


def changed_files(base: str, head: str) -> set[str]:
    """Paths changed between `base` and `head`, as git reports them."""
    completed = subprocess.run(
        ["git", "diff", "--name-only", f"{base}...{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return {line for line in completed.stdout.splitlines() if line}


def warn(path: str, message: str) -> None:
    """A GitHub Actions annotation, which is also readable as plain text."""
    print(f"::warning file={path}::{message}")


def main(argv: Sequence[str]) -> int:
    """Always returns 0. These checks advise; they never block."""
    if len(argv) != 3:
        sys.stderr.write("usage: check_docs_freshness.py <base> <head>\n")
        return 2

    pages = load_pages()
    changed = changed_files(argv[1], argv[2])
    today = dt.date.today()

    for page in stale_pages(pages, today=today):
        age = (today - page.last_reviewed).days  # type: ignore[operator]
        warn(
            page.path,
            f"last reviewed {page.last_reviewed} ({age} days ago, maximum "
            f"{MAX_REVIEW_AGE_DAYS}). Re-read it and update last_reviewed.",
        )

    for page in undeclared_pages(pages):
        warn(page.path, "no `last_reviewed` in its frontmatter.")

    for page_path, covered in uncovered_changes(pages, changed):
        warn(
            page_path,
            f"covers `{covered}`, which changed in this pull request while "
            f"this page did not. Check whether it is still accurate.",
        )

    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run --group dev pytest tests/ -q`
Expected: PASS, 11 tests.

- [ ] **Step 6: Add frontmatter to all 20 pages**

Every published page gets `last_reviewed: 2026-09-10`. Pages documenting a specific surface also get `covers:`. Use these pairings — they are the ones where a code change genuinely invalidates the prose:

| Page | `covers:` |
|---|---|
| `reference/configuration.md` | `examples/reference-service/src/reference_service/settings.py` |
| `reference/http-api.md` | `examples/reference-service/src/reference_service/api/` |
| `reference/errors.md` | `examples/reference-service/src/reference_service/api/errors.py` |
| `reference/logging.md` | `examples/reference-service/src/reference_service/observability/` |
| `reference/observability.md` | `examples/reference-service/src/reference_service/observability/`, `examples/reference-service/ops/` |
| `reference/contract.md` | `examples/reference-service/openapi.json`, `examples/reference-service/scripts/check_contract_compatibility.py` |
| `reference/commands.md` | `examples/reference-service/justfile` |
| `explanation/layers.md` | `examples/reference-service/.importlinter` |
| `explanation/architecture.md` | `examples/reference-service/src/reference_service/` |
| `explanation/testing.md` | `examples/reference-service/tests/` |
| `guides/outbound-http.md` | `examples/reference-service/src/reference_service/infrastructure/http/` |
| `guides/run-in-a-container.md` | `examples/reference-service/Dockerfile`, `examples/reference-service/compose.yaml` |
| `guides/add-an-endpoint.md` | `examples/reference-service/src/reference_service/api/` |
| `getting-started.md` | `examples/reference-service/justfile` |

The remaining six — `index.md`, `roadmap.md`, `contributing.md`, `glossary.md`, `explanation/why-a-template.md`, `guides/add-a-backend.md` — get `last_reviewed` only. None describes a specific file closely enough for path coupling to mean anything, and a `covers:` entry that fires on unrelated changes is worse than none: it teaches people to ignore the warning.

The frontmatter goes at the very top of the file, before the `# Title`:

```markdown
---
last_reviewed: 2026-09-10
covers:
  - examples/reference-service/src/reference_service/settings.py
---

# Configuration
```

- [ ] **Step 7: Verify the site still builds**

Run: `uv run mkdocs build --strict`
Expected: built, no warnings. Verified Fact 8 says MkDocs ignores both keys; this confirms it against all 20 pages rather than the one that was tested.

Also confirm the frontmatter is not rendering as visible text:

Run: `grep -c "last_reviewed" site/reference/configuration/index.html`
Expected: `0`.

- [ ] **Step 8: Run the script against real history**

Run: `uv run --group docs python scripts/check_docs_freshness.py HEAD~1 HEAD`
Expected: exit 0. Some `::warning` lines are fine and expected; what matters is that it does not crash and does not exit non-zero.

- [ ] **Step 9: Add the recipes**

In the root `justfile`:

```just
# The repository's own script tests.
test:
    uv run --group dev pytest tests/

# Documentation hygiene warnings for a pull request range. Never fails --
# see docs/contributing.md for why, and for what has to be true before
# these become hard failures.
docs-freshness base="origin/main" head="HEAD":
    uv run --group docs python scripts/check_docs_freshness.py {{base}} {{head}}
```

And extend `check`:

```just
# Everything CI checks at the repository level.
check: docs-build test
```

- [ ] **Step 10: Commit**

```bash
git add scripts/check_docs_freshness.py tests/test_check_docs_freshness.py \
        pyproject.toml justfile docs/
git commit -m "feat(docs): warn on unreviewed pages and uncovered code changes"
```

---

### Task 5: Dead external links

**Files:**
- Create: `lychee.toml`
- Modify: `justfile` (root)

**Interfaces:**
- Produces: `just links`, called by `ci.yml` (Task 15) and `nightly.yml` (Task 16).

**Why the configuration is not empty.** A link checker with default settings fails on things that are not broken: rate-limited hosts, the `edit_uri` URLs MkDocs generates for pages that exist only on a branch, and `localhost` URLs in examples that are correct instructions and unreachable from a runner.

- [ ] **Step 1: Write the configuration**

Create `lychee.toml` at the repository root:

```toml
# External link checking. Internal references are already covered by
# `mkdocs build --strict`, which fails on a dead cross-reference; this
# catches the other half -- links to things outside the repository, which
# rot without anyone here touching a file.

# Retry rather than fail on a slow or momentarily unhappy host. A link
# checker that reports false failures gets switched off within a month.
max_retries = 3
retry_wait_time = 2
timeout = 20

# Politeness, and self-preservation: too many parallel requests to one
# host is what earns a 429 in the first place.
max_concurrency = 8

# Some hosts refuse a request with no user agent, or with one they read as
# a scraper.
user_agent = "Mozilla/5.0 (compatible; lychee; +https://github.com/EmadMokhtar/pyfr)"

# 429 is rate limiting, not a dead link. Accepting it here is the
# difference between a check that means something and one people ignore.
accept = ["200..=299", "429"]

exclude = [
    # Examples telling a reader to open their own machine. Correct as
    # instructions, unreachable from a CI runner.
    "^https?://localhost",
    "^https?://127\\.0\\.0\\.1",
    "^https?://0\\.0\\.0\\.0",
    # Compose service names, which resolve only inside the compose network.
    "^https?://(minio|postgres|redis|payment-stub|otel-lgtm):",
    # MkDocs Material's own edit links point at paths on a branch, which
    # 404 for a page added in the same commit being checked.
    "^https://github\\.com/EmadMokhtar/pyfr/edit/",
    # Placeholder hosts in configuration examples.
    "example\\.com",
]

# Checked as text, not as a rendered site: the source is the thing under
# review, and site/ is a build artifact that may not exist.
exclude_path = ["site", ".venv", "examples/reference-service/.venv", "docs/superpowers"]
```

- [ ] **Step 2: Add the recipe**

In the root `justfile`:

```just
# Dead external links. Internal ones are already `mkdocs build --strict`'s
# job. Needs the lychee binary: `brew install lychee`, or run it in CI,
# where the action provides it.
links:
    lychee --config lychee.toml --no-progress 'docs/**/*.md' README.md
```

- [ ] **Step 3: Run it**

Run: `just links`

If `lychee` is not installed locally, this is expected — the check runs in CI regardless, and the recipe's comment says so. Install it (`brew install lychee`) to verify before committing, because a broken exclusion pattern is much easier to diagnose here than in a workflow log.

Expected: every link reachable, or a clear report of which are not. **Fix genuinely broken links now** rather than adding exclusions for them. An exclusion added to make a run green is how the check stops working.

- [ ] **Step 4: Commit**

```bash
git add lychee.toml justfile
git commit -m "build(docs): add external link checking with lychee"
```

---

### Task 6: Executable documentation examples

The check spec 10.3 describes as catching documentation that is *wrong*, not merely old. Kept deliberately narrow: the `curl` examples that a reader copies and runs, checked against a real running service.

**Files:**
- Create: `scripts/check_doc_examples.py`
- Modify: `docs/getting-started.md`, `docs/reference/http-api.md` (mark the runnable blocks)
- Modify: `examples/reference-service/justfile`

**Interfaces:**
- Produces: `just docs-examples`, run from `examples/reference-service/` because it needs that project's compose stack. Task 15 calls it.

**Why an opt-in marker rather than "run every bash block".** Most fenced blocks in the documentation are not runnable: they show a file's contents, a fragment of output, or a command that would modify the reader's machine. Running everything means either a wall of failures or a wall of exclusions. An explicit `<!-- exec -->` marker means each executable block was chosen, and the set stays small enough to be trustworthy.

- [ ] **Step 1: Write the script**

Create `scripts/check_doc_examples.py`:

```python
#!/usr/bin/env python3
"""Run the documentation's marked shell examples against a live service.

Spec 10.3 asks for a check that catches documentation that is WRONG rather
than merely old. A stale sentence is a nuisance; a `curl` example that
404s is a reader concluding the software is broken.

Opt-in by design. A block runs only when the line before its fence is
exactly `<!-- exec -->`. Most fenced blocks here are file contents,
fragments of output, or commands that would modify the reader's machine,
so "run everything" would mean a wall of exclusions -- and an exclusion
list is a place for a broken example to hide.

Stdlib only: it runs inside the reference service's environment via
`just docs-examples`, and adding a dependency to that project for a
documentation check would be the wrong trade.
"""

from __future__ import annotations

import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

MARKER = "<!-- exec -->"

# The marker, then a bash fence, then the body up to the closing fence.
_BLOCK = re.compile(
    rf"^{re.escape(MARKER)}\n```(?:bash|shell|console)\n(.*?)^```",
    re.MULTILINE | re.DOTALL,
)


@dataclass(frozen=True)
class Example:
    """One runnable block, with enough context to name it in a failure."""

    path: str
    line: int
    body: str


def find_examples(root: Path) -> list[Example]:
    """Every marked block under `root`, in file then document order."""
    examples: list[Example] = []
    for path in sorted(root.rglob("*.md")):
        # `superpowers` in parts, not a path prefix: `just docs-examples`
        # passes a RELATIVE root (`../../docs`) from the service directory,
        # so a prefix test would silently stop excluding the archive.
        if "superpowers" in path.parts:
            continue
        text = path.read_text(encoding="utf-8")
        for match in _BLOCK.finditer(text):
            examples.append(
                Example(
                    path=path.as_posix(),
                    line=text[: match.start()].count("\n") + 1,
                    body=match.group(1),
                )
            )
    return examples


def run(example: Example) -> tuple[bool, str]:
    """Run one block under `bash -euo pipefail`, capturing everything.

    `-e` matters more than it looks: without it a multi-command block
    reports the exit status of its LAST command only, so a broken `curl`
    followed by a working `echo` passes.
    """
    completed = subprocess.run(
        ["bash", "-euo", "pipefail", "-c", example.body],
        capture_output=True,
        text=True,
        timeout=60,
    )
    output = completed.stdout + completed.stderr
    return completed.returncode == 0, output


def main(argv: Sequence[str]) -> int:
    root = Path(argv[1]) if len(argv) > 1 else Path("docs")
    examples = find_examples(root)
    if not examples:
        sys.stderr.write(
            f"No `{MARKER}` blocks found under {root}. Either the marker "
            f"was renamed or the examples were removed; both are bugs.\n"
        )
        return 1

    failures = 0
    for example in examples:
        ok, output = run(example)
        location = f"{example.path}:{example.line}"
        if ok:
            print(f"  ok    {location}")
        else:
            failures += 1
            print(f"  FAIL  {location}")
            print("".join(f"        {line}\n" for line in output.splitlines()))

    print(f"\n{len(examples) - failures}/{len(examples)} examples passed")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
```

- [ ] **Step 2: Mark the runnable blocks**

In `docs/getting-started.md` and `docs/reference/http-api.md`, put `<!-- exec -->` on its own line immediately before the fence of each `curl` example that a reader is meant to run against a started service.

Mark these and nothing else:

- the health check (`curl .../healthz`)
- the readiness check (`curl .../readyz`)
- placing an order (`curl -X POST .../api/v1/orders`)
- fetching an order
- fetching a receipt
- a request that demonstrates a Problem Details error response

Two rules for a marked block. It must be **self-contained** — a block that reads `$ORDER_ID` from an earlier block fails on its own, so any block needing an identifier must create one first. And it must **assert**, not merely run: `curl -sf` fails on an HTTP error status, where a bare `curl` prints the error body and exits 0. Where a block needs to check a response body, pipe it:

```bash
curl -sf http://localhost:8000/healthz | grep -q '"status":"ok"'
```

Leave the surrounding prose showing example output exactly as it is. It is illustration, not a fence to run.

- [ ] **Step 3: Add the recipe**

In `examples/reference-service/justfile`, beside the other compose recipes:

```just
# Run the documentation's marked `curl` examples against a real service.
#
# A `#!`-shebang recipe with a trap, for the same reason `test-record` is
# one: the stack must come down whether the examples pass, fail, or the
# run is interrupted. The trap is armed BEFORE `up`, so a healthcheck
# timeout in `--wait` cannot leave the stack running.
docs-examples:
    #!/usr/bin/env bash
    set -euo pipefail
    trap 'docker compose down -v' EXIT
    docker compose up -d --wait
    python3 ../../scripts/check_doc_examples.py ../../docs
```

- [ ] **Step 4: Run it**

Run: `cd examples/reference-service && just docs-examples`
Expected: every marked example passes, and the summary line reports the count.

A failure here is the check doing its job. Fix the documentation, not the script — unless the failure is the example depending on state from a previous block, which is the script correctly refusing to paper over an example a reader cannot copy.

- [ ] **Step 5: Verify the script fails when an example is wrong**

A check nobody has watched fail is not known to work:

```bash
cd examples/reference-service
sed -i.bak 's|/healthz|/healthzzz|' ../../docs/getting-started.md
just docs-examples; echo "exit: $?"
mv ../../docs/getting-started.md.bak ../../docs/getting-started.md
```

Expected: a `FAIL` line naming `docs/getting-started.md` and its line number, and `exit: 1`.

- [ ] **Step 6: Commit**

```bash
git add scripts/check_doc_examples.py examples/reference-service/justfile \
        docs/getting-started.md docs/reference/http-api.md
git commit -m "test(docs): run the documented curl examples against a live service"
```

---

## Part C — Decision records and the runbook

### Task 7: The ADR mechanism, and the first two records

**Files:**
- Create: `docs/adr/README.md`, `docs/adr/template.md`
- Create: `docs/adr/0001-four-layer-dependency-rule.md`
- Create: `docs/adr/0002-cookiecutter-over-copier-and-cruft.md`
- Modify: `mkdocs.yml`

**Interfaces:**
- Produces: the `docs/adr/` tree and its nav section. Task 8 adds ten more records to it. `scripts/check_docs_freshness.py` already excludes the directory (Task 4, `EXCLUDED_PREFIXES`) — verify that rather than adding it again.

**Why these are being written now, four milestones late.** Every decision below is already recorded, in the design spec and the milestone plans — documents that run to 20,000 lines, are deliberately not published, and are written for whoever is building a milestone at that moment. A newcomer asking "why four layers?" should not have to mine a specification for the answer. The ADR is the published, one-page form.

**Each ADR points at the spec rather than restating it.** The spec is on GitHub and `roadmap.md` already links there; the ADR gives the decision, the alternatives and the consequences, and the link carries whoever wants the full argument.

- [ ] **Step 1: Write the template**

Create `docs/adr/template.md`:

```markdown
---
last_reviewed: 2026-09-10
---

# NNNN. Short title in the imperative

**Status:** Proposed | Accepted | Superseded by [NNNN](NNNN-….md)
**Date:** YYYY-MM-DD

## Context

What forced a decision. The constraints, the pressures, and what was true
at the time. Write this so it still makes sense to someone who arrives
after the situation has changed.

## Decision

What was decided, in the active voice: "We use X." One paragraph.

## Alternatives considered

What else was on the table, and the specific reason each was not chosen.
An ADR with no alternatives is a description, not a decision.

## Consequences

What this makes easy, what it makes hard, and what it commits us to.
Include the costs. An ADR that lists only benefits is advertising.
```

- [ ] **Step 2: Write the index**

Create `docs/adr/README.md`:

```markdown
---
last_reviewed: 2026-09-10
---

# Decision records

Each page here records one decision: what was decided, when, why, and what
it cost. They are short on purpose. The full reasoning lives in the
[design specification](https://github.com/EmadMokhtar/pyfr/tree/main/docs/superpowers),
and each record links to the section that argues its case.

Records 1 to 12 were written during M5 and describe decisions taken during
M0 to M4. They are backfilled, and dated to the milestone that made them
rather than to the day they were written down.

## Why they are never edited

An accepted record is history. It says what was decided on a date, given
what was known then. Changing your mind means writing a **new** record and
marking the old one superseded — never rewriting the old one, which
destroys the only account of why the software is the way it is.

For the same reason, records are exempt from the review-date warning that
covers every other page on this site. A decision does not go stale.

## Adding one

Copy [`template.md`](template.md), take the next number, and add it to the
nav in `mkdocs.yml`. Write it when the decision is made, while the
alternatives are still fresh — a record written six months later is a
reconstruction, and it shows.

## The records

| | Record | Decided |
|---|---|---|
| 0001 | [The four-layer dependency rule](0001-four-layer-dependency-rule.md) | M0 |
| 0002 | [cookiecutter over Copier and cruft](0002-cookiecutter-over-copier-and-cruft.md) | M0 |
```

Task 8 extends that table as it adds records. Keep it in numeric order.

- [ ] **Step 3: Write ADR 0001**

Create `docs/adr/0001-four-layer-dependency-rule.md`:

```markdown
---
last_reviewed: 2026-09-10
---

# 0001. Enforce a four-layer dependency rule

**Status:** Accepted
**Date:** 2026-08-28

## Context

A service accumulates coupling quietly. A domain object imports a FastAPI
type "just for a status code", a use case imports SQLAlchemy "just for a
session", and eighteen months later the business rules cannot be tested
without a database and an HTTP client.

Nothing about this is caught by a code review that is looking at one pull
request at a time, because each individual import is defensible.

## Decision

Four layers — `domain`, `services`, `api`, `infrastructure` — with
dependencies pointing inward only. `domain` imports nothing but Pydantic.
`services` imports `domain`. `api` and `infrastructure` may import both,
and never each other's internals.

The rule is enforced by `import-linter` in `.importlinter`, run by
`just imports` and by CI. It is a build failure, not a convention.

## Alternatives considered

- **A convention documented in a contributing guide.** Rejected: this is
  the arrangement that produced the problem. A rule that depends on
  everyone remembering it under deadline is not a rule.
- **Three layers, folding `api` and `infrastructure` together.** Rejected:
  they have genuinely different reasons to change — one follows the HTTP
  contract, the other follows whatever the database and the provider do —
  and merging them removes the boundary that keeps a driver detail out of
  a request handler.
- **A separate package per layer.** Rejected as premature. It buys the
  same enforcement `import-linter` already gives, at the cost of four
  build configurations and a versioning problem between them.

## Consequences

The domain layer is testable with no Docker, no network and no fixtures,
which is why `just test` runs in seconds and needs no daemon.

The cost is real and lands on newcomers. Placing a piece of code requires
knowing which layer owns it, and the answer is occasionally genuinely
unclear — mapping between a domain object and a response schema is the
recurring one. `just imports` fails the build rather than letting the
question be deferred, which is the point, but it is friction.

It also forces a mapping layer that a smaller service would not need:
`domain.Order` cannot be returned from a route, so an `api` schema and a
mapper exist for it. That is duplication, accepted deliberately, so that a
change to the HTTP contract cannot silently change the domain model.

Full reasoning: [spec section 4.3](https://github.com/EmadMokhtar/pyfr/blob/main/docs/superpowers/specs/2026-08-28-pyfr-cookiecutter-template-design.md).
```

- [ ] **Step 4: Write ADR 0002**

Create `docs/adr/0002-cookiecutter-over-copier-and-cruft.md`, following the same shape. The content, sourced from spec section 12's engine comparison table:

**Context.** PyFr generates services and must be able to send them later fixes. Three engines could do it: cookiecutter, Copier and cruft.

**Decision.** cookiecutter, with the update mechanism built on a git merge (M8) rather than on the engine.

**Alternatives considered.** *cruft* — purpose-built for exactly this and the least code to write, rejected because its last release was 2024-12-25, roughly twenty months before the decision, which is too dormant to carry a long-lived capability; it also applies patches rather than merging, so it fails on precisely the deleted example files every real project has. *Copier* — the healthiest of the three, with updates and cross-version migrations built in, rejected because Backstage's only Copier action is an unpublished third-party plugin last touched in February 2024, so portal self-service would mean owning forked TypeScript, whereas cookiecutter's Backstage module is first-party and actively released.

**Consequences.** Updates must be built rather than inherited — M8 exists because of this decision, and it is the largest cost. In exchange, generation is boring, widely understood, and works with the tooling teams already have. The `.pyfr-answers.yml` file M7 writes exists to make the M8 merge possible.

Link to the same spec, section 12.

- [ ] **Step 5: Add the nav section**

In `mkdocs.yml`, between Reference and Explanation:

```yaml
  - Decisions:
      - Overview: adr/README.md
      - 0001 Four-layer dependency rule: adr/0001-four-layer-dependency-rule.md
      - 0002 cookiecutter over Copier and cruft: adr/0002-cookiecutter-over-copier-and-cruft.md
```

Note `adr/template.md` is deliberately **not** in the nav. It is a file to copy, not a page to read, and `--strict` warns about a page in `docs/` that no nav entry references. Add it to `exclude_docs` beside `superpowers/`:

```yaml
exclude_docs: |
  superpowers/
  adr/template.md
```

- [ ] **Step 6: Verify the build**

Run: `uv run mkdocs build --strict`
Expected: built, no warnings. A missing nav entry or a broken relative link between records shows up here.

Confirm the exclusion of ADRs from the freshness check is real rather than assumed:

Run: `uv run --group docs python scripts/check_docs_freshness.py HEAD~1 HEAD | grep -c "docs/adr" || echo "0 (correct)"`
Expected: `0 (correct)`.

- [ ] **Step 7: Commit**

```bash
git add docs/adr/ mkdocs.yml
git commit -m "docs: add decision records with the first two backfilled"
```

---

### Task 8: The remaining ten records

**Files:**
- Create: ten files under `docs/adr/`
- Modify: `docs/adr/README.md` (the table), `mkdocs.yml` (the nav)

Each follows `template.md` exactly: frontmatter with `last_reviewed`, Status, Date, Context, Decision, Alternatives considered, Consequences, and a closing link to the spec section. Each is roughly a page. The Date is the milestone's date, not today's.

Below is what each record must contain. Write the prose; the decision, the alternatives and the costs are specified so nothing is invented.

- [ ] **Step 1: Write 0003 — uv over pip and Poetry**

**Date:** 2026-08-28. **Decision:** uv for dependency resolution, locking, virtual environments and running commands; `uv.lock` is committed; no `requirements.txt` anywhere. **Alternatives:** pip with `pip-tools` (rejected: separate tools for resolving, locking and running, and no dependency-group concept, so the split between service and documentation toolchains would be manual); Poetry (rejected: slower resolution and its own non-standard `pyproject.toml` sections, where uv uses PEP 621 metadata that other tools can read). **Consequences:** one tool, and resolution fast enough that CI can afford `uv sync` in every job. The cost is a young tool at the centre of the build; `pip-audit` is the one place a pip-named tool still appears (spec D2), and it runs through `uvx` without reintroducing pip as a package manager.

- [ ] **Step 2: Write 0004 — golang-migrate owns the schema**

**Date:** 2026-09-01. **Decision:** golang-migrate with plain `.up.sql` / `.down.sql` files. No `alembic/` directory and no `alembic_version` table. **Alternatives:** Alembic (rejected: autogeneration produces migrations nobody reads, and its Python runtime means the migration step needs the application's dependency tree — golang-migrate is one static binary in its own small image); hand-run SQL (rejected: no version tracking, no reversibility, no way to gate). **Consequences:** migrations are reviewable SQL, and the migration image is small and independent of the application image. Alembic remains an installed *dev* dependency for exactly one job — `compare_metadata()` powers the model/schema drift gate — and `pyproject.toml` says so where it is declared. The dirty-migration failure mode is real and is why the runbook has an entry for it.

- [ ] **Step 3: Write 0005 — in-memory adapters are a supported configuration**

**Date:** 2026-08-28. **Decision:** every optional dependency's absence selects an in-memory adapter, and the service runs normally. `APP_DATABASE__DSN` unset means an in-memory repository, not a startup failure. Same for payment, cache and storage. **Alternatives:** requiring every dependency (rejected: `just dev` would need four containers to serve one request, and a walking skeleton with no database is a real product — an aggregator, a webhook receiver); test-only fakes (rejected: a fake that is not a supported production path is a fake that drifts from the adapter it stands in for). **Consequences:** the service starts with no infrastructure at all, which makes the first five minutes work and keeps unit tests container-free. The cost is two code paths per port, both of which must keep behaving identically, and the risk that someone ships to production with the in-memory repository by leaving a variable unset — which is why the startup log states which adapter was selected.

- [ ] **Step 4: Write 0006 — the cache is fail-open, always**

**Date:** 2026-09-10. **Decision:** every Redis failure — connection, timeout, malformed payload — is logged and swallowed, and the wrapped repository answers. There is no configuration flag that makes a cache miss fatal. **Alternatives:** fail-closed (rejected: it converts a latency degradation the service is built to survive into a total outage); a configurable mode (rejected: the failing mode would be selected by someone who had not thought about it, and a flag whose wrong setting takes production down is not a feature). **Consequences:** a Redis outage costs latency, not availability, and `/readyz` reports the cache without gating on it. The cost is that a persistently broken cache is *quiet* — the service keeps serving while every read misses — so the cache hit rate is a dashboard panel and an alert rather than something a health check would catch.

- [ ] **Step 5: Write 0007 — emit OpenTelemetry and stop**

**Date:** 2026-09-02. **Decision:** the service emits standard OTLP traces, metrics and optionally logs, and bundles no observability platform. The Grafana stack in compose is a local development convenience behind a profile, never a deployment target. **Alternatives:** bundling a platform (rejected: teams already have one, and a second is not a gift); vendor-specific SDKs (rejected: it makes the telemetry unportable, which is the one thing OpenTelemetry exists to prevent). **Consequences:** the telemetry works with whatever the team already runs, and telemetry is off by default so a service wanting none of it pays nothing — no exporter imported, no socket opened, no background task started. The cost is that PyFr cannot promise a working dashboard out of the box beyond the local stack.

- [ ] **Step 6: Write 0008 — standard output is the source of truth for logs**

**Date:** 2026-09-02. **Decision:** logs go to standard output as one JSON object per line. OTLP log export is available and off by default, and is explicitly *in addition to* stdout, never instead of it. **Alternatives:** OTLP-only (rejected: it loses exactly the output you need when a service will not start — crashes, and anything failing before the SDK initialises — and it disappears entirely during a collector outage); files (rejected: a container writing log files is a disk-space incident waiting to happen). **Consequences:** logs survive a collector outage and capture startup failures. The cost is that turning OTLP export on in production alongside a platform log agent ingests every line twice, doubling volume and the bill — which is why the setting's description says so and the default is false.

- [ ] **Step 7: Write 0009 — RFC 9457 Problem Details for every error**

**Date:** 2026-08-28. **Decision:** every error response is `application/problem+json` per RFC 9457, including validation failures, which are translated from FastAPI's default shape. **Alternatives:** FastAPI's default `{"detail": …}` (rejected: it is undocumented as a contract, and varies in shape between a validation error and a raised `HTTPException`); a bespoke error envelope (rejected: a standard with a registry and existing client support beats a local invention). **Consequences:** clients can rely on one error shape, and `type` gives errors stable identifiers that survive message rewording. The cost is a translation layer over FastAPI's built-in handlers, and the discipline that the domain layer never knows an HTTP status code exists — the mapping lives in `api/errors.py`.

- [ ] **Step 8: Write 0010 — the OpenAPI document is committed and drift-gated**

**Date:** 2026-09-09. **Decision:** `openapi.json` is generated from the code, committed, and a gate fails the build when the committed copy differs from what the code produces. A second committed copy, `openapi.baseline.json`, is the last released contract, and `oasdiff` compares against it. **Alternatives:** generating it at build time only (rejected: an API change then has no diff to review — the contract changes invisibly inside a pull request that looks like a refactor); writing it by hand (rejected: it drifts from the code immediately). **Consequences:** every API change appears in a reviewable diff, and breaking changes are detected rather than discovered by a client. The cost is a regeneration step (`just openapi`) that people forget, which the drift gate then catches loudly.

- [ ] **Step 9: Write 0011 — `/readyz` reports optional dependencies without gating on them**

**Date:** 2026-09-10. **Decision:** readiness has two tiers. The database gates: if it is unreachable the endpoint returns 503 and the instance leaves load balancing. The cache and the object store are reported in the body and never affect the status code. **Alternatives:** gating on everything (rejected: a shared Redis makes every instance unready at once, converting a survivable degradation into a total outage); reporting nothing (rejected: an operator cannot then tell a healthy instance from one silently missing every cache read). **Consequences:** an optional dependency's outage is visible without being fatal. The cost is that "ready" now means something more specific than it appears to, so the endpoint's own documentation has to state which dependencies gate — a subtlety that is easy to miss when adding the next dependency.

- [ ] **Step 10: Write 0012 — mypy is strict on the inner layers only**

**Date:** 2026-08-28. **Decision:** `mypy --strict` on `domain/` and `services/`; lenient elsewhere. **Alternatives:** strict everywhere (rejected: third-party stubs in the infrastructure layer are imperfect, and the result is a codebase of `# type: ignore` comments, which is worse than lenient checking because it looks rigorous); lenient everywhere (rejected: the inner layers are where types encode business rules, and that is exactly where strictness pays). **Consequences:** type errors are caught where they carry meaning, without a stub-quality argument in every adapter. The cost is an uneven rule that has to be explained, and a boundary that must be maintained in `pyproject.toml` as the tree grows.

- [ ] **Step 11: Update the index and the nav**

Extend the table in `docs/adr/README.md` to all twelve rows, in numeric order, and add the ten nav entries to `mkdocs.yml` in the same order and the same `NNNN Title` format Task 7 established.

- [ ] **Step 12: Verify the build**

Run: `uv run mkdocs build --strict`
Expected: built, no warnings. Twelve records, twelve nav entries, no orphan pages.

Then check nothing was left as a stub:

Run: `grep -rn "TODO\|TBD\|Alternatives considered\s*$" docs/adr/ | grep -v template.md`
Expected: no output. An ADR with an empty Alternatives section is a description, not a decision.

- [ ] **Step 13: Commit**

```bash
git add docs/adr/ mkdocs.yml
git commit -m "docs: backfill the remaining ten decision records"
```

---

### Task 9: The on-call runbook

**Files:**
- Create: `docs/runbook.md`
- Modify: `mkdocs.yml`
- Modify: `docs/guides/outbound-http.md` (two forward references, lines 191 and 227)

**Interfaces:**
- Produces: `docs/runbook.md` with four anchored procedures. `outbound-http.md` links to `#a-dependency-is-down`.

**Written for someone under pressure at an hour they did not choose.** Every procedure follows the same four headings — Symptom, Confirm, Act, Do not — and every command is copy-pasteable. No prose paragraph explains background before saying what to do; the background goes after, or in an ADR.

Spec 6.4 also asks for a separate dirty-migration how-to guide. It is deliberately not being written — see "What M5 deliberately does not include". This page is where that procedure lives.

- [ ] **Step 1: Write the page**

Create `docs/runbook.md`. Frontmatter, then an orienting header, then four procedures:

```markdown
---
last_reviewed: 2026-09-10
covers:
  - examples/reference-service/ops/prometheus/rules/
  - examples/reference-service/justfile
---

# Runbook

Four procedures, for four things that go wrong. Each says what you will
see, how to confirm it, and what to do.

**Before anything else:** capture the correlation identifier from the
failing request. Every log line and every span carries it, and it turns
"the API is slow" into a single traceable request.
```

Then the four sections, with these exact anchors and contents:

**`## A migration is dirty`** — Symptom: the `migrate` container exits non-zero, and deployment stops. Confirm with `just migrate-version`, which prints the version and a dirty flag. Act: read the failed migration's SQL and determine whether it partially applied; if it did not, `just migrate-force <previous-version>` then re-run `just migrate`; if it did, the forward fix is a new migration, never an edit to the applied one. Do not: edit a migration that has run anywhere, and do not force a version without first establishing what actually reached the database. Point at ADR 0004 for why golang-migrate, and note that `migrate-force` sets the version without running anything — it is a claim about the state of the schema, and a wrong claim is worse than the dirty flag.

**`## A dependency is down`** — Symptom differs by dependency, which is the point of the section. Give a table: PostgreSQL → `/readyz` returns 503 and the instance leaves load balancing (it is the only gating dependency, ADR 0011); Redis → requests still succeed, cache hit rate falls to zero, latency rises (ADR 0006 — this is by design); S3 or MinIO → only `GET /orders/{id}/receipt` fails, and no order-placing request is affected; the payment gateway → the circuit breaker opens after the configured consecutive failures and order placement fails fast rather than hanging. Confirm: `curl -s localhost:8000/readyz | jq` shows every dependency's status including the non-gating ones. Act, per dependency. Do not: restart instances because Redis is down — they are healthy, and a rolling restart during a cache outage adds a cold-start stampede to an incident that was survivable.

**`## A burn-rate alert is firing`** — Symptom: one of the SLO alerts in `ops/prometheus/rules/slo.yml` fires. Explain what a burn rate is in one sentence (the rate at which the error budget is being consumed, relative to the rate that would exhaust it exactly at the period's end), then: a fast-burn alert means budget will be gone in hours and wants a response now; a slow-burn alert means a degradation that will exhaust the budget over days and wants a ticket. Confirm: the Grafana dashboards, named as they are in `ops/grafana/dashboards/`. Act: identify whether the errors are concentrated in one endpoint or one dependency, using the correlation identifier from a failing request. Do not: silence the alert without an owner and a deadline.

**`## Rolling back`** — Symptom: a release is bad and forward-fixing is slower than reverting. Act, in this order and no other: **first** establish whether the release included a migration — `just migrate-version` against the environment, compared against the previous release's expected version. If it did not, roll the application image back and stop. If it did, roll the application back only if the previous version can run against the *current* schema; a migration that dropped a column the previous release reads means the rollback is itself a schema change, and `migrate-down` is the tool, with the same care the dirty-migration section describes. Do not: roll an image back without checking for a migration first. This is the mistake that turns a bad release into an outage, and it is the reason the check is the first step rather than a caveat at the end.

- [ ] **Step 2: Add it to the nav**

In `mkdocs.yml`, as a top-level entry after Getting started — not buried under Project, because it is read under time pressure:

```yaml
  - Runbook: runbook.md
```

- [ ] **Step 3: Resolve the two forward references**

`docs/guides/outbound-http.md:191` currently says the gate that fails the build when a cassette changes is M5 work. Rewrite it to describe what now exists — Task 11's contract gate — or, if it refers to the weekly re-record job, state plainly that it was decided against and why (the recorded upstream is a local stub), matching the reasoning in "What M5 deliberately does not include".

`docs/guides/outbound-http.md:227` says "There is no on-call runbook yet to link this from — that is M5's". Replace it with a link to [the runbook's dependency section](../runbook.md#a-dependency-is-down).

- [ ] **Step 4: Verify the build and the anchors**

Run: `uv run mkdocs build --strict`
Expected: built, no warnings. `mkdocs.yml` sets `validation.anchors: warn`, and `--strict` turns that into a failure — so a mistyped `#a-dependency-is-down` fails here rather than shipping as a dead link.

- [ ] **Step 5: Commit**

```bash
git add docs/runbook.md mkdocs.yml docs/guides/outbound-http.md
git commit -m "docs: add the on-call runbook"
```

---

## Part D — Versioning and release

### Task 10: Commitizen and the initial changelog

**Files:**
- Modify: `pyproject.toml` (root)
- Create: `CHANGELOG.md` (root, generated)
- Modify: `justfile` (root)

**Interfaces:**
- Produces: `[tool.commitizen]` at the repository root, a `CHANGELOG.md` covering all history, and `just changelog`. Task 12's workflow runs `cz bump` against this configuration.

**Two facts that determine the configuration, both verified from Commitizen 4.18.0's own source:**

`version_provider = "uv"` rather than `"pep621"`. `uv.lock:379` pins `version = "0.0.0"` for this virtual project. The `pep621` provider writes `pyproject.toml` only, leaving the lock file stale — which the `uv-lock` pre-commit hook then fails on, in the release workflow, after the tag has been created. `UvProvider.set_version` writes both, matching the package by canonicalised project name.

`cz bump` commits with `git commit -a`. `Bump._get_commit_args` returns `["-a"]`, so the bump commit picks up **every tracked modification in the tree**, not just the files Commitizen wrote. The release job must therefore run on a clean checkout and must not write anything into the working tree before the bump. Task 12 states this in a comment where it matters.

- [ ] **Step 1: Configure Commitizen**

In the root `pyproject.toml`, set the version and add the section:

```toml
[project]
name = "pyfr"
version = "0.5.0"
```

```toml
[tool.commitizen]
name = "cz_conventional_commits"
# Writes BOTH pyproject.toml's [project].version and uv.lock's matching
# [[package]] entry. `pep621` writes only the first, which leaves the lock
# file stale and fails the uv-lock hook -- inside the release workflow,
# after the tag has already been pushed.
version_provider = "uv"
tag_format = "v$version"
update_changelog_on_bump = true
changelog_file = "CHANGELOG.md"
# Pre-1.0: a breaking change bumps the MINOR number (0.5.0 -> 0.6.0)
# rather than jumping to 1.0.0. Semver puts no compatibility promise on
# the major number below 1.0.0, and 1.0.0 should be a deliberate decision
# about stability, not a side effect of the first `feat!:`.
major_version_zero = true
```

**Why 0.5.0 and not a computed bump.** There are no tags (Verified Fact 10), so `cz bump` has no base and would either refuse or bump from `0.0.0` through the whole history at once. `0.5.0` states plainly that five milestones are done. From the next release onward Commitizen computes the number itself.

- [ ] **Step 2: Generate the changelog**

Run: `uvx --from commitizen==4.18.0 cz changelog --unreleased-version v0.5.0`
Expected: `CHANGELOG.md` written, grouped into Feat and Fix, covering every commit back to the first.

- [ ] **Step 3: Read it, and change nothing**

Run: `head -40 CHANGELOG.md`

You will see `add the m0 walking skeleton reference service` **twice**. Two commits carry that message; the changelog is reporting the history accurately (Verified Fact 7). **Leave it.** Editing generated output so it reads more tidily is how a changelog stops being a record and becomes a story.

Add a header above the generated content explaining what the file is:

```markdown
# Changelog

Generated by [Commitizen](https://commitizen-tools.github.io/commitizen/)
from Conventional Commit messages. Never edited by hand — a change here
comes from a commit message, and `just release` rewrites this file.

Versions before v0.5.0 were never tagged: v0.5.0 is the first release, and
the entries below it are the history that produced it.
```

- [ ] **Step 4: Add the recipes**

In the root `justfile`:

```just
# Preview the changelog entry the next release will write. Read-only.
changelog:
    uvx --from commitizen==4.18.0 cz changelog --dry-run --incremental

# Preview the version the next release will choose, without doing it.
# The release itself runs in CI (.github/workflows/release.yml); this is
# for answering "what will merging this produce?" before merging.
next-version:
    uvx --from commitizen==4.18.0 cz bump --dry-run
```

- [ ] **Step 5: Verify the version is readable and the lock file agrees**

```bash
uvx --from commitizen==4.18.0 cz version --project
uv lock --check
```

Expected: `0.5.0`, and the lock check passes. If `uv lock --check` fails, the version in `uv.lock` was not updated — run `uv lock` and confirm the only change is that one line.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock CHANGELOG.md justfile
git commit -m "build: add commitizen and generate the initial changelog"
```

---

### Task 11: The Conventional Commits range check

Replaces the version comparison in `check_contract_compatibility.py` with the check spec 10.2 actually describes. The script's own docstring asks for this (Verified Fact 14).

**Files:**
- Modify: `examples/reference-service/scripts/check_contract_compatibility.py`
- Create: `examples/reference-service/tests/unit/test_contract_commit_check.py`
- Modify: `docs/reference/contract.md` (the "What M5 replaces here" section)

**Interfaces:**
- Consumes: `git log` over a commit range.
- Produces: `range_is_marked_breaking(base, head) -> bool` and a `main()` that reads `--base` / `--head`. `breaking_changes()` and the oasdiff half are unchanged.

**What changes and why.** Before M5 the script compared `info.version` in the committed contract against the baseline's, because tags and Commitizen did not exist. Now the repository is versioned by Commitizen from commit messages, and the contract belongs to the reference service, which is not versioned at all — so the version comparison compares a number nobody bumps. The question spec 10.2 actually asks is: *did the person who broke the API say they were breaking it?* That is a property of the commit range, not of a version field.

- [ ] **Step 1: Write the failing test**

Create `examples/reference-service/tests/unit/test_contract_commit_check.py`:

```python
"""The Conventional Commits half of the contract gate.

Spec 10.2: if oasdiff reports a breaking change and no commit in the range
is marked breaking, the build fails. These tests cover the parsing, which
is where this goes wrong -- oasdiff's half is already tested by its own
exit-code handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_contract_compatibility import message_is_breaking  # noqa: E402


def test_exclamation_after_the_type_is_breaking() -> None:
    assert message_is_breaking("feat!: drop the legacy field") is True


def test_exclamation_after_a_scope_is_breaking() -> None:
    assert message_is_breaking("feat(api)!: drop the legacy field") is True


def test_breaking_change_footer_is_breaking() -> None:
    message = (
        "feat(api): replace the status field\n"
        "\n"
        "BREAKING CHANGE: `status` is now an enum rather than a string.\n"
    )
    assert message_is_breaking(message) is True


def test_hyphenated_footer_is_breaking() -> None:
    """The specification allows BREAKING-CHANGE as a synonym."""
    message = "fix(api): tighten validation\n\nBREAKING-CHANGE: rejects empty.\n"
    assert message_is_breaking(message) is True


def test_an_ordinary_commit_is_not_breaking() -> None:
    assert message_is_breaking("fix(api): correct a typo in a description") is False


def test_the_words_in_prose_are_not_a_footer() -> None:
    """A footer is a line that STARTS with the token.

    Without this, a commit body explaining that a change is deliberately
    not a breaking change marks itself as one -- and the gate then passes
    for the next genuinely breaking change that mentions it in passing.
    """
    message = (
        "fix(api): widen an enum\n"
        "\n"
        "This is not a BREAKING CHANGE: widening accepts strictly more.\n"
    )
    assert message_is_breaking(message) is False


def test_an_exclamation_in_the_description_is_not_a_marker() -> None:
    assert message_is_breaking("fix: stop the parser exploding!") is False
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_contract_commit_check.py -q`
Expected: `ImportError: cannot import name 'message_is_breaking'`.

- [ ] **Step 3: Replace the version half**

In `check_contract_compatibility.py`, **delete** `class Version`, `bump_is_sufficient`, `read_version` and `_render`, and replace the module docstring and `main()`. Keep `OASDIFF_IMAGE`, `BREAKING_LEVEL`, `BASELINE`, `CURRENT` and `breaking_changes()` exactly as they are.

New docstring:

```python
"""Fail the build when a breaking API change ships unannounced.

`oasdiff` says whether the API broke. The commit messages say whether
anyone meant to break it. These can disagree -- someone removes a response
field and writes `fix:` -- and when they do, a client pinned to a
compatible range breaks in production. This is the gate that stops it
(spec 10.2).

Before M5 the second half of this compared `info.version` between the
committed contract and the baseline. That check is gone: the repository is
now versioned by Commitizen from commit messages, and the reference
service's own version is a fixed 0.1.0 that nobody bumps, so the
comparison was reading a number with no meaning. The question is now asked
of the commits directly, which is what spec 10.2 describes.
"""
```

Add the parsing and the new `main`:

```python
import argparse
import re

# A Conventional Commits subject marks a breaking change with `!` before
# the colon: `feat!:` or `feat(api)!:`. The `!` must be immediately before
# the colon -- an exclamation mark inside the description is prose.
_BREAKING_SUBJECT = re.compile(r"^[a-z]+(\([^)]*\))?!:")

# A footer marks it with a token at the START of a line. Matching anywhere
# would let a body explaining that something is NOT a breaking change mark
# itself as one, which quietly disarms the gate for the next real break.
_BREAKING_FOOTER = re.compile(r"^BREAKING[ -]CHANGE:", re.MULTILINE)


def message_is_breaking(message: str) -> bool:
    """Does this commit message declare a breaking change?"""
    subject = message.splitlines()[0] if message else ""
    return bool(_BREAKING_SUBJECT.match(subject) or _BREAKING_FOOTER.search(message))


def range_is_marked_breaking(base: str, head: str) -> bool:
    """Is any commit in `base..head` marked as breaking?

    NUL-separated, not newline-separated: a commit body contains newlines,
    so splitting on them would treat every paragraph as its own commit --
    which happens to make the gate MORE permissive, and is therefore the
    kind of bug that never announces itself.
    """
    completed = subprocess.run(
        ["git", "log", "--format=%B%x00", f"{base}..{head}"],
        capture_output=True,
        text=True,
        check=True,
    )
    return any(
        message_is_breaking(message.strip())
        for message in completed.stdout.split("\0")
        if message.strip()
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="origin/main")
    parser.add_argument("--head", default="HEAD")
    arguments = parser.parse_args()

    findings = breaking_changes(BASELINE, CURRENT)
    if not findings:
        print("No breaking API changes against the committed baseline.")
        return 0

    if range_is_marked_breaking(arguments.base, arguments.head):
        print(
            f"{len(findings)} breaking change(s), and a commit in "
            f"{arguments.base}..{arguments.head} is marked breaking. Allowed."
        )
        return 0

    print(
        f"BREAKING API CHANGE with no commit marked breaking in "
        f"{arguments.base}..{arguments.head}.\n",
        file=sys.stderr,
    )
    for finding in findings:
        print(
            f"  [{finding['id']}] {finding['operation']} {finding['path']}\n"
            f"      {finding['text']}",
            file=sys.stderr,
        )
    print(
        "\nEither undo the change, or mark the commit breaking -- `feat!:` "
        "in the subject, or a `BREAKING CHANGE:` footer. Marking it is a "
        "statement that clients will need to act, so mean it.",
        file=sys.stderr,
    )
    return 1
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `cd examples/reference-service && uv run pytest tests/unit/test_contract_commit_check.py -q`
Expected: PASS, 7 tests.

- [ ] **Step 5: Run the whole gate**

Run: `cd examples/reference-service && just contract-gates`
Expected: `No breaking API changes against the committed baseline.` (needs Docker for the oasdiff image).

- [ ] **Step 6: Update the contract reference page**

`docs/reference/contract.md:146` has a section headed "What M5 replaces here". Rewrite it to describe what now exists rather than what is coming: the gate reads the commit range, `feat!:` or a `BREAKING CHANGE:` footer is how you declare an intentional break, and `just contract-release` promotes the current contract to the baseline as part of cutting a release — never to silence the gate.

Remove the forward-looking framing entirely. A page describing a future that has arrived is worse than one that never mentioned it.

- [ ] **Step 7: Commit**

```bash
git add examples/reference-service/scripts/check_contract_compatibility.py \
        examples/reference-service/tests/unit/test_contract_commit_check.py \
        docs/reference/contract.md
git commit -m "feat(reference-service): gate breaking api changes on commit markers"
```

---

### Task 12: The release workflow

**Files:**
- Create: `.github/workflows/release.yml`
- Modify: `docs/contributing.md` (one-time repository settings)

**Interfaces:**
- Consumes: `[tool.commitizen]` from Task 10.
- Produces: a tag, a bump commit, and a GitHub Release, on every push to `main` that contains a releasable change.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/release.yml`:

```yaml
name: Release

# Releases the REPOSITORY, not the reference service. One version, one
# CHANGELOG.md, one tag series -- see the M5 plan's Global Constraints.
# The reference service is an example nobody deploys; it stays at 0.1.0
# and publishes nothing. Image publishing arrives in M6.

on:
  push:
    branches: [main]
  # Allows cutting a release without a code change.
  workflow_dispatch:

permissions:
  contents: write

# Never two releases at once: they would race for the same tag, and the
# loser pushes a commit whose version was already taken. Not cancelling
# in-flight runs, because a cancelled release can leave a tag with no
# GitHub Release attached.
concurrency:
  group: release
  cancel-in-progress: false

jobs:
  release:
    # Commitizen's own bump commit is a push to main, so without this the
    # workflow triggers itself forever. `cz bump`'s message begins with
    # `bump:` by default.
    if: "!startsWith(github.event.head_commit.message, 'bump:')"
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          # cz reads every commit since the last tag, and needs the tags
          # themselves to know where that is.
          fetch-depth: 0
          # A push made with the default GITHUB_TOKEN does not trigger
          # other workflows. That is correct here -- ci.yml and docs.yml
          # already ran on the merge commit this release is built from --
          # but it looks like a broken trigger to whoever investigates
          # later, so: it is deliberate, and it is GitHub's loop
          # protection, not a misconfiguration.
          token: ${{ secrets.GITHUB_TOKEN }}

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Identify the committer
        # The bump commit needs an author. Using the Actions bot rather
        # than impersonating whoever merged: the commit is made by
        # automation and should say so.
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "41898282+github-actions[bot]@users.noreply.github.com"

      - name: Bump the version and write the changelog
        id: bump
        # Pinned to the version .pre-commit-config.yaml pins, so the tool
        # deciding the version here is the tool that validated the commit
        # messages it reads.
        #
        # `cz bump` commits with `git commit -a`, which stages every
        # tracked modification in the tree -- so nothing may write into
        # the working tree before this step. There is deliberately no
        # `uv sync` above for that reason.
        #
        # Exit 21 is NO_COMMITS_FOUND: nothing releasable since the last
        # tag, which is an ordinary outcome for a docs-only merge, not a
        # failure.
        run: |
          set +e
          uvx --from commitizen==4.18.0 cz bump --yes --changelog
          status=$?
          set -e
          if [ "$status" -eq 21 ]; then
            echo "released=false" >> "$GITHUB_OUTPUT"
            echo "No releasable commits since the last tag."
            exit 0
          fi
          if [ "$status" -ne 0 ]; then
            exit "$status"
          fi
          echo "released=true" >> "$GITHUB_OUTPUT"
          echo "version=$(uvx --from commitizen==4.18.0 cz version --project)" \
            >> "$GITHUB_OUTPUT"

      - name: Push the bump commit and its tag
        if: steps.bump.outputs.released == 'true'
        run: git push --follow-tags origin main

      - name: Publish the GitHub Release
        if: steps.bump.outputs.released == 'true'
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          VERSION: ${{ steps.bump.outputs.version }}
        # --notes-from-tag would use the tag message; the changelog entry
        # this release just generated is better prose, and `cz changelog`
        # can print exactly that one version's section.
        run: |
          uvx --from commitizen==4.18.0 cz changelog "v${VERSION}" \
            --dry-run > release-notes.md
          gh release create "v${VERSION}" \
            --title "v${VERSION}" \
            --notes-file release-notes.md
```

- [ ] **Step 2: Check the workflow parses**

Run: `uv run --group docs python -c "import yaml,sys; yaml.safe_load(open('.github/workflows/release.yml')); print('valid yaml')"`
Expected: `valid yaml`.

The `if:` expression is the part most likely to be subtly wrong. Note the quoting: `if: "!startsWith(...)"` needs the surrounding quotes because a bare `!` starts a YAML tag.

- [ ] **Step 3: Document the one-time settings**

`docs/contributing.md` already has a "One-time repository settings" section for GitHub Pages. Add two more, both of which fail confusingly rather than loudly:

1. **Workflow write permission.** Settings → Actions → General → Workflow permissions → "Read and write permissions". Without it the push in the release job fails with a 403 *after* `cz bump` has already created the commit and tag locally.

2. **Branch protection and the release push.** If `main` is protected, the default `GITHUB_TOKEN` cannot push to it, and every release fails at the push step. Either exempt the `github-actions[bot]` actor in the protection rule, or replace `secrets.GITHUB_TOKEN` in the checkout step with a personal access token or a GitHub App token that is exempt. State plainly that the token in the checkout step is the one that matters — replacing only the one in the `gh release create` step changes nothing, because it is the `actions/checkout` token that git push uses.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/release.yml docs/contributing.md
git commit -m "ci: release the repository with commitizen on every merge"
```

---

## Part E — Continuous integration

### Task 13: The service's fast gates

The reference service has never run in CI. This task adds the jobs that need no Docker.

**Files:**
- Modify: `.github/workflows/ci.yml`

**Interfaces:**
- Produces: a `check` job. Tasks 14 and 15 add jobs beside it in the same file.

**Every job calls a `just` recipe and nothing else.** A job that inlines `uv run ruff check .` creates a second definition of what linting means, and the two drift. See the Global Constraint.

- [ ] **Step 1: Add the job**

In `.github/workflows/ci.yml`, add to `jobs:` alongside the existing `docs` and `docs-freshness`:

```yaml
  check:
    # `just check` is lint, typecheck, imports, unit tests and pre-commit,
    # then `git diff --exit-code` to catch a hook that mutated the tree.
    # One job rather than five: they share an install, they all finish in
    # a couple of minutes, and splitting them would mean five copies of
    # the setup for a failure message that already names which gate broke.
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: examples/reference-service
    steps:
      - uses: actions/checkout@v4
        with:
          # `just precommit` runs pre-commit over `git ls-files`, and the
          # commitizen hook checks commit messages in the range -- both
          # need real history, not a shallow clone.
          fetch-depth: 0

      - name: Install uv
        uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true

      - name: Install just
        uses: extractions/setup-just@v2

      - name: Install the project
        run: uv sync

      - name: Run every fast gate
        run: just check
```

- [ ] **Step 2: Add concurrency to the workflow**

At the top of `ci.yml`, below `on:`, so a force-push does not leave a stale run burning a runner:

```yaml
# One run per branch. Cancelling in-flight runs is safe here in a way it
# is not for release.yml or docs.yml: nothing is published, so a cancelled
# run leaves nothing half-done.
concurrency:
  group: ci-${{ github.ref }}
  cancel-in-progress: true
```

- [ ] **Step 3: Verify the recipe works from a clean checkout**

The CI job's environment differs from a developer's in one way that matters — no `.venv`, no caches. Reproduce it:

```bash
cd examples/reference-service
git stash push -u -m "m5-ci-clean-check"
uv sync
just check
git stash list --format='%H %gs' | head -3
```

Expected: `just check` passes. Restore your work with `git stash apply <sha>` using the SHA for the `m5-ci-clean-check` entry, then drop that entry — never a bare `git stash pop`, because this is a worktree and the stash stack is shared.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run the reference service's fast gates"
```

---

### Task 14: The container gates

Four jobs that need a Docker daemon. `ubuntu-latest` provides one, and testcontainers manages its own containers — no `services:` block is needed or wanted.

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add the four jobs**

```yaml
  integration:
    # testcontainers starts PostgreSQL, Redis and MinIO itself. Deliberately
    # NOT a `services:` block: the containers are pinned in the test code,
    # so the versions CI runs against are the versions a developer runs
    # against, and there is one place to change them.
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: examples/reference-service
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - uses: extractions/setup-just@v2
      - run: uv sync
      - run: just test-integration

  gates:
    # Migration files, the schema snapshot, model/schema drift, and the
    # generated configuration reference. Needs Docker for the schema
    # gates, which run against a real PostgreSQL.
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: examples/reference-service
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - uses: extractions/setup-just@v2
      - run: uv sync
      - run: just gates

  contract:
    # OpenAPI drift, schemathesis conformance, and the oasdiff plus
    # commit-marker cross-check. `fetch-depth: 0` because that last one
    # reads the commit range -- with a shallow clone `git log base..head`
    # is empty, which reads as "nobody marked it breaking" and fails every
    # legitimate breaking change.
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: examples/reference-service
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - uses: extractions/setup-just@v2
      - run: uv sync
      - run: just contract-gates

  o11y-gates:
    # promtool over the SLO rules, out of the pinned otel-lgtm image. No
    # uv sync: it runs no Python at all.
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: examples/reference-service
    steps:
      - uses: actions/checkout@v4
      - uses: extractions/setup-just@v2
      - run: just o11y-gates
```

- [ ] **Step 2: Confirm the contract gate's base reference resolves**

`just contract-gates` calls the script with its default `--base origin/main`. On a pull request runner, `origin/main` exists after a `fetch-depth: 0` checkout. On a push **to** main it also exists, and `origin/main..HEAD` is empty — which correctly means "no commit in this range is marked breaking", and is only reached at all if oasdiff found a break that the pull request's own run already passed or failed on.

Verify locally, from a branch:

```bash
cd examples/reference-service
uv run python scripts/check_contract_compatibility.py --base origin/main --head HEAD
```

Expected: exit 0 with the "No breaking API changes" line.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: run the integration, schema, contract and slo gates"
```

---

### Task 15: The documentation jobs and the image build

**Files:**
- Modify: `.github/workflows/ci.yml`

- [ ] **Step 1: Add the three remaining jobs**

```yaml
  docs-warnings:
    # Advisory only -- review dates and path coupling. Never fails; see
    # docs/contributing.md for what has to be true before it does.
    if: github.event_name == 'pull_request'
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - name: Install the documentation toolchain
        # For PyYAML, which arrives transitively with MkDocs.
        run: uv sync --group docs
      - name: Report documentation freshness
        env:
          BASE_SHA: ${{ github.event.pull_request.base.sha }}
        run: |
          uv run python scripts/check_docs_freshness.py "$BASE_SHA" HEAD

  links:
    # External links only; internal ones are `mkdocs build --strict`'s job
    # in the `docs` job above. Separate from that job because this one
    # depends on the internet being well, and a network blip should not
    # read as a broken site.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Check external links
        uses: lycheeverse/lychee-action@v2
        with:
          args: --config lychee.toml --no-progress 'docs/**/*.md' README.md
          fail: true

  docs-examples:
    # The documented `curl` examples, against a real running stack.
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: examples/reference-service
    steps:
      - uses: actions/checkout@v4
      - uses: extractions/setup-just@v2
      - run: just docs-examples

  build:
    # Proves the Dockerfile still builds. Deliberately no push and no
    # multi-architecture matrix -- both are M6, with the registry and the
    # vulnerability scanning that should accompany them.
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: examples/reference-service
    steps:
      - uses: actions/checkout@v4
      - name: Build the application image
        run: docker build -t reference-service:ci .
      - name: Build the migrations image
        run: docker build -f Dockerfile.migrations -t reference-service-migrations:ci .
```

- [ ] **Step 2: Verify the whole workflow parses and the job list is right**

```bash
uv run --group docs python -c "
import yaml
jobs = yaml.safe_load(open('.github/workflows/ci.yml'))['jobs']
print(len(jobs), 'jobs:', sorted(jobs))
"
```

Expected: `11 jobs:` listing `build`, `check`, `contract`, `docs`, `docs-examples`, `docs-freshness`, `docs-warnings`, `gates`, `integration`, `links`, `o11y-gates`.

- [ ] **Step 3: Commit**

```bash
git add .github/workflows/ci.yml
git commit -m "ci: check links, run the documented examples and build the images"
```

---

### Task 16: The nightly workflow

The slow, valuable work that must not sit in the pull request path.

**Files:**
- Create: `.github/workflows/nightly.yml`

**What is not here.** The weekly cassette re-record job spec 10.4 describes is deliberately absent — the recorded upstream is a local WireMock stub, so re-recording produces an empty diff forever (Verified Fact 15). Dependency re-auditing belongs with the rest of M6's supply-chain work.

- [ ] **Step 1: Write the workflow**

Create `.github/workflows/nightly.yml`:

```yaml
name: Nightly

# Slow work that must not sit in the pull request path. Mutation testing
# takes far longer than a reviewer will wait, and external link checking
# fails for reasons nobody in the pull request caused.

on:
  schedule:
    # 03:17 UTC. Deliberately not on the hour: every scheduled job on
    # GitHub is queued at :00, and a job that starts when the queue is
    # empty starts sooner.
    - cron: "17 3 * * *"
  workflow_dispatch:

permissions:
  contents: read

jobs:
  mutation:
    # Measures whether a test would NOTICE a change in behaviour, which is
    # the question coverage cannot answer. Read the survivors, not the
    # percentage -- the recipe enforces a floor so a regression is caught,
    # but the value is in which mutants lived.
    runs-on: ubuntu-latest
    timeout-minutes: 60
    defaults:
      run:
        working-directory: examples/reference-service
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v5
        with:
          enable-cache: true
      - uses: extractions/setup-just@v2
      - run: uv sync
      - run: just mutants-gate

  links:
    # The full sweep. ci.yml checks links on every pull request too; this
    # one exists because an external link rots without anyone here
    # touching a file, so nothing would ever re-check it otherwise.
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: lycheeverse/lychee-action@v2
        with:
          args: --config lychee.toml --no-progress 'docs/**/*.md' README.md '**/*.md'
          fail: true
```

- [ ] **Step 2: Verify it parses**

Run: `uv run --group docs python -c "import yaml; print(sorted(yaml.safe_load(open('.github/workflows/nightly.yml'))['jobs']))"`
Expected: `['links', 'mutation']`.

- [ ] **Step 3: Confirm the mutation gate runs locally**

Run: `cd examples/reference-service && just mutants-gate`
Expected: a mutation score line and exit 0. This is slow — that is the reason it is nightly. If it fails on the floor, that is a real finding and belongs in its own change, not this one.

- [ ] **Step 4: Commit**

```bash
git add .github/workflows/nightly.yml
git commit -m "ci: run mutation testing and the full link sweep nightly"
```

---

### Task 17: Close the milestone

Every forward reference to M5 in published prose becomes a statement about what exists.

**Files:**
- Modify: `docs/roadmap.md`, `docs/contributing.md`, `docs/reference/commands.md`, `examples/reference-service/justfile`, `examples/reference-service/README.md`

- [ ] **Step 1: Update the roadmap**

Set the M5 row's State to **Done**, and rewrite its "What exists at the end" to describe what was actually built — noting that the Diátaxis structure and GitHub Pages arrived earlier, and that `catalog-info.yaml` was dropped. Update the opening line to "M0, M1, M2, M3, M4 and M5 are done."

Add both dropped items to the "What is deliberately excluded" table, with the reasons from this plan's own exclusions table. That table is the published record of decisions taken against; a decision that lives only in a plan document is not recorded where readers look.

- [ ] **Step 2: Document the hygiene switch**

In `docs/contributing.md`, under "Documentation ships with the change", describe the three mechanisms now in place and how they differ:

- `check_docs_updated.py` — a hard gate. Source changed, no documentation did. Escape hatch: the `no-docs-needed` label.
- `check_docs_freshness.py` — warnings. A page's `covers:` path changed while the page did not, or `last_reviewed` is over 180 days old.
- `lychee` and `mkdocs --strict` — hard gates on links.

Then state the conditions for flipping the warnings to failures, plainly enough that someone can check them: every published page carries `covers:` where a coupling genuinely exists; a month of pull requests has passed without the warnings producing noise nobody acted on; and the team has agreed that the blunt `check_docs_updated.py` gate is retired in the same change, because keeping both as hard gates means one pull request failing twice for the same reason.

- [ ] **Step 3: Update the commands reference and the service README**

`docs/reference/commands.md` needs the new recipes: `config-docs`, `config-docs-check`, `docs-examples` in the service; `test`, `docs-freshness`, `links`, `changelog`, `next-version` at the root.

`examples/reference-service/README.md:57` describes `just check-all` as "what CI will run at M5". M5 is now. Rewrite it to say what CI runs, and drop the forward reference. Do the same for the `justfile` comment above `check-all` ("What CI will run at M5") and above `gates`.

- [ ] **Step 4: Verify no forward references survive**

```bash
grep -rn "M5" --include="*.md" --include="justfile" --include="*.py" \
  docs README.md examples/reference-service \
  | grep -v "docs/superpowers/" | grep -v "^docs/roadmap.md"
```

Expected: no output. Every remaining mention should be in the archive (`docs/superpowers/`) or in the roadmap's own M5 row.

- [ ] **Step 5: Run everything**

```bash
just check
cd examples/reference-service && just check-all
```

Expected: both pass. This is the last point before the pull request where a gate added in this milestone can be found to disagree with a gate added in an earlier one.

- [ ] **Step 6: Commit**

```bash
git add docs/ examples/reference-service/README.md examples/reference-service/justfile
git commit -m "docs: mark m5 done and describe the gates it added"
```

---

## Definition of done

- [ ] `just check` passes at the repository root.
- [ ] `just check-all` passes in `examples/reference-service/`.
- [ ] `just config-docs` produces no diff; editing `.env.example` by hand makes `just gates` fail.
- [ ] `mkdocs build --strict` is clean with all 20 pages carrying frontmatter, 12 ADRs and the runbook in the nav.
- [ ] `just docs-examples` runs every marked `curl` example against a live stack and passes; breaking one makes it fail.
- [ ] `just links` reports no dead external links.
- [ ] `CHANGELOG.md` exists, covers the full history, and `uv lock --check` passes at version `0.5.0`.
- [ ] `check_contract_compatibility.py` fails a breaking contract change with no breaking commit marker, and passes one with `feat!:`.
- [ ] `ci.yml` has 11 jobs; `release.yml` and `nightly.yml` parse.
- [ ] No forward reference to M5 survives outside `docs/superpowers/` and the roadmap's own row.
