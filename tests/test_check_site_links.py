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


REPOSITORY_URL = check_site_links.REPOSITORY_URL


def checkout(tmp_path: Path) -> Path:
    root = tmp_path / "repo"
    write(root / "{{cookiecutter.project_slug}}" / "docs" / "runbook.md", "# Runbook\n")
    write(root / "docs" / "superpowers" / "plans" / "m6.md", "# Plan\n")
    write(root / "README.md", "# PyFr\n")
    return root


def test_repository_links_that_name_a_checked_out_path_resolve(tmp_path: Path) -> None:
    site = tmp_path / "site"
    # An edit link as Material writes it from the nested build's EDIT_URI:
    # the template body's braces percent-encoded, one link per page.
    write(
        site / "reference-service" / "runbook" / "index.html",
        f'<a href="{REPOSITORY_URL}edit/main/%7B%7Bcookiecutter.project_slug%7D%7D'
        '/docs/runbook.md">Edit</a>\n'
        f'<a href="{REPOSITORY_URL}blob/main/docs/superpowers/plans/m6.md#design">'
        "Full reasoning</a>\n"
        f'<a href="{REPOSITORY_URL}tree/main/docs/superpowers/">the archive</a>\n'
        f'<a href="{REPOSITORY_URL}blob/main/README.md?plain=1">plain</a>\n',
    )
    assert check_site_links.unresolved_repository_links(site, checkout(tmp_path)) == []


def test_a_repository_link_to_a_missing_path_is_reported_once(tmp_path: Path) -> None:
    site = tmp_path / "site"
    gone = f"{REPOSITORY_URL}edit/main/docs/runbook.md"
    for page in ("runbook", "glossary"):
        write(
            site / "reference-service" / page / "index.html",
            f'<a href="{gone}">Edit</a>\n'
            f'<a href="{REPOSITORY_URL}blob/main/README.md">fine</a>\n',
        )
    problems = check_site_links.unresolved_repository_links(site, checkout(tmp_path))
    # The same edit prefix is broken on every page; naming it once, on the
    # first page found, is enough to fix it.
    assert len(problems) == 1
    assert "glossary/index.html" in problems[0]
    assert gone in problems[0]
    assert "docs/runbook.md" in problems[0]


def test_other_repository_urls_and_placeholders_are_ignored(tmp_path: Path) -> None:
    site = tmp_path / "site"
    write(
        site / "index.html",
        f'<a href="{REPOSITORY_URL}">the repository</a>\n'
        f'<a href="{REPOSITORY_URL}issues/48">an issue</a>\n'
        '<a href="https://github.com/EmadMokhtar/other/blob/main/nowhere.md">x</a>\n'
        f"<code>{REPOSITORY_URL}blob/main/&lt;path&gt;</code>\n"
        f"<code>{REPOSITORY_URL}edit/main/…</code>\n",
    )
    assert check_site_links.unresolved_repository_links(site, checkout(tmp_path)) == []


def test_main_checks_repository_links_only_when_given_a_repo_root(
    tmp_path: Path, capsys
) -> None:
    site = built_site(tmp_path)
    write(
        site / "reference-service" / "runbook" / "index.html",
        f'<a href="{REPOSITORY_URL}edit/main/nowhere/runbook.md">Edit</a>\n',
    )
    page = write(tmp_path / "docs" / "index.md", f"[ok]({SITE_URL}contributing/)\n")
    root = checkout(tmp_path)

    assert check_site_links.main(["--site", str(site), str(page)]) == 0

    argv = ["--site", str(site), "--repo-root", str(root), str(page)]
    assert check_site_links.main(argv) == 1
    out = capsys.readouterr().out
    assert "nowhere/runbook.md" in out
    assert "1 repository link(s) name nothing" in out

    write(root / "nowhere" / "runbook.md", "# Moved\n")
    assert check_site_links.main(argv) == 0
    out = capsys.readouterr().out
    assert "Every cross-site link resolves" in out
    assert "every repository link names a path" in out


def test_main_refuses_a_repo_root_that_does_not_exist(tmp_path: Path, capsys) -> None:
    site = built_site(tmp_path)
    page = write(tmp_path / "docs" / "index.md", "nothing\n")
    argv = ["--site", str(site), "--repo-root", str(tmp_path / "gone"), str(page)]
    assert check_site_links.main(argv) == 1
    assert "is not a directory" in capsys.readouterr().out
