"""The hard documentation gate: source changed, no documented surface did.

The script is a heuristic on purpose, so these tests pin what it counts
as source, what it counts as documentation, and how the options reshape
both -- PyFr's own root run points every one of them somewhere else.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import check_docs_updated
from check_docs_updated import (
    DEFAULT_DOCS_PATHS,
    DEFAULT_SOURCE_PREFIXES,
    LABEL,
    source_changes,
    touches_docs,
)


def test_source_changes_keeps_only_the_watched_prefixes() -> None:
    paths = ["src/pkg/api/routes.py", "tests/unit/test_routes.py", "README.md"]
    assert source_changes(paths, DEFAULT_SOURCE_PREFIXES) == ["src/pkg/api/routes.py"]
    assert source_changes(paths, ("tests/",)) == ["tests/unit/test_routes.py"]
    assert source_changes(paths, ("src/", "tests/")) == paths[:2]


def test_touches_docs_with_the_defaults() -> None:
    assert touches_docs(["docs/runbook.md"], DEFAULT_DOCS_PATHS, None)
    assert touches_docs(["README.md"], DEFAULT_DOCS_PATHS, None)
    assert touches_docs(["mkdocs.yml"], DEFAULT_DOCS_PATHS, None)
    assert not touches_docs(["src/pkg/api/routes.py"], DEFAULT_DOCS_PATHS, None)
    # A prefix, not a substring: a file that merely mentions docs is not one.
    assert not touches_docs(["src/pkg/docs/x.py"], DEFAULT_DOCS_PATHS, None)


def test_an_excluded_prefix_does_not_count_as_documentation() -> None:
    plan = "docs/superpowers/plans/m7.md"
    assert touches_docs([plan], DEFAULT_DOCS_PATHS, None)
    assert not touches_docs([plan], DEFAULT_DOCS_PATHS, "docs/superpowers/")
    # The exclusion removes that subtree only; a real page still counts.
    assert touches_docs(
        [plan, "docs/index.md"], DEFAULT_DOCS_PATHS, "docs/superpowers/"
    )


@pytest.fixture
def changed(monkeypatch: pytest.MonkeyPatch):
    """Make `main` see a fixed changed-file list instead of asking git."""

    def install(paths: list[str]) -> None:
        monkeypatch.setattr(
            check_docs_updated, "changed_files", lambda base, head: paths
        )

    return install


def test_main_passes_when_no_source_changed(changed, capsys) -> None:
    changed(["README.md", "tests/unit/test_routes.py"])
    assert check_docs_updated.main(["base", "head"]) == 0
    assert capsys.readouterr().out == ""


def test_main_passes_when_source_and_docs_changed_together(changed) -> None:
    changed(["src/pkg/api/routes.py", "docs/reference/http-api.md"])
    assert check_docs_updated.main(["base", "head"]) == 0


def test_main_fails_and_names_the_source_and_the_surfaces(changed, capsys) -> None:
    changed(["src/pkg/api/routes.py", "src/pkg/settings.py", "uv.lock"])
    assert check_docs_updated.main(["base", "head"]) == 1
    out = capsys.readouterr().out
    assert "  - src/pkg/api/routes.py" in out
    assert "  - src/pkg/settings.py" in out
    assert "  - uv.lock" not in out
    for surface in DEFAULT_DOCS_PATHS:
        assert f"  - {surface}" in out
    assert f"`{LABEL}` label" in out


def test_main_options_reshape_source_and_docs(changed) -> None:
    # The shape of a run over a repository that vendors this project under
    # a subdirectory: that subdirectory's src/ is the source, and its docs
    # and README count as documentation beside the outer repository's own.
    nested_run = [
        "--source",
        "vendored/src/",
        "--docs",
        "docs/",
        "--docs",
        "README.md",
        "--docs",
        "mkdocs.yml",
        "--docs",
        "vendored/docs/",
        "--docs",
        "vendored/README.md",
        "--exclude-docs",
        "docs/superpowers/",
        "base",
        "head",
    ]
    source = "vendored/src/pkg/api/routes.py"

    # The default source prefix no longer counts: `src/` at the root is
    # not watched once --source names another tree.
    changed(["src/pkg/api/routes.py"])
    assert check_docs_updated.main(nested_run) == 0

    changed([source])
    assert check_docs_updated.main(nested_run) == 1

    changed([source, "vendored/README.md"])
    assert check_docs_updated.main(nested_run) == 0

    changed([source, "vendored/docs/runbook.md"])
    assert check_docs_updated.main(nested_run) == 0

    # A plan is documented-looking and excluded; it does not rescue the change.
    changed([source, "docs/superpowers/plans/m7.md"])
    assert check_docs_updated.main(nested_run) == 1


def test_main_lists_the_docs_paths_it_was_given(changed, capsys) -> None:
    changed(["lib/x.py"])
    argv = ["--source", "lib/", "--docs", "manual/", "--docs", "NOTES.md", "b", "h"]
    assert check_docs_updated.main(argv) == 1
    out = capsys.readouterr().out
    assert "  - manual/" in out
    assert "  - NOTES.md" in out
    assert "  - docs/" not in out
