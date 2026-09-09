"""Applies the `contract` marker, and contains one third-party warning.

Every module in this directory gets the marker automatically, so no test
below has to remember it — forgetting it would put a conformance test back
into the default selection, which is the exact failure this tier exists to
avoid.
"""

from __future__ import annotations

import pytest

# Scoped to this directory ON PURPOSE, never to pyproject.toml's global
# `filterwarnings`. The leak is in Schemathesis's ASGI transport, not in
# our code — both middlewares in api/middleware.py are plain ASGI
# callables rather than BaseHTTPMiddleware subclasses, so the usual
# Starlette explanation does not apply. Filtering it globally would
# silence a genuine resource leak anywhere else in the service, which is
# a real class of bug in an async application holding a connection pool.
pytestmark = [
    pytest.mark.contract,
    pytest.mark.filterwarnings("ignore::ResourceWarning"),
    pytest.mark.filterwarnings("ignore::pytest.PytestUnraisableExceptionWarning"),
]
