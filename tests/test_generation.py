"""What every render must satisfy, whatever the answers.

PR 1 checks the default answers and the reference answers. PR 2 makes this
a matrix over the backend combinations.
"""

from __future__ import annotations

import subprocess
import sys
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
    for arguments in (
        ["format", "--check"],
        ["check", "--select", "E501"],
    ):
        completed = subprocess.run(
            [sys.executable, "-m", "ruff", *arguments, str(root)],
            cwd=root,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 0, completed.stdout + completed.stderr


def test_dashboards_are_copied_verbatim(cookies) -> None:
    result = cookies.bake()
    assert result.exit_code == 0, result.exception
    for name in ("runtime.json", "service-health.json", "slo.json"):
        rendered = result.project_path / "ops" / "grafana" / "dashboards" / name
        template_root = ROOT / "{{cookiecutter.project_slug}}"
        source = template_root / "ops" / "grafana" / "dashboards" / name
        assert rendered.read_bytes() == source.read_bytes()
