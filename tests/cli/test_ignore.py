""".pyfr-update-ignore: gitignore syntax over the paths an update never touches."""

from __future__ import annotations

from pathlib import Path

import pytest

from pyfr_cli import answers, ignore
from pyfr_cli.versions import Version

RECORDED = answers.Answers(
    Path(".pyfr-answers.yml"),
    "https://example.com/pyfr",
    Version(0, 10, 0),
    {"package_name": "my_service", "database": "postgres"},
)


@pytest.mark.parametrize(
    ("pattern", "path", "expected"),
    [
        ("/README.md", "README.md", True),
        ("/README.md", "docs/adr/README.md", False),
        ("README.md", "docs/adr/README.md", True),
        ("/docs/adr/", "docs/adr/0001-x.md", True),
        ("/docs/adr/", "docs/adr-drafts/x.md", False),
        ("/src/my_service/domain/", "src/my_service/domain/deep/order.py", True),
        ("/src/my_service/domain/", "src/my_service/services/order.py", False),
        ("*.snap", "tests/unit/__snapshots__/a.snap", True),
        ("**/fixtures/", "tests/integration/fixtures/x.json", True),
        ("/.pyfr-update-ignore", ".pyfr-update-ignore", True),
    ],
)
def test_patterns_follow_gitignore(pattern: str, path: str, expected: bool) -> None:
    assert ignore.Ignore([pattern]).matches(path) is expected


def test_comments_blank_lines_and_negation() -> None:
    spec = ignore.Ignore.from_text("# yours\n\n/docs/*.md\n!/docs/index.md\n")
    assert spec.matches("docs/runbook.md")
    assert not spec.matches("docs/index.md")
    assert not spec.matches("docs/reference/commands.md")


def test_a_hash_after_a_pattern_is_part_of_the_pattern() -> None:
    # gitignore has no inline comments; the default keeps comments on their
    # own lines for exactly this reason (spec section 5.2).
    spec = ignore.Ignore.from_text("/README.md   # yours\n")
    assert not spec.matches("README.md")


def test_default_covers_the_spec_s_list_and_ignores_itself() -> None:
    spec = ignore.Ignore.from_text(ignore.default_text("my_service", "postgres"))
    for path in (
        ".pyfr-answers.yml",
        ".pyfr-update-ignore",
        "README.md",
        "CHANGELOG.md",
        "uv.lock",
        "migrations/000001_init.up.sql",
        "schema.sql",
        "openapi.json",
        "openapi.baseline.json",
        "docs/adr/0001-x.md",
        "src/my_service/domain/order.py",
        "src/my_service/services/orders.py",
        "src/my_service/api/v1/orders.py",
    ):
        assert spec.matches(path), path
    for path in (
        "pyproject.toml",
        "justfile",
        "src/my_service/api/health.py",
        "src/my_service/infrastructure/db/engine.py",
        "tests/unit/test_settings.py",
        ".github/workflows/ci.yml",
        "docs/reference/commands.md",
    ):
        assert not spec.matches(path), path


def test_default_drops_the_schema_lines_without_postgres() -> None:
    text = ignore.default_text("my_service", "none")
    assert "migrations/" not in text
    assert "schema.sql" not in text
    assert "/src/my_service/domain/" in text


def test_load_prefers_the_project_file(tmp_path: Path) -> None:
    (tmp_path / ignore.FILE).write_text("/ruff.toml\n")
    spec, from_file = ignore.load(tmp_path, RECORDED)
    assert from_file
    assert spec.matches("ruff.toml")
    assert not spec.matches("README.md")


def test_load_falls_back_to_the_default_for_the_recorded_answers(
    tmp_path: Path,
) -> None:
    spec, from_file = ignore.load(tmp_path, RECORDED)
    assert not from_file
    assert spec.matches("README.md")
    assert spec.matches("migrations/000001_init.up.sql")
    assert spec.matches("src/my_service/domain/order.py")


def test_install_copies_the_render_s_file_to_a_project_without_one(
    tmp_path: Path,
) -> None:
    render, project = tmp_path / "render", tmp_path / "project"
    render.mkdir()
    project.mkdir()
    (render / ignore.FILE).write_text("/README.md\n")
    assert ignore.install(render, project)
    assert (project / ignore.FILE).read_text() == "/README.md\n"


def test_install_does_nothing_when_the_render_has_no_file(tmp_path: Path) -> None:
    render, project = tmp_path / "render", tmp_path / "project"
    render.mkdir()
    project.mkdir()
    assert not ignore.install(render, project)
    assert not (project / ignore.FILE).exists()


def test_install_leaves_the_project_s_own_file_alone(tmp_path: Path) -> None:
    render, project = tmp_path / "render", tmp_path / "project"
    render.mkdir()
    project.mkdir()
    (render / ignore.FILE).write_text("/README.md\n")
    (project / ignore.FILE).write_text("# ours\n/ruff.toml\n")
    assert not ignore.install(render, project)
    assert (project / ignore.FILE).read_text() == "# ours\n/ruff.toml\n"
