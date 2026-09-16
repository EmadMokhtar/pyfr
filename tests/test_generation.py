"""What every render must satisfy, whatever the answers.

PR 1 checks the default answers and the reference answers. PR 2 makes this
a matrix over the backend combinations.
"""

from __future__ import annotations

import ast
import json
import re
import shutil
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_ANSWERS = ROOT / "tests" / "reference-answers.yaml"

# The version the release last wrote into pyproject.toml. cookiecutter.json
# cannot compute, so its `_template_version` is written by the same
# `cz bump` (pyproject.toml's [tool.commitizen] version_files) and must
# equal this at every commit.
TEMPLATE_VERSION: str = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"][
    "version"
]

BACKENDS = {
    "database": ("postgres", "none"),
    "cache": ("redis", "none"),
    "object_storage": ("s3", "none"),
}
# The eight combinations, as the extra_context dicts pytest-cookies takes.
COMBINATIONS = [
    {"database": db, "cache": cache, "object_storage": storage}
    for db in BACKENDS["database"]
    for cache in BACKENDS["cache"]
    for storage in BACKENDS["object_storage"]
]
EVERYTHING_ON = COMBINATIONS[0]


def combination_id(answers: dict[str, str]) -> str:
    return "-".join(answers[key] for key in ("database", "cache", "object_storage"))


def render(cookies, **answers: str):
    result = cookies.bake(extra_context=answers)
    assert result.exit_code == 0, result.exception
    return result.project_path


# The longest package name hooks/pre_gen_project.py accepts. The reference
# name is 17 characters; every line that spells the package out gets 8
# columns longer here, and the render must still pass the formatter and the
# 88-column limit.
CAP_PROJECT_NAME = "Abcde Fghij Klmno Pqrst U"
CAP_PACKAGE_NAME = "abcde_fghij_klmno_pqrst_u"

JINJA_MARKERS = (b"{{", b"{%")

# Markers that must never survive a render, in ANY file (grafana excepted):
# an unrendered cookiecutter variable, a {% raw %}/{% endraw %}/{% if %}/
# {% endif %} tag Jinja failed to consume, or a left-strip {%- tag Jinja
# failed to consume. Checking for these -- rather than for bare {{ / {% --
# is what lets the four files below still be checked for real Jinja bugs
# instead of being skipped outright.
ALWAYS_FORBIDDEN_MARKERS = (
    b"{{ cookiecutter",
    b"{% raw",
    b"{% endraw",
    b"{% if",
    b"{% endif",
    b"{%-",
)

# Files where a literal {{ }} / {% %} is someone else's syntax, not ours,
# and is guarded with {% raw %} so Jinja leaves it alone: golang-migrate's
# CLI placeholders and the buildx/trivy recipes' own {{name}} interpolation
# (justfile), Prometheus's alert-label templating (slo.yml), sqlfluff's
# comment naming its own template markers (.sqlfluff), a raw PromQL query
# string (test_observability_stack.py), and GitHub Actions' `${{ }}`
# expressions (the five workflows). None of these are cookiecutter
# collisions. They are still checked for ALWAYS_FORBIDDEN_MARKERS above --
# only their own raw-guarded braces are excused, not real Jinja mistakes.
RAW_GUARDED_FILES = frozenset(
    {
        "justfile",
        "ops/prometheus/rules/slo.yml",
        ".sqlfluff",
        "tests/integration/test_observability_stack.py",
        ".github/workflows/ci.yml",
        ".github/workflows/nightly.yml",
        ".github/workflows/release.yml",
        ".github/workflows/docs.yml",
        ".github/workflows/template-update.yml",
    }
)


