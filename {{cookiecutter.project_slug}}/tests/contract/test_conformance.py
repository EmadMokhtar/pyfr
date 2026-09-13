"""Schemathesis generates requests from the contract and checks the app.

Over ASGI, in-process: no server, no socket, no network. The schema is
read from the live app rather than from the committed openapi.json on
purpose — tests/unit/test_contract_drift.py already proves those two are
identical, and reading the app means a failure here is never explained
away as "the file is stale".
"""

from __future__ import annotations

import gc
import warnings

import schemathesis
from schemathesis.python.asgi import shutdown_lifespans

from {{ cookiecutter.package_name }}.main import create_app
from {{ cookiecutter.package_name }}.settings import Settings
from tests.conftest import no_app_env_vars

# `no_app_env_vars()` around an explicit, environment-free `Settings`,
# never a bare `create_app()`. This module calls `create_app()` at IMPORT
# time, before any fixture runs — including the session-scoped
# `_no_developer_app_env_vars` fixture in tests/conftest.py, which strips
# `APP_*` from the environment but only takes effect once pytest starts
# running fixtures, well after collection has already imported this
# module. A bare `create_app()` therefore calls `load_settings()`, which
# reads `.env` and every `APP_*` variable already in the process
# environment. Measured: with `APP_PAYMENT__BASE_URL` set — exactly what
# `.env.example` and `compose.yaml` both encourage a developer to set —
# Schemathesis generated a request that reached the real network and
# failed after two `stamina.retry_scheduled` attempts and a
# `ConnectError`, in direct violation of "no outbound request in a test
# ever reaches the network."
#
# `Settings(_env_file=None)` ALONE does not fix this: it only stops
# `Settings` reading a `.env` FILE, and pydantic-settings' environment-
# variable source still reads `os.environ` regardless — confirmed
# directly, `APP_PAYMENT__BASE_URL` still populated `settings.payment`
# with that argument alone and nothing else. `no_app_env_vars()` is what
# actually empties the `APP_*` namespace before `Settings` ever looks at
# it; see its docstring in tests/conftest.py.
with no_app_env_vars():
    app = create_app(Settings(_env_file=None))  # type: ignore[call-arg]


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
# without the fix below, `just test` failed
# tests/api/test_errors.py::test_a_domain_error_becomes_problem_details —
# a test with nothing to do with contracts — reproducibly, every run.
#
# `shutdown_lifespans()` plus `gc.collect()` force that GC pass here
# instead, during this module's own import — the one moment neither this
# directory's conftest.py nor pyproject.toml's global `filterwarnings`
# needs to cover. This does NOT fix the leak: the streams are still
# reported `Unclosed` at the instant they are reaped here, because
# `shutdown_lifespans()` cancels the lifespan task without closing the two
# anyio memory-object streams behind it — that is a gap in Schemathesis's
# ASGI transport, not in this codebase, and it stays open. What this
# controls is only WHEN the resulting warning fires: here, at import time,
# rather than at an unpredictable later point blamed on an unrelated test.
#
# `warnings.catch_warnings()` scoped to these three statements, with
# `ResourceWarning` filtered to "ignore", is what makes that safe. Verified
# directly (see the fix-round-1 section of this task's report for the
# experiment): CPython's `__del__` machinery calls `warnings.warn(...)`
# through the ordinary warnings-filter chain FIRST; only when the active
# filter says "error" — which pyproject.toml's `filterwarnings = ["error"]`
# does, session-wide — does that call raise, and only THEN, because
# raising out of `__del__` is not allowed, does CPython reroute the
# resulting exception to `sys.unraisablehook` (which is where pytest's own
# hook, installed at `pytest_configure`, queues it for later and blames
# whichever test's setup/call/teardown boundary is running when the queue
# is next drained). Filtering `ResourceWarning` to "ignore" for the
# duration of this block intercepts it at the FIRST step: `warnings.warn`
# returns without raising, so no exception is ever produced, so nothing
# ever reaches `sys.unraisablehook` — pytest's queue stays empty and no
# later, unrelated test can be blamed. A previous version of this comment
# claimed the opposite — that `warnings.catch_warnings()` could not reach
# this because the hook fires "before the warnings filtering machinery
# ever sees anything." That claim was disproven by direct experiment: with
# only the ini-level `filterwarnings = ["error"]` active and no further
# suppression, these three statements produce four `sys.unraisablehook`
# calls (two `MemoryObjectSendStream` / `MemoryObjectReceiveStream` pairs);
# wrapped in this `catch_warnings()` block instead, they produce zero,
# every time.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", ResourceWarning)
    schema = schemathesis.openapi.from_asgi("/openapi.json", app)
    shutdown_lifespans()
    gc.collect()


@schema.parametrize()
def test_api_conforms_to_its_own_contract(case: schemathesis.Case) -> None:
    case.call_and_validate()
