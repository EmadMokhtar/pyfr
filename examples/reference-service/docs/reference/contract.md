---
last_reviewed: 2026-09-12
covers:
  - openapi.json
  - scripts/check_contract_compatibility.py
---

# The API contract

`openapi.json` is committed at the root of the service, generated
from the code, never hand-edited. It is the contract: the thing a client, a
generated SDK, or another team's test suite is entitled to rely on.

A committed file that nothing checks is a file nobody trusts. Three gates
keep it honest — that the file matches the code, that the app actually
behaves the way the file says, and that a breaking change never ships
silently.

## Gate 1 — the file matches the code (drift)

`tests/unit/test_contract_drift.py` renders the OpenAPI document from the
live app and compares it, byte for byte, against the committed
`openapi.json`.

Byte comparison rather than a parsed comparison on purpose: a parsed check
can only say "these differ", where a byte diff shows up in a pull request as
an ordinary diff of `openapi.json` — which is the entire reason the file is
committed at all.

**Catches:** a route or a schema changed in the code with the committed
file left behind.

**Fix:** `just openapi` regenerates it from the app. Read the diff before
you commit it — it is your API change, stated completely, independent of
what you meant to change.

Lives in `tests/unit/`, and runs in the DEFAULT `just test` / `just check`
tier, unlike gate 2 below. It builds the app inside the test function, not
at import time, and calls only the synchronous `.openapi()` — no lifespan,
no HTTP generation, no Docker — so none of the reasons gate 2 needs its own
slower, separate tier apply to this one.

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

## Gate 3 — no breaking change ships unannounced

`scripts/check_contract_compatibility.py` runs
[oasdiff](https://github.com/oasdiff/oasdiff) — from its pinned image, so
checking a Python service's contract never requires a Go toolchain — against
the committed `openapi.baseline.json`, and keeps only the findings oasdiff
itself calls breaking: severity level 3, which oasdiff calls `error`. Levels
1 and 2 (`info`, `warning`) do not block.

A breaking change is not refused outright. The gate also reads the commit
messages in the range under test — `git log base..head` — and asks whether
any of them declares the break on purpose: a Conventional Commits subject
with `!` immediately before the colon (`feat!:`, `feat(api)!:`), or a
`BREAKING CHANGE:` (or `BREAKING-CHANGE:`) footer starting a line in the
commit body. A breaking change with a commit that says so passes; the
identical change with no commit marked breaking fails the build. The
failure message lists the specific oasdiff findings and tells you to
either undo the change or mark the commit breaking.

`--head` defaults to `HEAD`. `--base` defaults to the **most recent tag**
(`git describe --tags --abbrev=0`), falling back to the repository's
**first commit** when there are no tags at all — a copy of this repository
before its first release. Both are overridable on the command line.

The default is the most recent tag, and deliberately not `origin/main`:
`openapi.baseline.json` only moves at a release (`just contract-release`
below), so the window this half of the gate reads has to cover the same
span as the window the baseline diff already covers — since the last
release. `origin/main` cannot do that: it resets on every pull request
branch, so a breaking change marked `feat(api)!:` in one pull request
would clear the baseline diff for good, while the very next pull request's
range no longer contains that marking commit — and would fail the same
gate for a break someone already announced and shipped. A release always
leaves a tag behind and promotes the baseline in the same bump commit —
`.github/workflows/release.yml` does both — so the most recent tag names
exactly the same point the baseline was last promoted from.

```bash
just contract-gates
```

runs gate 2 (`pytest -m contract`, `test_conformance.py`) and then this
script. Gate 1 is deliberately NOT part of `contract-gates` — it already ran
as part of the default `just test` / `just check` tier, long before this
command exists to be typed; see gate 1's own section above. The script half
of `contract-gates` needs Docker, for the oasdiff image, and the committed
baseline — `just test-contract` alone needs neither.

`openapi.baseline.json` moves only at a release, never to silence a red
gate:

```bash
just contract-release
```

copies the current `openapi.json` over it. `release.yml` makes that
promotion inside the bump commit of every release it cuts, so nobody runs
it by hand. `just contract-release` works on this project's own tree.
Running it by hand to make `contract-gates` stop complaining *is* the
silent breaking change this gate exists to catch — it does not report
anything different afterwards, it simply has nothing left to compare
against.

This is also, deliberately, the same moment `--base`'s default moves to: a
release both promotes the baseline and leaves the tag that the *next*
release's window will start counting from — in one commit, made by one
workflow — which is exactly why the two halves of this gate stay in step
without either one needing to know about the other.

## The workflow

1. Change a route or a schema.
2. `just openapi`.
3. **Read the diff.** It is your API change, stated completely — including
   the parts you did not think of as "the change".
4. `just contract-gates`.
5. If it reports a breaking change, either undo it or mark the commit
   breaking — `feat!:` (or `feat(api)!:`) in the subject, or a `BREAKING
   CHANGE:` footer in the body — then run `just contract-gates` again to
   confirm. Marking a commit breaking is a statement that clients will
   have to act on the change, so mean it: don't reach for it just to make
   the gate go green.
