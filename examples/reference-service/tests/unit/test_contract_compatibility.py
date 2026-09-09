"""The compatibility gate's own rules, without Docker.

`breaking_changes` shells out to oasdiff and is exercised by
`just contract-gates`; what is worth unit-testing is the rule that decides
whether a version bump admits a breaking change, because getting it wrong
in the lenient direction silently disables the whole gate.
"""

from __future__ import annotations

import pytest

from scripts.check_contract_compatibility import Version, bump_is_sufficient


@pytest.mark.parametrize(
    ("baseline", "current", "sufficient"),
    [
        # Below 1.0.0 the MINOR number carries breaking changes.
        ("0.1.0", "0.2.0", True),
        ("0.1.0", "1.0.0", True),
        ("0.1.0", "0.1.1", False),
        ("0.1.0", "0.1.0", False),
        # At and above 1.0.0 it is the major.
        ("1.4.2", "2.0.0", True),
        ("1.4.2", "1.5.0", False),
        ("1.4.2", "1.4.3", False),
    ],
)
def test_which_bumps_admit_a_breaking_change(
    baseline: str, current: str, sufficient: bool
) -> None:
    assert (
        bump_is_sufficient(Version.parse(baseline), Version.parse(current))
        is sufficient
    )


def test_a_non_semantic_version_is_refused_rather_than_guessed() -> None:
    with pytest.raises(ValueError, match="not a semantic version"):
        Version.parse("1.2")
