"""The committed contract must match the code, byte for byte.

Bytes, not parsed structures. A parsed comparison can only say "these
differ"; a byte comparison makes the difference show up in the pull
request as an ordinary diff of openapi.json, which is the entire point of
committing it (spec 8.2, gate 1).

Lives in tests/unit/, not tests/contract/, and that placement is
deliberate rather than an oversight — see the comment on
test_the_committed_contract_matches_the_code below for why.
"""

from __future__ import annotations

import json
from pathlib import Path

from {{ cookiecutter.package_name }}.main import create_app
from {{ cookiecutter.package_name }}.settings import Settings
from tests.conftest import no_app_env_vars

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

    `no_app_env_vars()` around `create_app(Settings(_env_file=None))`,
    never a bare `create_app()`. `just openapi` runs this function
    directly with `python -c`, outside pytest entirely, so no fixture
    strips `APP_*` from the environment first — a bare `create_app()`
    would call `load_settings()`, which reads `.env` and whatever `APP_*`
    variables the shell already has. Measured: with `APP_SERVICE_NAME=zzz`
    set, a bare `create_app()` rendered `{"title": "zzz", ...}`.
    `Settings(_env_file=None)` alone does NOT fix this — confirmed
    directly, that argument only stops `Settings` reading a `.env` FILE,
    and pydantic-settings' environment-variable source still reads
    `os.environ` regardless, so `service_name` was still `"zzz"` with
    only that argument changed. `no_app_env_vars()` (see
    tests/conftest.py) is what actually empties the `APP_*` namespace
    first. Without it, `just openapi` would commit whatever a developer's
    own shell happened to have set, and this same function is also what
    `test_the_committed_contract_matches_the_code` below re-renders on
    every run — so the committed file would then fail the drift check for
    every OTHER developer, which is the milestone's central claim — that
    the contract is a deterministic function of the code, not of whoever
    happens to run `just openapi` — failing in practice.
    """
    with no_app_env_vars():
        document = create_app(Settings(_env_file=None)).openapi()  # type: ignore[call-arg]
    return json.dumps(document, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def test_the_committed_contract_matches_the_code() -> None:
    """Deselected by `-m contract` on purpose — this runs in the DEFAULT
    tier (`just test`, `just check`), unlike test_conformance.py.

    That difference between two tests that live one directory apart is
    deliberate, not an oversight: `render_openapi()` above builds the app
    fresh, INSIDE this function, at test-call time, never at import time —
    confirmed by reading it, and the reason this file was moved out of
    tests/contract/ in the first place. `test_conformance.py`'s slowness
    and its Schemathesis ASGI-transport ResourceWarning (see that module's
    own comment, and tests/contract/conftest.py) both come from generating
    and executing many requests against a real started lifespan; this test
    calls `.openapi()`, a synchronous schema dump with no lifespan, no
    generation and no Docker, so it costs about as much as any other unit
    test and none of the reasons the `contract` marker exists apply to it.
    """
    assert CONTRACT_PATH.exists(), (
        f"{CONTRACT_PATH.name} is missing. Run `just openapi` and commit it."
    )
    assert CONTRACT_PATH.read_text(encoding="utf-8") == render_openapi(), (
        "openapi.json is out of date. Run `just openapi` and commit the result "
        "— and read the diff before you do: it is the API change you just made, "
        "stated in full."
    )
