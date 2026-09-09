"""Schemathesis generates requests from the contract and checks the app.

Over ASGI, in-process: no server, no socket, no network. The schema is
read from the live app rather than from the committed openapi.json on
purpose — test_drift.py already proves those two are identical, and
reading the app means a failure here is never explained away as "the file
is stale".
"""

from __future__ import annotations

import gc
import sys

import schemathesis
from schemathesis.python.asgi import shutdown_lifespans

from reference_service.main import create_app

app = create_app()


# `from_asgi` below starts the app's ASGI lifespan (real requests through a
# real server would expect startup to have already run, so schemathesis
# runs it for real rather than faking readiness) and, by design, leaves it
# running afterwards: schemathesis's own pytest plugin calls
# `shutdown_lifespans()` again after every contract test's teardown, on the
# assumption that some *other* test in the same module will still want the
# lifespan warm. Nothing here does — this is the only test that needs it,
# and it needs it once, at import time, before pytest has even started
# collecting `-m contract` deselection.
#
# That matters because of a resourcewarning the tests/contract/conftest.py
# `contract` marker's per-item filter cannot reach. The two anyio streams
# behind a started lifespan are not freed by simple reference counting;
# closing them needs a full garbage-collection pass, and neither
# `from_asgi` nor `shutdown_lifespans` forces one. Left alone, that pass
# runs at some LATER point Python's GC scheduler picks — and
# pytest.PytestUnraisableExceptionWarning blames whichever test's
# setup/call/teardown boundary is running when it fires. Under `just
# test-contract` that is always another contract test, which the
# directory's conftest.py already ignores. Under plain `just test` the
# `contract` marker deselects every test below — but pytest still
# COLLECTS this module to know that, so `from_asgi` still runs, and the
# object it leaves behind still gets reaped mid-suite. Verified directly:
# without the three lines below, `just test` failed
# tests/api/test_errors.py::test_a_domain_error_becomes_problem_details —
# a test with nothing to do with contracts — reproducibly, every run.
#
# `shutdown_lifespans()` plus `gc.collect()` reap it deterministically
# here instead, during this module's own import, which is the one moment
# neither this directory's conftest.py nor pyproject.toml's global
# `filterwarnings` needs to cover. The `sys.unraisablehook` swap is what
# makes that safe: CPython calls the hook synchronously from inside
# `__del__`, before the `warnings` filtering machinery ever sees anything,
# so a plain `warnings.catch_warnings()` here would not catch it — pytest
# installs its OWN hook at `pytest_configure`, before collection starts,
# specifically to queue these for later and re-raise them as a warning
# next to whatever test is then running. Swapping in a no-op for this one,
# narrow, known cause and putting pytest's hook straight back afterwards
# empties that queue before it can be filled with something unrelated.
def _discard_unraisable(_: sys.UnraisableHookArgs) -> None:
    pass


_pytest_hook = sys.unraisablehook
sys.unraisablehook = _discard_unraisable
try:
    schema = schemathesis.openapi.from_asgi("/openapi.json", app)
    shutdown_lifespans()
    gc.collect()
finally:
    sys.unraisablehook = _pytest_hook


@schema.parametrize()
def test_api_conforms_to_its_own_contract(case: schemathesis.Case) -> None:
    case.call_and_validate()
