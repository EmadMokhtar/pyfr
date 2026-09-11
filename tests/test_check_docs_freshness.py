"""The documentation freshness and path-coupling warnings.

These never fail a build, which makes them easy to get silently wrong --
a check that always prints nothing looks identical to a check that has
nothing to report. These tests pin the difference.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from check_docs_freshness import (  # noqa: E402
    MAX_REVIEW_AGE_DAYS,
    Page,
    parse_frontmatter,
    stale_pages,
    undeclared_pages,
    uncovered_changes,
)


def test_parse_frontmatter_reads_both_keys() -> None:
    text = (
        "---\n"
        "last_reviewed: 2026-09-10\n"
        "covers:\n"
        "  - examples/reference-service/src/reference_service/settings.py\n"
        "---\n\n"
        "# Title\n"
    )
    meta = parse_frontmatter(text)
    assert meta["last_reviewed"] == dt.date(2026, 9, 10)
    assert meta["covers"] == [
        "examples/reference-service/src/reference_service/settings.py"
    ]


def test_parse_frontmatter_on_a_page_with_none() -> None:
    """Every page had no frontmatter before this task; absence is not an error."""
    assert parse_frontmatter("# Title\n\nBody.\n") == {}


def test_parse_frontmatter_ignores_a_horizontal_rule() -> None:
    """`---` mid-document is a rule, not a frontmatter fence."""
    assert parse_frontmatter("# Title\n\n---\n\nBody.\n") == {}


def test_a_page_reviewed_today_is_not_stale() -> None:
    today = dt.date(2026, 9, 10)
    page = Page(path="docs/index.md", last_reviewed=today, covers=[])
    assert stale_pages([page], today=today) == []


def test_a_page_past_the_maximum_age_is_stale() -> None:
    today = dt.date(2026, 9, 10)
    page = Page(
        path="docs/index.md",
        last_reviewed=today - dt.timedelta(days=MAX_REVIEW_AGE_DAYS + 1),
        covers=[],
    )
    assert [entry.path for entry in stale_pages([page], today=today)] == [
        "docs/index.md"
    ]


def test_a_page_with_no_review_date_is_not_reported_as_stale() -> None:
    """Missing is a different problem from old, and reported separately.

    Conflating them means the day someone adds a page with no frontmatter,
    it is reported as 'last reviewed 2000-01-01' -- a date that never
    existed, in a warning nobody can act on.
    """
    today = dt.date(2026, 9, 10)
    page = Page(path="docs/index.md", last_reviewed=None, covers=[])
    assert stale_pages([page], today=today) == []


def test_undeclared_pages_returns_only_pages_without_review_dates() -> None:
    """undeclared_pages() pins the second, separate review-date warning.

    Without this test, the `undeclared_pages()` filter can be deleted or
    inverted (e.g., to `if page.last_reviewed is not None`) and the suite
    stays green. A check that silently stops firing is the exact failure
    mode this script exists to prevent.

    This test must include both pages with and without `last_reviewed` to
    catch an inverted filter -- a test that passed only pages without dates
    would still pass if the filter were inverted to return everything.
    """
    page_with_date = Page(
        path="docs/with-date.md", last_reviewed=dt.date(2026, 9, 10), covers=[]
    )
    page_without_date = Page(
        path="docs/without-date.md", last_reviewed=None, covers=[]
    )
    result = undeclared_pages([page_with_date, page_without_date])
    assert [page.path for page in result] == ["docs/without-date.md"]


def test_a_covered_path_that_changed_without_the_page_is_reported() -> None:
    page = Page(
        path="docs/reference/configuration.md",
        last_reviewed=None,
        covers=["examples/reference-service/src/reference_service/settings.py"],
    )
    changed = {"examples/reference-service/src/reference_service/settings.py"}
    assert uncovered_changes([page], changed) == [
        (
            "docs/reference/configuration.md",
            "examples/reference-service/src/reference_service/settings.py",
        )
    ]


def test_a_covered_path_that_changed_with_the_page_is_not_reported() -> None:
    page = Page(
        path="docs/reference/configuration.md",
        last_reviewed=None,
        covers=["examples/reference-service/src/reference_service/settings.py"],
    )
    changed = {
        "examples/reference-service/src/reference_service/settings.py",
        "docs/reference/configuration.md",
    }
    assert uncovered_changes([page], changed) == []


def test_a_covers_entry_matches_a_directory_prefix() -> None:
    """`covers: [src/api/]` must match every file beneath it.

    Requiring one entry per file would make the frontmatter unmaintainable
    and guarantee it goes stale -- which is the thing being prevented.
    """
    page = Page(
        path="docs/reference/http-api.md",
        last_reviewed=None,
        covers=["examples/reference-service/src/reference_service/api/"],
    )
    changed = {"examples/reference-service/src/reference_service/api/orders.py"}
    assert uncovered_changes([page], changed) == [
        (
            "docs/reference/http-api.md",
            "examples/reference-service/src/reference_service/api/",
        )
    ]


def test_an_unrelated_change_reports_nothing() -> None:
    page = Page(
        path="docs/reference/http-api.md",
        last_reviewed=None,
        covers=["examples/reference-service/src/reference_service/api/"],
    )
    assert uncovered_changes([page], {"README.md"}) == []
