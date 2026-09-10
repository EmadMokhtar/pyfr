"""Cassette settings for every recorded test.

These tests run in the DEFAULT selection on purpose: replaying a cassette
needs no Docker and no network, so they are as fast and as portable as a
unit test. Only re-recording needs the stub, and that is `just test-record`.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

PAYMENT_STUB_URL = "http://localhost:9099"


@pytest.fixture(scope="module")
def vcr_cassette_dir(request: pytest.FixtureRequest) -> str:
    """Put recordings under tests/cassettes/, as spec 8.1 lays out, rather
    than beside the test module where pytest-recording puts them."""
    module = Path(request.node.path).stem
    return str(Path(__file__).resolve().parents[1] / "cassettes" / module)


@pytest.fixture(scope="module")
def vcr_config() -> dict[str, Any]:
    return {
        # Credentials must never land in a committed file. The list is
        # explicit rather than clever: a header not named here IS recorded,
        # so adding an authenticated upstream means adding its header here.
        "filter_headers": [
            "authorization",
            "cookie",
            "set-cookie",
            "idempotency-key",
        ],
        # Match on the body too. Without it, the authorised and declined
        # recordings — same method, same URL — are indistinguishable and
        # the first one always answers.
        "match_on": ["method", "scheme", "host", "port", "path", "query", "body"],
    }
