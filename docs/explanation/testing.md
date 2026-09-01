# Testing strategy

M0 ships 102 tests that run in about three seconds, with no containers and no
network.

```bash
just test
```

## The layout

```
tests/
  unit/    domain and services. No input or output. Milliseconds.
  api/     the app over ASGI: routes, middleware, error handling.
  fakes.py hand-written test doubles.
  conftest.py shared fixtures.
```

Later milestones add `integration/` (real PostgreSQL, Redis and MinIO started
in Docker for the test session), `contract/` (generated requests checked
against the published API contract), and `cassettes/` (recorded outbound HTTP
responses, replayed offline).

## Unit tests carry the weight

Because the domain layer imports nothing but Pydantic, business rules are
tested with no database, no event loop, and no fixtures. That is the practical
payoff of the [layering](layers.md), and it gives a useful diagnostic:

> If a unit test needs a container, a layer boundary has leaked.

Tests of the api layer call the application directly over ASGI — the interface
between a Python web server and an application — so no network socket is
opened and no port is bound. They are fast enough to run on every save.

## Property-based testing

Some tests use [Hypothesis](https://hypothesis.readthedocs.io/), which
generates hundreds of random valid inputs and checks that a rule holds for all
of them, instead of testing three examples somebody thought of.

It suits the domain models well, because their rules are stated as properties
already. "No sequence of valid operations produces an `Order` whose total
disagrees with its lines" is one short test that covers cases nobody would
think to write by hand.

When Hypothesis finds a failure it *shrinks* it — it searches for the smallest
input that still fails, so you get a two-line reproduction rather than the
random 40-field object it happened to find first.

## Warnings are errors

The pytest configuration sets `filterwarnings = ["error"]`. Any warning raised
during a test run fails that test.

A deprecation warning is a dated notice that something will break. Left as
output, it scrolls past for two years and then becomes an outage on a routine
upgrade. Turned into a failure, it gets handled on the day it appears.

There is exactly one exception, and it is narrow on purpose: Starlette's test
client emits a deprecation warning about its own use of `httpx`. It is
suppressed by its precise message and category, not by a blanket
`ignore::DeprecationWarning` — which would silently hide the *next* warning
instead of surfacing it.

## Fakes, not mocks

Test doubles are hand-written classes in `tests/fakes.py` that implement the
same [port](layers.md) as the real adapter.

A fake in-memory repository is a few lines and behaves like a repository: save
then get returns what you saved. A mock configured to return a value proves
only that your code called the method you told it to call. When the real
adapter's behaviour changes, the fake is wrong in a way a test can catch, and
the mock is wrong in a way nothing can catch.

## What is not measured yet

Coverage thresholds and mutation testing arrive in later milestones.

Mutation testing introduces small deliberate bugs into the source — `>` becomes
`>=`, `True` becomes `False` — and re-runs the tests. A mutation that survives
proves the tests never actually checked that behaviour. It measures whether
tests *assert*, where coverage measures only whether lines *executed*. It is
the stronger of the two signals, and the documentation says so plainly
wherever both are reported.

## Your `.env` is kept out of the tests

The `justfile` sets `dotenv-load := true`, so your own `.env` enters the
environment of every recipe — including `just test`. Without a guard, a test
that claims to check "the defaults, with no environment set" would actually be
checking *your* `.env`, and would pass only because the shipped
`.env.example` happens to match the defaults.

A session-wide fixture in `conftest.py` strips every `APP_*` variable from the
environment before any test runs, and restores them afterwards. So tests see
the real defaults, and a colleague whose `.env` differs from yours does not get
a confusing unrelated failure.

Note that building settings with no `.env` file is *not* sufficient on its
own: that only stops the settings loader reading a file, and does nothing
about `APP_*` variables already in the environment by the time pytest starts.

## Testing note: `caplog` does not work

Logging setup clears the root logger's handlers, which also removes the one
pytest's logging plugin installs. Any test that builds the application gets
nothing in `caplog`.

Assert on captured standard output instead. See
[Logging](../reference/logging.md#testing-note-caplog-does-not-work).
