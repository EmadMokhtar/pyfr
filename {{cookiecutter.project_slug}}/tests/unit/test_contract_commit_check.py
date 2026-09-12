"""The Conventional Commits half of the contract gate.

Spec 10.2: if oasdiff reports a breaking change and no commit in the range
is marked breaking, the build fails. These tests cover the parsing, which
is where this goes wrong -- oasdiff's half is already tested by its own
exit-code handling.

They also cover `default_base()`'s two resolution states -- a tag present,
and no tags at all -- against throwaway repositories built in `tmp_path`,
never against this repository's own history.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_contract_compatibility import default_base, message_is_breaking


def _run_git(cwd: Path, *args: str) -> str:
    # S603/S607: `git`, resolved via PATH, with a fixed argument list this
    # test constructs itself -- nothing here is untrusted input. The same
    # exception is already granted to scripts/* for the identical reason;
    # see the per-file-ignores comment in ruff.toml.
    completed = subprocess.run(  # noqa: S603
        ["git", *args],  # noqa: S607
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True,
    )
    return completed.stdout.strip()


def _init_repo(cwd: Path) -> None:
    _run_git(cwd, "init", "--quiet")
    # A throwaway identity: these commits never leave tmp_path, but `git
    # commit` refuses to run at all without SOME configured author.
    _run_git(cwd, "config", "user.email", "test@example.invalid")
    _run_git(cwd, "config", "user.name", "Test")


def _commit(cwd: Path, message: str) -> str:
    (cwd / "file.txt").write_text(message, encoding="utf-8")
    _run_git(cwd, "add", "-A")
    _run_git(cwd, "commit", "--quiet", "-m", message)
    return _run_git(cwd, "rev-parse", "HEAD")


def test_exclamation_after_the_type_is_breaking() -> None:
    assert message_is_breaking("feat!: drop the legacy field") is True


def test_exclamation_after_a_scope_is_breaking() -> None:
    assert message_is_breaking("feat(api)!: drop the legacy field") is True


def test_breaking_change_footer_is_breaking() -> None:
    message = (
        "feat(api): replace the status field\n"
        "\n"
        "BREAKING CHANGE: `status` is now an enum rather than a string.\n"
    )
    assert message_is_breaking(message) is True


def test_hyphenated_footer_is_breaking() -> None:
    """The specification allows BREAKING-CHANGE as a synonym."""
    message = "fix(api): tighten validation\n\nBREAKING-CHANGE: rejects empty.\n"
    assert message_is_breaking(message) is True


def test_an_ordinary_commit_is_not_breaking() -> None:
    assert message_is_breaking("fix(api): correct a typo in a description") is False


def test_the_words_in_prose_are_not_a_footer() -> None:
    """A footer is a line that STARTS with the token.

    Without this, a commit body explaining that a change is deliberately
    not a breaking change marks itself as one -- and the gate then passes
    for the next genuinely breaking change that mentions it in passing.
    """
    message = (
        "fix(api): widen an enum\n"
        "\n"
        "This is not a BREAKING CHANGE: widening accepts strictly more.\n"
    )
    assert message_is_breaking(message) is False


def test_an_exclamation_in_the_description_is_not_a_marker() -> None:
    assert message_is_breaking("fix: stop the parser exploding!") is False


def test_default_base_resolves_to_the_most_recent_tag(tmp_path: Path) -> None:
    """A release always leaves a tag, so the most recent one IS the window."""
    _init_repo(tmp_path)
    _commit(tmp_path, "chore: init")
    _commit(tmp_path, "feat: add a thing")
    _run_git(tmp_path, "tag", "v1.0.0")
    _commit(tmp_path, "fix: patch it")

    assert default_base(cwd=tmp_path) == "v1.0.0"


def test_default_base_falls_back_to_the_root_commit_with_no_tags(
    tmp_path: Path,
) -> None:
    """No tags means no release has happened yet, so the whole history counts.

    This is this repository's own state today -- `git tag -l` is empty --
    which is exactly why the fallback matters rather than being a purely
    theoretical branch.
    """
    _init_repo(tmp_path)
    root = _commit(tmp_path, "chore: init")
    _commit(tmp_path, "feat: add a thing")

    assert default_base(cwd=tmp_path) == root
