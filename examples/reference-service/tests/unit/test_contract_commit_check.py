"""The Conventional Commits half of the contract gate.

Spec 10.2: if oasdiff reports a breaking change and no commit in the range
is marked breaking, the build fails. These tests cover the parsing, which
is where this goes wrong -- oasdiff's half is already tested by its own
exit-code handling.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_contract_compatibility import message_is_breaking


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
