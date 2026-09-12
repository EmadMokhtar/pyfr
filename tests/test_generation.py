"""What every render must satisfy, whatever the answers.

PR 1 checks the default answers and the reference answers. PR 2 makes this
a matrix over the backend combinations.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml  # noqa: F401 -- unused until Task 8 adds the reference-answers case

ROOT = Path(__file__).resolve().parent.parent
REFERENCE_ANSWERS = ROOT / "tests" / "reference-answers.yaml"

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


def test_no_template_syntax_survives_the_default_render(cookies) -> None:
    result = cookies.bake()
    assert result.exit_code == 0, result.exception
    offenders = []
    for path in files_under(result.project_path):
        relative = path.relative_to(result.project_path).as_posix()
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
