# The API contract

`openapi.json` is committed at the root of the reference service, generated
from the code, never hand-edited. It is the contract: the thing a client, a
generated SDK, or another team's test suite is entitled to rely on.

A committed file that nothing checks is a file nobody trusts. Three gates
keep it honest — that the file matches the code, that the app actually
behaves the way the file says, and that a breaking change never ships
silently.

## Gate 1 — the file matches the code (drift)

`tests/contract/test_drift.py` renders the OpenAPI document from the live
app and compares it, byte for byte, against the committed `openapi.json`.

Byte comparison rather than a parsed comparison on purpose: a parsed check
can only say "these differ", where a byte diff shows up in a pull request as
an ordinary diff of `openapi.json` — which is the entire reason the file is
committed at all.

**Catches:** a route or a schema changed in the code with the committed
file left behind.

**Fix:** `just openapi` regenerates it from the app. Read the diff before
you commit it — it is your API change, stated completely, independent of
what you meant to change.

## Gate 2 — the app honours what it publishes (conformance)

`tests/contract/test_conformance.py` uses
[Schemathesis](https://schemathesis.readthedocs.io/) to generate requests
from `openapi.json` and call the running app directly over ASGI — no
server, no socket, no network. It checks the reverse direction from gate 1:
not "does the file match the code" but "does the *behaviour* match the
file".

**Catches:** any place the contract promises something the app does not
actually do. Run it with:

```bash
just test-contract
```

It is a separate tier from `just test`, deselected by default — not only
because generated testing is slower than the unit and api tiers, but
because Schemathesis's ASGI transport leaks two `anyio` memory streams that
`filterwarnings = ["error"]` turns into failures blamed on unrelated tests.
`tests/contract/conftest.py` contains that damage to this tier alone.

One operation, `POST /api/v1/orders`, carries a documented exception in
`schemathesis.toml`: two of its rules — all lines sharing one currency, and
the line total fitting in `NUMERIC(14, 2)` — are relationships *between*
fields, which JSON Schema has no way to express. A generator working
strictly from the schema will always eventually produce a request that
satisfies every per-field constraint and still breaks one of those two, and
422 is the right answer to that request. The exception says so, by name,
with the reasoning in a comment — a reviewed exception, not a disabled
check. `not_a_server_error` is untouched: a 500 for that same input would
still fail the gate.

### What this gate found, before it existed

Writing this gate against the code that already existed found five real
defects, none of them contrived:

1. Three of the service's most common responses — a 405 on the wrong
   method, a 404 on an unknown path, a 400 on a body that is not valid
   UTF-8 — were answered by the framework's own default handler, as plain
   `{"detail": "..."}` over `application/json`. Every other error on this
   service is [Problem Details](errors.md); these three silently were not.
2. The published schema for `unit_amount` was more permissive than the
   model that actually validates it, in *both* branches of its rendered
   `anyOf`: the numeric branch dropped the decimal-place limit entirely, and
   the string branch's pattern was missing a closing `$`, so trailing junk
   after a valid-looking number satisfied it.
3. Two individually valid order lines — each within its own bounds — could
   multiply out to a total that overflowed what the database column can
   hold, and the service answered 500 for what was, from the caller's side,
   ordinary bad input.
4. Fixing defect 1 by hand-writing a response for the framework's
   `HTTPException` dropped the `Allow` header that RFC 9110 requires on a
   405 — caught by the same gate, in the same run that added it.
5. `{"quantity": true}` was accepted as `quantity: 1`. `bool` is a subclass
   of `int` in Python, so pydantic's default integer validation let a JSON
   boolean through where the contract's `type: integer` says it must not.

None of these needed an adversarial input. Schemathesis found each one by
generating ordinary, schema-shaped requests and comparing the answer against
what the contract already promised.

## Gate 3 — no breaking change ships without a version bump

`scripts/check_contract_compatibility.py` runs
[oasdiff](https://github.com/oasdiff/oasdiff) — from its pinned image, so
checking a Python service's contract never requires a Go toolchain — against
the committed `openapi.baseline.json`, and reports only the findings oasdiff
itself calls breaking.

A breaking change is not refused outright. It is cross-checked against the
version in `pyproject.toml`: below `1.0.0` a breaking change needs at least a
minor bump (`0.1.0` → `0.2.0`); at or above `1.0.0` it needs a major one. A
breaking change with a sufficient bump passes; the identical change with the
version left alone fails the build.

```bash
just contract-gates
```

runs gates 1 and 2 (`pytest -m contract`, which covers both
`test_drift.py` and `test_conformance.py`) and then this script. The script
half needs Docker, for the oasdiff image, and the committed baseline —
`just test-contract` alone needs neither.

`openapi.baseline.json` moves only at a release, never to silence a red
gate:

```bash
just contract-release
```

copies the current `openapi.json` over it. Running that to make
`contract-gates` stop complaining *is* the silent breaking change this gate
exists to catch — it does not report anything different afterwards, it
simply has nothing left to compare against.

## The workflow

1. Change a route or a schema.
2. `just openapi`.
3. **Read the diff.** It is your API change, stated completely — including
   the parts you did not think of as "the change".
4. `just contract-gates`.
5. If it reports a breaking change, either undo it or bump the version in
   `pyproject.toml` and run `just openapi` again.

## What M5 replaces here

The version cross-check in gate 3 is a placeholder for the Conventional
Commits range check the [roadmap](../roadmap.md) schedules for M5, once tags
and Commitizen exist to derive a version from commit history rather than
from a number someone has to remember to bump by hand. The oasdiff half —
the part that decides whether a change is breaking at all — stays exactly as
it is.
