"""The committed contract must match the code, byte for byte.

Bytes, not parsed structures. A parsed comparison can only say "these
differ"; a byte comparison makes the difference show up in the pull
request as an ordinary diff of openapi.json, which is the entire point of
committing it (spec 8.2, gate 1).
"""

from __future__ import annotations

import json
from pathlib import Path

from reference_service.main import create_app

CONTRACT_PATH = Path(__file__).resolve().parents[2] / "openapi.json"


def render_openapi() -> str:
    """The one place that decides how the contract is serialised.

    `sort_keys=True` so the file has a stable order independent of how
    FastAPI happens to build the dict; `ensure_ascii=False` so a non-ASCII
    description stays readable in the diff rather than becoming escape
    sequences; a trailing newline because every other text file here has
    one and pre-commit's end-of-file-fixer would add it anyway.

    Verified byte-stable across two separate processes — see the plan's
    Verified Fact 2 — which is what makes a byte comparison legitimate.
    """
    document = create_app().openapi()
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_the_committed_contract_matches_the_code() -> None:
    assert CONTRACT_PATH.exists(), (
        f"{CONTRACT_PATH.name} is missing. Run `just openapi` and commit it."
    )
    assert CONTRACT_PATH.read_text(encoding="utf-8") == render_openapi(), (
        "openapi.json is out of date. Run `just openapi` and commit the result "
        "— and read the diff before you do: it is the API change you just made, "
        "stated in full."
    )
