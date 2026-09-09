"""Applies the `contract` marker, and contains one third-party warning.

Every module in this directory gets the marker automatically, so no test
below has to remember it — forgetting it would put a conformance test back
into the default selection, which is the exact failure this tier exists to
avoid.
"""

from __future__ import annotations

from pathlib import Path

import pytest

_THIS_DIRECTORY = Path(__file__).resolve().parent


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """Mark everything in this directory `contract` automatically.

    A plain module-level `pytestmark` list — what this file had before —
    does NOT do this. pytest reads `pytestmark` off the test module
    itself (see `_pytest.mark.structures.get_unpacked_marks`), never off
    a sibling conftest.py, so a directory-level `pytestmark` is silently
    ignored, with no warning: confirmed empirically against this
    project's pinned pytest 9.1.1 by writing a two-file reproduction
    outside this repo and watching `-m contract` deselect the test
    anyway. `tests/integration/conftest.py` hits the identical problem
    for the `integration` marker and already solves it with this same
    hook; see its docstring for why the `_THIS_DIRECTORY in
    Path(item.path).resolve().parents` guard below is load-bearing rather
    than decorative — in short, this hook runs once against the WHOLE
    session's collected items, from every conftest.py that defines it, so
    an unconditional `item.add_marker(...)` here would mark the entire
    suite `contract` and turn `just test` into "match nothing" instead of
    running the unit and api tiers.
    """
    for item in items:
        if _THIS_DIRECTORY in Path(item.path).resolve().parents:
            item.add_marker(pytest.mark.contract)
            # Scoped to this directory ON PURPOSE, never to
            # pyproject.toml's global `filterwarnings`. The leak is in
            # Schemathesis's ASGI transport, not in our code — both
            # middlewares in api/middleware.py are plain ASGI callables
            # rather than BaseHTTPMiddleware subclasses, so the usual
            # Starlette explanation does not apply. Filtering it globally
            # would silence a genuine resource leak anywhere else in the
            # service, which is a real class of bug in an async
            # application holding a connection pool.
            item.add_marker(pytest.mark.filterwarnings("ignore::ResourceWarning"))
            item.add_marker(
                pytest.mark.filterwarnings(
                    "ignore::pytest.PytestUnraisableExceptionWarning"
                )
            )
