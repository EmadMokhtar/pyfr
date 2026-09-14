"""scripts/check_site_links.py against a hand-made site directory."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))

import check_site_links  # noqa: E402

SITE_URL = check_site_links.SITE_URL


def write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def built_site(tmp_path: Path) -> Path:
    site = tmp_path / "site"
    write(site / "index.html", '<h1 id="pyfr">PyFr</h1>')
    write(
        site / "contributing" / "index.html",
        '<h2 id="one-time-repository-settings">Settings</h2>',
    )
    write(
        site / "reference-service" / "runbook" / "index.html",
        '<h2 id="a-dependency-is-down">Down</h2>',
    )
    return site


def test_links_to_existing_pages_and_anchors_resolve(tmp_path: Path) -> None:
    site = built_site(tmp_path)
    page = write(
        tmp_path / "docs" / "index.md",
        f"See [the settings]({SITE_URL}contributing/#one-time-repository-settings),\n"
        f"[the runbook]({SITE_URL}reference-service/runbook/) and <{SITE_URL}>.\n"
        f"Prose can end with the site {SITE_URL}reference-service/runbook.\n",
    )
    assert check_site_links.unresolved([page], site) == []


def test_a_missing_page_and_a_missing_anchor_are_reported(tmp_path: Path) -> None:
    site = built_site(tmp_path)
    page = write(
        tmp_path / "docs" / "index.md",
        f"[gone]({SITE_URL}reference-service/reference/commands/)\n"
        f"[renamed]({SITE_URL}contributing/#working-on-the-template)\n",
    )
    problems = check_site_links.unresolved([page], site)
    assert len(problems) == 2
    assert "no page at" in problems[0]
    assert "reference/commands/index.html" in problems[0]
    assert "no element with id 'working-on-the-template'" in problems[1]


def test_other_hosts_and_relative_links_are_ignored(tmp_path: Path) -> None:
    site = built_site(tmp_path)
    page = write(
        tmp_path / "docs" / "index.md",
        "[relative](runbook.md#a-dependency-is-down)\n"
        "[github](https://github.com/EmadMokhtar/pyfr/blob/main/README.md)\n"
        "[another site](https://example.github.io/pyfr/contributing/)\n",
    )
    assert check_site_links.unresolved([page], site) == []


def test_main_walks_directories_and_exits_nonzero_on_a_problem(
    tmp_path: Path, capsys
) -> None:
    site = built_site(tmp_path)
    docs = tmp_path / "docs"
    write(docs / "ok.md", f"[ok]({SITE_URL}contributing/)\n")
    write(docs / "guides" / "bad.md", f"[bad]({SITE_URL}missing/)\n")
    assert check_site_links.main(["--site", str(site), str(docs)]) == 1
    out = capsys.readouterr().out
    assert "guides/bad.md" in out
    assert "1 cross-site link(s) do not resolve" in out

    (docs / "guides" / "bad.md").unlink()
    assert check_site_links.main(["--site", str(site), str(docs)]) == 0
    assert "Every cross-site link resolves" in capsys.readouterr().out


def test_main_refuses_to_run_without_a_built_site(tmp_path: Path, capsys) -> None:
    page = write(tmp_path / "docs" / "index.md", "nothing\n")
    assert check_site_links.main(["--site", str(tmp_path / "site"), str(page)]) == 1
    assert "run `just docs-build` first" in capsys.readouterr().out


def test_placeholders_in_prose_and_excluded_directories_are_skipped(
    tmp_path: Path,
) -> None:
    site = built_site(tmp_path)
    docs = tmp_path / "docs"
    write(
        docs / "contributing.md",
        f"A root page links `{SITE_URL}reference-service/<page>/#anchor` and\n"
        f"a moved page links `{SITE_URL}contributing/#…`.\n",
    )
    write(docs / "superpowers" / "plan.md", f"[gone]({SITE_URL}nowhere/)\n")
    files = check_site_links.markdown_files([docs], [docs / "superpowers"])
    assert files == [docs / "contributing.md"]
    assert check_site_links.unresolved(files, site) == []
    assert (
        check_site_links.main(
            ["--site", str(site), "--exclude", str(docs / "superpowers"), str(docs)]
        )
        == 0
    )
