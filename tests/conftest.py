"""Shared pytest plumbing for the repository's own tests."""

from __future__ import annotations

import pytest


@pytest.hookimpl(wrapper=True, tryfirst=True)
def pytest_runtest_makereport(item: pytest.Item, call: pytest.CallInfo):
    # Records whether the test failed -- in its own body or in a fixture's
    # setup -- on the item itself, so a fixture's teardown can read
    # `request.node.failed`. The full-suite fixture keeps a rendered
    # project on disk only when its test failed: each render carries a
    # `.venv/` of a few hundred megabytes, and pytest keeps the last three
    # sessions' temporary directories.
    report = yield
    if report.when in ("setup", "call") and report.failed:
        item.failed = True  # type: ignore[attr-defined]
    return report