@pytest.fixture(autouse=True)
def _regen_mode(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PYFR_REGEN", "1")


def files_under(root: Path) -> list[Path]:
    return sorted(p for p in root.rglob("*") if p.is_file())


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_no_template_syntax_survives_any_combination(cookies, answers) -> None:
    root = render(cookies, **answers)
    offenders = []
    for path in files_under(root):
        relative = path.relative_to(root).as_posix()
        # Grafana's own {{ }} legend syntax, copied verbatim on purpose
        # (spec section 7); never rendered, so nothing here to check.
        if relative.startswith("ops/grafana/"):
            continue
        content = path.read_bytes()
        if any(marker in content for marker in ALWAYS_FORBIDDEN_MARKERS):
            offenders.append(relative)
            continue
        if relative in RAW_GUARDED_FILES:
            if relative.startswith(".github/workflows/"):
                # Every {{ in a workflow file must be GitHub Actions'
                # own ${{ }} expression syntax, not a cookiecutter
                # variable that escaped rendering.
                assert content.count(b"{{") == content.count(b"${{"), relative
            continue
        if any(marker in content for marker in JINJA_MARKERS):
            offenders.append(relative)
    assert offenders == []


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_every_combination_renders_and_records_its_answers(cookies, answers) -> None:
    root = render(cookies, **answers)
    recorded = yaml.safe_load((root / ".pyfr-answers.yml").read_text())
    assert recorded["_template_version"] == TEMPLATE_VERSION
    assert recorded["_template"] == "https://github.com/EmadMokhtar/pyfr"
    for key, value in answers.items():
        assert recorded[key] == value
    assert recorded["package_name"] == "my_service"


def test_the_template_version_is_the_repository_version() -> None:
    # A hand edit of either file between releases would drift them apart;
    # `cz bump --check-consistency` in release.yml then refuses to release
    # a version it cannot find on cookiecutter.json's line, and this fails
    # first, on the pull request.
    answers = json.loads((ROOT / "cookiecutter.json").read_text())
    assert answers["_template_version"] == TEMPLATE_VERSION


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_the_contract_is_the_same_in_every_combination(cookies, answers) -> None:
    root = render(cookies, **answers)
    reference = render(cookies, **EVERYTHING_ON)
    for name in ("openapi.json", "openapi.baseline.json"):
        assert (root / name).read_bytes() == (reference / name).read_bytes()


def test_the_reference_answers_render_the_reference_names(cookies) -> None:
    answers = yaml.safe_load(REFERENCE_ANSWERS.read_text())
    result = cookies.bake(extra_context={k: str(v) for k, v in answers.items()})
    assert result.exit_code == 0, result.exception
    assert result.project_path.name == "reference-service"
    package = result.project_path / "src" / "reference_service"
    assert (package / "main.py").is_file()
    pyproject = (result.project_path / "pyproject.toml").read_text()
    assert 'name = "reference-service"' in pyproject
    assert "Emad Mokhtar" in pyproject
    assert (
        (result.project_path / "LICENSE")
        .read_text()
        .startswith("Mozilla Public License Version 2.0")
    )


# 9100: no template file mentions it, and nothing in the stack binds it.
def test_a_custom_port_reaches_every_place_the_port_lives(cookies) -> None:
    result = cookies.bake(extra_context={"http_port": "9100"})
    assert result.exit_code == 0, result.exception
    root = result.project_path
    assert "EXPOSE 9100" in (root / "Dockerfile").read_text()
    assert '"9100:9100"' in (root / "compose.yaml").read_text()
    assert "APP_HTTP_PORT=9100" in (root / ".env.example").read_text()
    settings = (root / "src" / "my_service" / "settings.py").read_text()
    assert "default=9100" in settings
    test_settings = (root / "tests" / "unit" / "test_settings.py").read_text()
    assert "== 9100" in test_settings


def test_the_docs_carry_the_chosen_port(cookies) -> None:
    # The eight-combination matrix never varies http_port; this render does,
    # so a port hard-coded in a page fails here and not in a user's
    # config-docs-check.
    root = render(cookies, http_port="9100")
    offenders = [
        path.relative_to(root).as_posix()
        for path in sorted((root / "docs").rglob("*.md"))
        if "localhost:8000" in path.read_text()
    ]
    assert offenders == []
    configuration = (root / "docs" / "reference" / "configuration.md").read_text()
    # The generated table's row: `just config-docs-check` regenerates it
    # from the settings model, whose default is the answer.
    row = next(
        line
        for line in configuration.splitlines()
        if line.startswith("| `APP_HTTP_PORT` |")
    )
    assert "| `9100` |" in row, row


def test_a_package_name_at_the_cap_is_format_clean(cookies) -> None:
    assert len(CAP_PACKAGE_NAME) == 25
    result = cookies.bake(extra_context={"project_name": CAP_PROJECT_NAME})
    assert result.exit_code == 0, result.exception
    root = result.project_path
    assert (root / "src" / CAP_PACKAGE_NAME / "main.py").is_file()
    # ruff from the root's dev group, through its module entry point; it
    # picks the render's own ruff.toml, so this is the check a generated
    # project's `just check` runs.
    for completed in (
        ruff(root, "format", "--check"),
        ruff(root, "check", "--select", "E501"),
    ):
        assert completed.returncode == 0, completed.stdout + completed.stderr


def test_dashboards_are_copied_verbatim(cookies) -> None:
    result = cookies.bake()
    assert result.exit_code == 0, result.exception
    for name in ("runtime.json", "service-health.json", "slo.json"):
        rendered = result.project_path / "ops" / "grafana" / "dashboards" / name
        template_root = ROOT / "{{cookiecutter.project_slug}}"
        source = template_root / "ops" / "grafana" / "dashboards" / name
        assert rendered.read_bytes() == source.read_bytes()


def test_a_render_owns_its_commitizen(cookies) -> None:
    # M7-9: a generated project has its own version, tags and release
    # workflow, so the tool that decides its version is in its own lock.
    root = render(cookies)
    table = tomllib.loads((root / "pyproject.toml").read_text())["tool"]["commitizen"]
    assert table["version_provider"] == "uv"
    assert table["tag_format"] == "v$version"
    assert table["update_changelog_on_bump"] is True
    assert table["major_version_zero"] is True
    assert "commitizen" in dependency_names(root)
    hooks = yaml.safe_load((root / ".pre-commit-config.yaml").read_text())
    assert "commit-msg" in hooks["default_install_hook_types"]
    local = next(repo for repo in hooks["repos"] if repo["repo"] == "local")
    commitizen = next(hook for hook in local["hooks"] if hook["id"] == "commitizen")
    assert commitizen["stages"] == ["commit-msg"]
    assert (
        commitizen["entry"]
        == "uv run --locked cz check --allow-abort --commit-msg-file"
    )
    assert {"changelog", "next-version"} <= recipe_names(root)


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_the_ignore_file_is_the_tool_s_built_in_default(cookies, answers) -> None:
    # `pyfr update` carries the same list as its fallback for a project
    # generated before the file existed (spec section 5.2, decision M8-5).
    # One text, two places: the body ships it, the tool embeds it.
    from pyfr_cli.ignore import default_text

    root = render(cookies, **answers)
    recorded = yaml.safe_load((root / ".pyfr-answers.yml").read_text())
    expected = default_text(recorded["package_name"], recorded["database"])
    assert (root / ".pyfr-update-ignore").read_text() == expected
    schema_lines = {"/migrations/", "/schema.sql"}
    present = set(expected.splitlines()) & schema_lines
    assert bool(present) == (answers["database"] == "postgres")


PACKAGE = "my_service"

# Per backend: the libraries a render must not import, the ones .importlinter
# names, the settings group's variable prefix, the compose services, the
# justfile recipes, the dependencies and the paths the hook deletes. Only
# .py files, .env.example, .importlinter, compose.yaml, pyproject.toml and
# the justfile are inspected; prose (README.md, comments) is not.
BACKEND = {
    "database": {
        "libraries": ("sqlalchemy", "asyncpg", "alembic"),
        "importlinter": ("sqlalchemy", "asyncpg"),
        "package": "db",
        "env_prefix": "APP_DATABASE__",
        "services": ("postgres", "migrate"),
        "recipes": (
            "schema-snapshot",
            "migrate",
            "migrate-new",
            "migrate-manifest",
            "migrate-down",
            "migrate-version",
            "migrate-force",
            "psql",
        ),
        "dependencies": (
            "sqlalchemy",
            "asyncpg",
            "alembic",
            "opentelemetry-instrumentation-sqlalchemy",
        ),
        "paths": (
            "migrations/",
            "schema.sql",
            "Dockerfile.migrations",
            ".sqlfluff",
            f"src/{PACKAGE}/infrastructure/db/",
            "tests/unit/test_db_mappers.py",
            "tests/unit/test_engine.py",
            "tests/unit/test_migration_files.py",
            "tests/unit/test_order_repository.py",
            "tests/integration/test_order_repository.py",
            "tests/integration/test_db_instrumentation.py",
            "tests/integration/test_schema_drift.py",
            "tests/integration/test_schema_gates.py",
            "docs/adr/0004-golang-migrate-owns-the-schema.md",
        ),
    },
    "cache": {
        "libraries": ("redis",),
        "importlinter": ("redis",),
        "package": "cache",
        "env_prefix": "APP_CACHE__",
        "services": ("redis",),
        "recipes": ("redis-cli",),
        "dependencies": ("redis", "opentelemetry-instrumentation-redis"),
        "paths": (
            f"src/{PACKAGE}/infrastructure/cache/",
            "tests/unit/test_cached_order_repository.py",
            "tests/integration/test_cached_order_repository.py",
            "tests/integration/test_redis_instrumentation.py",
            "docs/adr/0006-the-cache-is-fail-open-always.md",
        ),
    },
    "object_storage": {
        "libraries": ("aioboto3", "botocore", "boto3"),
        "importlinter": ("aioboto3",),
        "package": "storage",
        "env_prefix": "APP_STORAGE__",
        "services": ("minio", "minio-bootstrap"),
        "recipes": ("minio-console",),
        # `minio` is the test-container client in the dev group, not the
        # adapter's library; it follows the backend all the same.
        "dependencies": ("aioboto3", "minio"),
        "paths": (
            f"src/{PACKAGE}/infrastructure/storage/",
            "tests/integration/test_receipt_store.py",
        ),
    },
}
IMPORT = re.compile(r"^\s*(?:from|import)\s+([A-Za-z_][\w.]*)", re.MULTILINE)
INFRA = re.compile(r"infrastructure\.(db|cache|storage)\b")


def python_files(root: Path) -> list[Path]:
    return [p for p in files_under(root) if p.suffix == ".py"]


def imported_top_levels(path: Path) -> set[str]:
    return {m.group(1).split(".")[0] for m in IMPORT.finditer(path.read_text())}


def compose_services(root: Path) -> set[str]:
    return set(yaml.safe_load((root / "compose.yaml").read_text())["services"])


def dependency_names(root: Path) -> set[str]:
    data = tomllib.loads((root / "pyproject.toml").read_text())
    names = set()
    groups = [
        data["project"]["dependencies"],
        *data.get("dependency-groups", {}).values(),
    ]
    for group in groups:
        for spec in group:
            if isinstance(spec, str):
                names.add(re.split(r"[\[<>=!~; ]", spec, maxsplit=1)[0].lower())
    return names


def extras_of_testcontainers(root: Path) -> set[str]:
    data = tomllib.loads((root / "pyproject.toml").read_text())
    for spec in data["dependency-groups"]["dev"]:
        if isinstance(spec, str) and spec.startswith("testcontainers"):
            extras = re.match(r"testcontainers(?:\[([^\]]*)\])?", spec).group(1) or ""
            return {extra for extra in extras.split(",") if extra}
    raise AssertionError("testcontainers is not a dev dependency")


def recipe_names(root: Path) -> set[str]:
    return {
        m.group(1)
        for m in re.finditer(
            r"^([A-Za-z_][\w-]*)(?:\s+[^:\n]*)?:(?!=)",
            (root / "justfile").read_text(),
            re.M,
        )
    }


def ruff(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    # The root environment's ruff (a dependency of the `dev` group); run in
    # the render, so ruff picks the render's own ruff.toml.
    return subprocess.run(
        [sys.executable, "-m", "ruff", *args, "."],
        cwd=root,
        capture_output=True,
        text=True,
    )


def module_scope(body: list[ast.stmt]) -> Iterator[ast.stmt]:
    """The statements that bind at module scope: the body, descending into
    try/if/with/for blocks (a `try: __version__ = …` binds the module), never
    into a def or class."""
    for node in body:
        yield node
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        blocks = [getattr(node, field, []) for field in ("body", "orelse", "finalbody")]
        for block in blocks + [h.body for h in getattr(node, "handlers", [])]:
            yield from module_scope(block)


def bound_names(target: ast.expr) -> set[str]:
    """The names an assignment target binds: `a`, `(a, b)`, `[a, *b]`."""
    return {n.id for n in ast.walk(target) if isinstance(n, ast.Name)}


def top_level_names(module: Path) -> set[str]:
    """Every name a module binds at top level: defs, assignments, type
    aliases, imports, and the targets of a module-scope `for` or `with`."""
    names: set[str] = set()
    for node in module_scope(ast.parse(module.read_text()).body):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                names |= bound_names(target)
        elif isinstance(node, ast.AnnAssign):
            names |= bound_names(node.target)
        elif isinstance(node, ast.TypeAlias):
            names.add(node.name.id)
        elif isinstance(node, ast.For | ast.AsyncFor):
            names |= bound_names(node.target)
        elif isinstance(node, ast.With | ast.AsyncWith):
            for item in node.items:
                if item.optional_vars is not None:
                    names |= bound_names(item.optional_vars)
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
    return names


def unresolved_first_party_imports(root: Path) -> list[tuple[str, str, str]]:
    """(file, module, name) for every first-party `from … import name` that
    names a module the render lacks or a name that module does not bind. A
    conditional that prunes a def but not a test's import of it passes ruff
    and fails only at collection time; this is that check, without pytest.
    Relative imports (`from . import x`, `from .sibling import x`) are
    skipped: only absolute paths under the package or `tests` are resolved.
    """
    roots = {PACKAGE: root / "src" / PACKAGE, "tests": root / "tests"}
    failures = []
    for path in python_files(root):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
                continue
            if node.level:  # relative: `from .sibling import x`
                continue
            head, *rest = node.module.split(".")
            if head not in roots:
                continue
            location = roots[head].joinpath(*rest)
            module = location.with_suffix(".py")
            if not module.is_file():
                module = location / "__init__.py"
            bound = top_level_names(module) if module.is_file() else set()
            for alias in node.names:
                name = alias.name
                if name in bound or (location / f"{name}.py").is_file():
                    continue
                if (location / name / "__init__.py").is_file():
                    continue
                failures.append((path.relative_to(root).as_posix(), node.module, name))
    return failures


def assert_compose_is_self_consistent(root: Path, answers: dict[str, str]) -> None:
    """compose.yaml beyond its service names.

    The chosen backends' variables reach `app.environment` and no other
    backend's survive anywhere in the file; every `depends_on` names a
    service the file defines; every named volume a service mounts is
    declared under the top-level `volumes`. A conditional that prunes a
    service but not the lines that point at it renders a file compose
    refuses to start, and nothing else here reads those lines.
    """
    compose_text = (root / "compose.yaml").read_text()
    compose = yaml.safe_load(compose_text)
    services = compose["services"]
    declared_volumes = set(compose.get("volumes") or {})
    # A mapping (`KEY: value`) or a list of `KEY=value`; either iterates
    # to strings that start with the variable name.
    app_environment = services["app"].get("environment") or {}
    for key, spec in BACKEND.items():
        on = answers[key] != "none"
        prefix = spec["env_prefix"]
        assert (prefix in compose_text) == on, (key, "compose.yaml")
        if on:
            assert any(name.startswith(prefix) for name in app_environment), (
                key,
                "app.environment",
            )
    for name, service in services.items():
        # `depends_on` is a mapping (`postgres: {condition: …}`) or a list
        # of names; iterating either yields the names.
        for dependency in service.get("depends_on") or {}:
            assert dependency in services, (name, "depends_on", dependency)
        for mount in service.get("volumes") or []:
            # Short syntax only (`source:/target[:ro]`). A source that starts
            # with `/` or `.` is a host path; anything else names a volume.
            source = mount.split(":", 1)[0]
            if source.startswith(("/", ".")):
                continue
            assert source in declared_volumes, (name, "volumes", source)


# A word that must not survive in .github/ when its backend is off. Matched
# case-insensitively over the whole file, comments included: a comment that
# names a container the render does not have is the M7 PR 2 rule broken.
# "schema" is not here because "schemathesis" carries it in every render.
WORKFLOW_BACKEND_WORDS = {
    "database": ("postgres", "migrat"),
    "cache": ("redis",),
    "object_storage": ("minio", "s3"),
}

# Pages that document what the render HAS: a word of a pruned backend in
# them is a section that should have been conditional. Comparative prose
# elsewhere (an ADR weighing PostgreSQL against an in-memory store) is
# deliberately not policed.
DOCS_BACKEND_PAGES = (
    "docs/index.md",
    "docs/getting-started.md",
    "docs/runbook.md",
    "docs/reference/commands.md",
    "docs/reference/configuration.md",
    "docs/reference/observability.md",
    "docs/reference/supply-chain.md",
    "docs/guides/run-in-a-container.md",
    "docs/glossary.md",
    "mkdocs.yml",
    "README.md",
)
DOCS_BACKEND_WORDS = {
    "database": ("postgres", "migrat", "schema.sql", "golang-migrate"),
    "cache": ("redis",),
    # "bucket" is deliberately not here: it is also Prometheus's own word for
    # a histogram bucket (observability.md's "Changing the objectives"
    # section), so banning it would fail a combination that has nothing to
    # do with object storage.
    "object_storage": ("minio", " s3"),
}
JUST_CALL = re.compile(r"\bjust\s+([a-z][a-z0-9-]*)")
DEPENDABOT_ECOSYSTEMS = [
    "uv",
    "github-actions",
    "docker",
    "docker-compose",
    "pre-commit",
]


def workflow_files(root: Path) -> list[Path]:
    return sorted((root / ".github").rglob("*.yml"))


def run_scripts(document: dict) -> Iterator[str]:
    """Every `run:` value in a parsed workflow, shell comment lines removed."""
    for job in document.get("jobs", {}).values():
        for step in job.get("steps", []):
            script = step.get("run")
            if script:
                yield "\n".join(
                    line
                    for line in script.splitlines()
                    if not line.lstrip().startswith("#")
                )


def assert_workflows_are_coherent(root: Path, answers: dict[str, str]) -> None:
    # The rendered workflows never run in this repository (GitHub runs
    # workflows from a repository's root only), so this is their only
    # gate before a generated project pushes them: the YAML parses, a
    # pruned backend leaves no word behind, every `just` recipe a step
    # calls exists in this render's justfile, and Dependabot's schedule
    # names the five ecosystems.
    recipes = recipe_names(root)
    for path in workflow_files(root):
        relative = path.relative_to(root).as_posix()
        text = path.read_text()
        document = yaml.safe_load(text)
        assert isinstance(document, dict), relative
        for key, words in WORKFLOW_BACKEND_WORDS.items():
            if answers[key] == "none":
                for word in words:
                    assert word not in text.lower(), (relative, word)
        if relative == ".github/dependabot.yml":
            updates = document["updates"]
            assert [u["package-ecosystem"] for u in updates] == DEPENDABOT_ECOSYSTEMS
            assert all(u["directory"] == "/" for u in updates), relative
            continue
        for script in run_scripts(document):
            for recipe in JUST_CALL.findall(script):
                assert recipe in recipes, (relative, recipe)
    # Deliberately checked last: with only some of ci.yml/nightly.yml/
    # release.yml/dependabot.yml present, the per-file checks above must
    # still run against whatever files do exist before this assertion ends
    # the test, so a broken word or a broken `just` call is caught even
    # while the file set is incomplete.
    present = {p.relative_to(root).as_posix() for p in workflow_files(root)}
    assert present >= {
        ".github/workflows/ci.yml",
        ".github/workflows/nightly.yml",
        ".github/workflows/release.yml",
        ".github/workflows/docs.yml",
        ".github/dependabot.yml",
    }, present


def assert_invariant(root: Path, answers: dict[str, str]) -> None:
    services = compose_services(root)
    dependencies = dependency_names(root)
    recipes = recipe_names(root)
    env_example = (root / ".env.example").read_text()
    importlinter = (root / ".importlinter").read_text()
    for key, spec in BACKEND.items():
        on = answers[key] != "none"
        for path in spec["paths"]:
            assert (root / path).exists() == on, (key, path, on)
        for service in spec["services"]:
            assert (service in services) == on, (key, service, on)
        for recipe in spec["recipes"]:
            assert (recipe in recipes) == on, (key, recipe, on)
        for dependency in spec["dependencies"]:
            assert (dependency in dependencies) == on, (key, dependency, on)
        assert (spec["env_prefix"] in env_example) == on, (key, "env")
        configuration = (root / "docs" / "reference" / "configuration.md").read_text()
        assert (spec["env_prefix"] in configuration) == on, (key, "configuration.md")
        if not on:
            for page in DOCS_BACKEND_PAGES:
                text = (root / page).read_text().lower()
                for word in DOCS_BACKEND_WORDS[key]:
                    assert word not in text, (key, page, word)
        for library in spec["importlinter"]:
            assert (library in importlinter) == on, (key, library, ".importlinter")
        if on:
            continue
        for path in python_files(root):
            text = path.read_text()
            imports = imported_top_levels(path)
            assert not imports & set(spec["libraries"]), (key, path.relative_to(root))
            assert not any(
                m.group(1) == spec["package"] for m in INFRA.finditer(text)
            ), (key, path.relative_to(root))
            assert spec["env_prefix"] not in text, (key, path.relative_to(root))
    assert_compose_is_self_consistent(root, answers)
    assert_workflows_are_coherent(root, answers)
    # Cross-cutting: nothing empty, nothing unformatted, nothing unused.
    for directory in (p for p in root.rglob("*") if p.is_dir()):
        assert any(directory.iterdir()), (
            f"empty directory {directory.relative_to(root)}"
        )
    # The rendered justfile must parse: a recipe left calling a pruned recipe,
    # or an unbalanced inline tag, shows up here and nowhere else. `just` is
    # on PATH in CI (extractions/setup-just) and on every contributor machine
    # this repository's own justfile assumes; skipped, not failed, elsewhere.
    if shutil.which("just"):
        listed = subprocess.run(
            ["just", "--list", "--justfile", str(root / "justfile")],
            capture_output=True,
            text=True,
        )
        assert listed.returncode == 0, listed.stdout + listed.stderr
    check = ruff(root, "check")
    assert check.returncode == 0, check.stdout + check.stderr
    fmt = ruff(root, "format", "--check")
    assert fmt.returncode == 0, fmt.stdout + fmt.stderr
    assert unresolved_first_party_imports(root) == []
    # testcontainers stays in every render: test_observability_stack.py
    # drives the LGTM container through testcontainers.core. Only its
    # extras follow the backends.
    extras = {"database": "postgres", "cache": "redis", "object_storage": "minio"}
    chosen = {extras[key] for key in BACKEND if answers[key] != "none"}
    assert extras_of_testcontainers(root) == chosen


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_a_render_carries_only_the_backends_it_chose(cookies, answers) -> None:
    assert_invariant(render(cookies, **answers), answers)


def build_site(root: Path) -> subprocess.CompletedProcess[str]:
    # The root's MkDocs over the render's own mkdocs.yml: no `uv sync` in
    # the render, so no network and no second toolchain. `site_url` and the
    # repository keys read SITE_URL, REPO_URL, REPO_NAME and EDIT_URI
    # through `!ENV`; unset, the defaults apply.
    return subprocess.run(
        [
            sys.executable,
            "-m",
            "mkdocs",
            "build",
            "--strict",
            "--config-file",
            str(root / "mkdocs.yml"),
            "--site-dir",
            str(root / "site"),
        ],
        capture_output=True,
        text=True,
    )


@pytest.mark.parametrize(
    "answers", [EVERYTHING_ON, COMBINATIONS[-1]], ids=combination_id
)
def test_the_two_extreme_renders_build_their_sites(cookies, answers) -> None:
    # Every page, every nav entry and every cross-reference must resolve
    # with everything on and with everything off; the six other
    # combinations are covered by the full-suite tests (PR 5).
    root = render(cookies, **answers)
    built = build_site(root)
    assert built.returncode == 0, built.stdout + built.stderr
    assert (root / "site" / "index.html").is_file()


# The reference service's identity must never leak into a project with a
# different one. PyFr's own URLs are the exception: a generated project
# links back to the template it came from.
IDENTITY_LEAKS = ("reference-service", "reference_service", "Reference Service")
PYFR_URLS = ("github.com/EmadMokhtar/pyfr", "emadmokhtar.github.io/pyfr/")
# Where a render speaks about itself: the site, the README, the scripts'
# docstrings and comments, the site's configuration and the workflows.
IDENTITY_TREES = ("docs", "README.md", "scripts", "mkdocs.yml", ".github")


def identity_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for name in IDENTITY_TREES:
        path = root / name
        files.extend(files_under(path) if path.is_dir() else [path])
    return files


def test_the_docs_carry_the_answers_not_the_reference_identity(cookies) -> None:
    root = render(cookies)  # default answers: my-service, my_service, your-org
    offenders = []
    for path in identity_files(root):
        text = path.read_text()
        for line in text.splitlines():
            stripped = line
            for url in PYFR_URLS:
                stripped = stripped.replace(url, "")
            if (
                any(leak in stripped for leak in IDENTITY_LEAKS)
                or "emadmokhtar" in stripped.lower()
            ):
                offenders.append(f"{path.relative_to(root)}: {line.strip()[:80]}")
    assert offenders == []


def test_the_update_recipes_wrap_pyfr_cli_from_pypi(cookies) -> None:
    # spec section 5.1: the newest release on PyPI is, by construction, the
    # newest template tag, so `@latest` runs the updater at the target
    # version; a pinned `to` pins both the tool and the target.
    root = render(cookies, **EVERYTHING_ON)
    justfile = (root / "justfile").read_text()
    assert "uvx --from pyfr-cli@latest pyfr update\n" in justfile
    assert "uvx --from pyfr-cli@latest pyfr update-check\n" in justfile
    assert (
        'uvx --from "pyfr-cli==${version}" pyfr update --to "v${version}"' in justfile
    )
    # just's own interpolation survived Jinja: the recipe reads {{to}}.
    assert 'if [ -n "{{to}}" ]; then' in justfile
    # Neither tool enters the project's environment.
    pyproject = (root / "pyproject.toml").read_text()
    assert "pyfr-cli" not in pyproject
    assert "cookiecutter" not in pyproject


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_every_render_carries_the_update_guide(cookies, answers) -> None:
    # Twelve error messages in pyfr-cli point the reader at
    # docs/guides/update-from-template.md; the page must exist in every
    # render, and be in the site's nav (tests/test_site_nav.py checks the
    # example's nav; this checks the render's).
    from pyfr_cli.answers import GUIDE

    root = render(cookies, **answers)
    page = root / GUIDE
    assert page.is_file()
    text = page.read_text()
    assert text.startswith("---\nlast_reviewed: ")
    for phrase in (
        "just update",
        "git branch --force template",
        "git commit --no-edit",
        ".pyfr-update-ignore",
        "RELEASE_TOKEN",
    ):
        assert phrase in text, phrase
    nav = (root / "mkdocs.yml").read_text()
    assert "guides/update-from-template.md" in nav


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_every_render_carries_the_weekly_template_update(cookies, answers) -> None:
    root = render(cookies, **answers)
    workflow = (root / ".github" / "workflows" / "template-update.yml").read_text()
    # The decisions are the tool's exit codes (spec section 5.3); the
    # workflow only pushes and talks to GitHub.
    assert "uvx --from pyfr-cli@latest pyfr update-check --json" in workflow
    assert "uvx --from pyfr-cli@latest pyfr update --no-push" in workflow
    assert 'cron: "23 6 * * 1"' in workflow
    # RELEASE_TOKEN never enters the checkout: its `with:` block carries
    # no `token:` override, so it persists whatever the ambient workflow
    # token is.
    checkout = workflow.split("- uses: actions/checkout@v7")[1].split(
        "- name: Install uv"
    )[0]
    assert "token:" not in checkout
    assert "persist-credentials: true" in checkout
    assert "pyfr/update-" in workflow
    assert "gh pr create" in workflow and "gh issue create" in workflow
    # #55: the run stops while any update pull request or conflict issue
    # is open, whatever its version -- not only the newest version's.
    assert 'startswith("pyfr/update-")' in workflow
    assert 'startswith("chore: template ")' in workflow
    # #55: the conflict issue opens even when the push step failed, and
    # says so; a failed step otherwise skips everything after it.
    assert "!cancelled() && steps.update.outcome == 'success'" in workflow
    assert "steps.push.outcome" in workflow
    # #55: the release page comes from the tool, not from the workflow.
    assert "release_url=$(jq -r .release_url check.json)" in workflow
    assert "/releases/tag/" not in workflow
    # #55: a refused `gh pr create` or `gh issue create` names the missing
    # permission, as the refused push already does.
    assert workflow.count("::error::") >= 3
    assert "lacks the Pull requests permission" in workflow
    assert "lacks the Issues permission" in workflow


def test_the_readme_documents_the_update_workflow_and_its_token(cookies) -> None:
    root = render(cookies, **EVERYTHING_ON)
    readme = (root / "README.md").read_text()
    section = readme.split("## Continuous integration and releases")[1].split("\n## ")[
        0
    ]
    assert "Five workflows" in section
    assert "`template-update.yml`" in section
    # spec section 5.4: the token's documented permissions widen, and the
    # consequences of leaving it out are stated.
    assert "Pull requests" in section and "Issues" in section
    assert "Workflows" in section
    normalized_section = " ".join(section.split())
    assert (
        "Allow GitHub Actions to create and approve pull requests" in normalized_section
    )
    assert "Six settings" in section
    contributing = (root / "docs" / "contributing.md").read_text()
    assert "Six settings" in contributing
