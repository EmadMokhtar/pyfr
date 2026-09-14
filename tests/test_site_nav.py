"""Every page in a docs/ tree is reachable from its site's nav.

`mkdocs build --strict` fails on a nav entry whose page is missing, but a
page that exists and is in no nav is one INFO line nobody reads: it
builds, it is published, and nothing links to it. Both sites get the
check, and so does a render with every backend off, whose nav has lost
the pruned decision records and must have lost nothing else.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
EXAMPLE = ROOT / "examples" / "reference-service"
# Not pages: the design archive (the root mkdocs.yml excludes it from the
# build) and the decision-record template, copied and never read on the
# site.
NOT_PAGES = ("superpowers/", "adr/template.md")


class Loader(yaml.SafeLoader):
    """Tolerates the `!ENV [NAME, default]` tag MkDocs resolves itself."""


def env_default(loader: Loader, node: yaml.SequenceNode) -> object:
    return loader.construct_sequence(node)[-1]


Loader.add_constructor("!ENV", env_default)


def nav_pages(mkdocs_yml: Path) -> set[str]:
    pages: set[str] = set()

    def walk(node: object) -> None:
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)
        elif isinstance(node, str) and node.endswith(".md"):
            pages.add(node)

    walk(yaml.load(mkdocs_yml.read_text(), Loader=Loader)["nav"])  # noqa: S506
    return pages


def pages_missing_from_nav(root: Path) -> list[str]:
    docs = root / "docs"
    on_disk = {path.relative_to(docs).as_posix() for path in docs.rglob("*.md")}
    return sorted(
        page
        for page in on_disk - nav_pages(root / "mkdocs.yml")
        if not page.startswith(NOT_PAGES)
    )


def test_pyfr_site_lists_every_page() -> None:
    assert pages_missing_from_nav(ROOT) == []


def test_the_reference_service_site_lists_every_page() -> None:
    assert pages_missing_from_nav(EXAMPLE) == []


def test_a_render_with_every_backend_off_lists_every_page(
    cookies, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("PYFR_REGEN", "1")
    result = cookies.bake(
        extra_context={"database": "none", "cache": "none", "object_storage": "none"}
    )
    assert result.exit_code == 0, result.exception
    assert pages_missing_from_nav(result.project_path) == []


def test_the_helper_names_an_orphan(tmp_path: Path) -> None:
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "index.md").write_text("# Home\n")
    (tmp_path / "docs" / "lost.md").write_text("# Lost\n")
    (tmp_path / "mkdocs.yml").write_text(
        "site_name: x\nrepo_url: !ENV [REPO_URL, https://example.com]\n"
        "nav:\n  - Home: index.md\n"
    )
    assert pages_missing_from_nav(tmp_path) == ["lost.md"]
