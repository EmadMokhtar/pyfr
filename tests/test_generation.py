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

# Files where a literal {{ }} / {% %} is someone else's syntax, not ours,
# and is guarded with {% raw %} so Jinja leaves it alone: golang-migrate's
# CLI placeholders and the buildx/trivy recipes' own {{name}} interpolation
# (justfile), Prometheus's alert-label templating (slo.yml), sqlfluff's
# comment naming its own template markers (.sqlfluff), and a raw PromQL
# query string (test_observability_stack.py). None of these are cookiecutter
# collisions.
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
        if not any(marker in path.read_bytes() for marker in JINJA_MARKERS):
            continue
        # Grafana's own {{ }} legend syntax, copied verbatim on purpose
        # (spec section 7); anything else here is a collision.
        if relative.startswith("ops/grafana/"):
            continue
        if relative in RAW_GUARDED_FILES:
            continue
        offenders.append(relative)
    assert offenders == []
