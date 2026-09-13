"""What every render must satisfy, whatever the answers.

PR 1 checks the default answers and the reference answers. PR 2 makes this
a matrix over the backend combinations.
"""

from __future__ import annotations

import ast
import re
import subprocess
import sys
import tomllib
from collections.abc import Iterator
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_ANSWERS = ROOT / "tests" / "reference-answers.yaml"

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
# an unrendered cookiecutter variable, or a {% raw %}/{% endraw %}/{% if %}/
# {% endif %} tag Jinja failed to consume. Checking for these -- rather than
# for bare {{ / {% -- is what lets the four files below still be checked for
# real Jinja bugs instead of being skipped outright.
ALWAYS_FORBIDDEN_MARKERS = (
    b"{{ cookiecutter",
    b"{% raw",
    b"{% endraw",
    b"{% if",
    b"{% endif",
)

# Files where a literal {{ }} / {% %} is someone else's syntax, not ours,
# and is guarded with {% raw %} so Jinja leaves it alone: golang-migrate's
# CLI placeholders and the buildx/trivy recipes' own {{name}} interpolation
# (justfile), Prometheus's alert-label templating (slo.yml), sqlfluff's
# comment naming its own template markers (.sqlfluff), and a raw PromQL
# query string (test_observability_stack.py). None of these are cookiecutter
# collisions. They are still checked for ALWAYS_FORBIDDEN_MARKERS above --
# only their own raw-guarded braces are excused, not real Jinja mistakes.
RAW_GUARDED_FILES = frozenset(
    {
        "justfile",
        "ops/prometheus/rules/slo.yml",
        ".sqlfluff",
        "tests/integration/test_observability_stack.py",
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
            continue
        if any(marker in content for marker in JINJA_MARKERS):
            offenders.append(relative)
    assert offenders == []


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_every_combination_renders_and_records_its_answers(cookies, answers) -> None:
    root = render(cookies, **answers)
    recorded = yaml.safe_load((root / ".pyfr-answers.yml").read_text())
    assert recorded["_template_version"] == "0.6.0"
    assert recorded["_template"] == "https://github.com/EmadMokhtar/pyfr"
    for key, value in answers.items():
        assert recorded[key] == value
    assert recorded["package_name"] == "my_service"


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


def test_a_custom_port_reaches_every_place_the_port_lives(cookies) -> None:
    result = cookies.bake(extra_context={"http_port": "9000"})
    assert result.exit_code == 0, result.exception
    root = result.project_path
    assert "EXPOSE 9000" in (root / "Dockerfile").read_text()
    assert '"9000:9000"' in (root / "compose.yaml").read_text()
    assert "APP_HTTP_PORT=9000" in (root / ".env.example").read_text()
    settings = (root / "src" / "my_service" / "settings.py").read_text()
    assert "default=9000" in settings
    test_settings = (root / "tests" / "unit" / "test_settings.py").read_text()
    assert "== 9000" in test_settings


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
        ),
    },
    "object_storage": {
        "libraries": ("aioboto3", "botocore", "boto3"),
        "importlinter": ("aioboto3",),
        "package": "storage",
        "env_prefix": "APP_STORAGE__",
        "services": ("minio", "minio-bootstrap"),
        "recipes": ("minio-console",),
        "dependencies": ("aioboto3",),
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


def top_level_names(module: Path) -> set[str]:
    """Every name a module binds at top level: defs, assignments, imports."""
    names: set[str] = set()
    for node in module_scope(ast.parse(module.read_text()).body):
        if isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            names.add(node.name)
        elif isinstance(node, ast.Assign | ast.AnnAssign):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for target in targets:
                names.update(n.id for n in ast.walk(target) if isinstance(n, ast.Name))
        elif isinstance(node, ast.Import | ast.ImportFrom):
            names.update(a.asname or a.name.split(".")[0] for a in node.names)
    return names


def unresolved_first_party_imports(root: Path) -> list[tuple[str, str, str]]:
    """(file, module, name) for every first-party `from … import name` that
    names a module the render lacks or a name that module does not bind. A
    conditional that prunes a def but not a test's import of it passes ruff
    and fails only at collection time; this is that check, without pytest.
    """
    roots = {PACKAGE: root / "src" / PACKAGE, "tests": root / "tests"}
    failures = []
    for path in python_files(root):
        for node in ast.walk(ast.parse(path.read_text())):
            if not isinstance(node, ast.ImportFrom) or node.module is None:
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
    # Cross-cutting: nothing empty, nothing unformatted, nothing unused.
    for directory in (p for p in root.rglob("*") if p.is_dir()):
        assert any(directory.iterdir()), (
            f"empty directory {directory.relative_to(root)}"
        )
    check = ruff(root, "check")
    assert check.returncode == 0, check.stdout + check.stderr
    fmt = ruff(root, "format", "--check")
    assert fmt.returncode == 0, fmt.stdout + fmt.stderr
    assert unresolved_first_party_imports(root) == []
    # testcontainers is needed by exactly the integration tests the chosen
    # backends keep; with every backend off it has no user.
    any_on = any(answers[key] != "none" for key in BACKEND)
    assert ("testcontainers" in dependencies) == any_on


@pytest.mark.parametrize("answers", COMBINATIONS, ids=combination_id)
def test_a_render_carries_only_the_backends_it_chose(cookies, answers) -> None:
    assert_invariant(render(cookies, **answers), answers)
