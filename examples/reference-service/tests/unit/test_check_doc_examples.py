"""The executable-documentation check (spec 10.3).

This check runs the `curl` examples a reader is meant to copy against a
real service, so a wrong example is caught as a failure rather than
merely as stale prose. That only works if three things hold, and each has
a test below: the opt-in marker is what decides what runs (not "every
bash fence"), a multi-command block genuinely fails when its FIRST command
fails (not just its last), and "nothing was found" is treated as a bug
rather than a silent pass.

No Docker and no network here. `find_examples()` is exercised against
synthetic markdown written into `tmp_path`, and `run()` is exercised with
`true`/`false` — real subprocesses, but ones that touch nothing outside
the interpreter itself.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_doc_examples import Example, find_examples, main, run


def test_find_examples_returns_only_the_marked_block(tmp_path: Path) -> None:
    """The marker, not the fence language, is what makes a block runnable.

    A document with two bash fences -- one preceded by `<!-- exec -->`,
    one not -- must yield exactly the marked one. Returning both would
    mean the check silently promotes every code sample a reader was never
    meant to run; returning neither would mean the marker does nothing.
    """
    doc = tmp_path / "page.md"
    doc.write_text(
        "# Page\n\n"
        "This block is illustration only and must never run:\n\n"
        "```bash\n"
        "rm -rf /\n"
        "```\n\n"
        "This one is marked and must run:\n\n"
        "<!-- exec -->\n"
        "```bash\n"
        "true\n"
        "```\n",
        encoding="utf-8",
    )

    examples = find_examples(tmp_path)

    assert len(examples) == 1
    assert examples[0].body == "true\n"


def test_reported_line_number_points_at_the_marker(tmp_path: Path) -> None:
    """A failure report is useless if it sends the reader to the wrong line.

    The marker sits on line 5 of this document; the fence and body follow.
    Pinning the exact number catches an off-by-one in the `count("\\n")`
    arithmetic, which would otherwise point one line into the fence or one
    line short of it -- close enough to look right in a quick glance and
    still send someone hunting through the wrong part of the file.
    """
    doc = tmp_path / "page.md"
    doc.write_text(
        "# Heading\n"
        "\n"
        "Some text before the example.\n"
        "\n"
        "<!-- exec -->\n"
        "```bash\n"
        "true\n"
        "```\n",
        encoding="utf-8",
    )

    [example] = find_examples(tmp_path)

    assert example.line == 5


def test_every_accepted_fence_language_is_found_and_others_are_not(
    tmp_path: Path,
) -> None:
    """`bash`, `shell` and `console` are accepted; nothing else is.

    A fifth, unlisted language (`python` here) checks the other direction:
    the regex's alternation is closed, not "bash or anything really" --
    which matters because a marked non-shell fence would be handed to
    `bash -c` and either fail confusingly or, worse, run as something
    other than what it displays.
    """
    doc = tmp_path / "page.md"
    doc.write_text(
        "<!-- exec -->\n```bash\ntrue\n```\n\n"
        "<!-- exec -->\n```shell\ntrue\n```\n\n"
        "<!-- exec -->\n```console\ntrue\n```\n\n"
        "<!-- exec -->\n```python\nTrue\n```\n",
        encoding="utf-8",
    )

    examples = find_examples(tmp_path)

    assert len(examples) == 3
    assert all(example.body == "true\n" for example in examples)


def test_superpowers_directory_is_excluded_by_path_parts_not_prefix(
    tmp_path: Path, monkeypatch
) -> None:
    """The archive is skipped even when the root argument is relative.

    `just docs-examples` invokes this script as
    `python3 scripts/check_doc_examples.py docs` today, but the root
    argument is just a path a caller supplies, and nothing stops a future
    caller from passing a RELATIVE one with leading `..` segments -- the
    way this same recipe did before the scripts moved into the template.
    A check written as `path.as_posix().startswith("superpowers")` passes
    on an absolute tmp_path fixture (where the string never starts with
    "superpowers" anyway) but is exactly the bug that a leading `../docs/`
    prefix would trigger: a string-prefix test never matches "superpowers"
    at all there, and the archive's stale exec-marked blocks start
    running. Testing `"superpowers" in path.parts` is what survives both
    the absolute fixture path and a relative one with leading `..`
    segments.
    """
    docs = tmp_path / "docs"
    (docs / "superpowers" / "plans").mkdir(parents=True)
    (docs / "superpowers" / "plans" / "archive.md").write_text(
        "<!-- exec -->\n```bash\nfalse\n```\n", encoding="utf-8"
    )
    (docs / "guide.md").write_text(
        "<!-- exec -->\n```bash\ntrue\n```\n", encoding="utf-8"
    )

    workdir = tmp_path / "service"
    workdir.mkdir()
    monkeypatch.chdir(workdir)

    examples = find_examples(Path("../docs"))

    assert [example.path for example in examples] == ["../docs/guide.md"]


def test_run_reports_success_for_a_zero_exit() -> None:
    """The baseline: an example that behaves passes."""
    ok, _output = run(Example(path="page.md", line=1, body="true"))
    assert ok is True


def test_run_reports_failure_for_a_nonzero_exit() -> None:
    """The baseline's mirror: an example that misbehaves fails."""
    ok, _output = run(Example(path="page.md", line=1, body="false"))
    assert ok is False


def test_run_fails_when_only_the_first_of_two_commands_fails() -> None:
    """The single most important test in this file.

    `bash -c` alone reports the exit status of its LAST command. A block
    of `curl <broken url>` followed by `echo done` would exit 0 under
    plain `bash -c`, because `echo` succeeds even though the `curl` before
    it failed -- the exact silent-pass failure mode spec 10.3 exists to
    catch. `run()` invokes `bash -euo pipefail`, where `-e` stops the
    script at the first failing command instead of running to the end and
    reporting the last one.

    `false` stands in for the broken command and `echo` for the harmless
    one that follows it, so this makes no network call and touches
    nothing outside the interpreter -- but the shape (fails, then a
    command that would itself succeed) is exactly a broken `curl` followed
    by a working `echo`.
    """
    ok, _output = run(Example(path="page.md", line=1, body="false\necho recovered"))
    assert ok is False


def test_main_returns_nonzero_when_a_marked_example_fails(tmp_path: Path) -> None:
    """The exit code is the signal CI acts on -- a passing summary line
    that still exits 0 would let a broken example merge anyway.
    """
    (tmp_path / "page.md").write_text(
        "<!-- exec -->\n```bash\nfalse\n```\n", encoding="utf-8"
    )

    assert main(["check_doc_examples.py", str(tmp_path)]) != 0


def test_main_returns_nonzero_when_no_marked_blocks_exist(tmp_path: Path) -> None:
    """ "No examples found" is treated as a bug, not a clean pass.

    A renamed marker or a documentation rewrite that deletes every
    `<!-- exec -->` block would otherwise leave `just docs-examples`
    reporting "0/0 passed" and exiting 0 -- a check that has quietly
    stopped checking anything, and looks identical to a check with
    nothing to report. This is the same failure mode
    `test_check_docs_freshness.py` guards against for its own warnings,
    except here it must be a hard failure rather than a warning, because
    this check is meant to gate CI.
    """
    (tmp_path / "page.md").write_text("# Nothing marked here.\n", encoding="utf-8")

    assert main(["check_doc_examples.py", str(tmp_path)]) != 0
