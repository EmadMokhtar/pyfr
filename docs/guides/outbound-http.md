# Outbound HTTP calls

The reference service calls one outbound dependency: a payment provider,
authorising a card before an order is accepted. This guide describes the
pattern that call is built on — a shared client, a narrow retry rule, and a
hand-written circuit breaker — so that a second outbound integration (a
shipping quote, a fraud check, a stock lookup) can reuse it instead of
reinventing it.

`infrastructure/http/payment_gateway.py` is the worked example throughout.
Its own docstring states the shape in three words:

```
breaker( retry( one HTTP request ) )
```

The breaker sits outside the retries, and the ordering is the design, not
an accident: retries are attempts at *one* logical call, so three retries
against a dead dependency must count as one failure against the breaker.
Nested the other way round, the breaker would open at a third of its
configured threshold and nobody reading its settings would know why.

## The shared client

`infrastructure/http/client.py` builds one `httpx.AsyncClient` per process,
in the composition root, closed at shutdown — never one per request. A
fresh client per call throws away the connection pool, so every outbound
request would pay a new TCP and TLS handshake, and nothing would bound how
many sockets the service opens.

Four timeout phases are set explicitly — connect, read, write, and the time
spent waiting for a free connection from the pool:

```python
httpx.Timeout(
    connect=settings.connect_timeout_seconds,
    read=settings.read_timeout_seconds,
    write=settings.write_timeout_seconds,
    pool=settings.pool_timeout_seconds,
)
```

`httpx.Timeout(5.0)` would set all four to the same number in one call.
Writing them out is what makes a reviewer notice if one is ever dropped —
and the pool timeout is the one people forget: with the pool exhausted, a
request queues *here*, before a socket is even opened, and an unbounded
wait turns one slow dependency into a stalled service just as effectively
as an unbounded read timeout would. Every field is documented in
[Configuration](../reference/configuration.md#variables) under
`APP_PAYMENT__HTTP__*`.

## The retry rule, and why it is narrow

Skim this code and the obvious assumption is "retry on failure". That is
not the rule, and the gap between the assumption and the rule is the
reason this section exists.

The actual rule, stated in `is_retryable()`'s own docstring: **can this
request have been delivered?** Not "did it fail" — a payment gateway can
fail *after* delivering a request perfectly well, and retrying a delivered
request is a second charge.

What counts as "never delivered", and is therefore safe to retry:

| Case | Why it is safe |
| --- | --- |
| `ConnectError` / `ConnectTimeout` | No socket to the gateway ever opened. |
| `PoolTimeout` | Failed waiting for a connection from *our own* pool — before any socket to the gateway opens, so nothing was submitted either. |
| `429 Too Many Requests` | Rejected at the edge, before the gateway looked at what was behind it. |
| `503 Service Unavailable` | The gateway is declaring itself unable to handle requests at all. |

What is excluded, deliberately, and stays excluded even though it looks
like an oversight:

- **`ReadTimeout`.** The gateway may have taken the payment and simply been
  slow to say so. Retrying that is the double charge this module exists to
  prevent.
- **`WriteTimeout`.** The request was partially or wholly on the wire when
  the deadline hit — whether the gateway received all of it is exactly as
  unknowable as whether a slow responder already processed it.
- **502 Bad Gateway and 504 Gateway Timeout.** Both mean the request *got
  there*: the gateway forwarded it and either could not make sense of the
  answer (502) or got no timely one (504). That is the identical ambiguity
  a `ReadTimeout` carries, wearing a status code instead of an exception.
  It is tempting to lump these in with 429 and 503 because all four "smell
  like" transient gateway trouble — they are not the same kind of trouble.

Making read and write timeouts safe to retry needs an idempotency key the
gateway itself honours on every attempt — the next section covers the one
this client already sends, and why sending it is not the same thing as
this problem being solved. That is scheduled for M9, not M3; see the
roadmap's M9 row.

A decline is handled separately from both of these, and on purpose:
`PaymentDeclinedError` — a 402 the gateway returned on purpose, with a
reason — is a **successful call with a negative answer**, not a failure.
It never retries and never counts against the breaker below. A card being
declined says nothing about whether the gateway is healthy.

## The breaker's three states

`infrastructure/http/breaker.py` is eighty lines, written rather than
depended on. Two asyncio-native circuit breakers exist on PyPI, and both
were last released in 2021 and 2022; the one package still actively
maintained, `pybreaker`, offers Tornado coroutines rather than `await`.
Eighty lines this service's own tests cover is the smaller long-term cost.

```
CLOSED  --[consecutive failures reach the threshold]--> OPEN
OPEN    --[the cool-down window elapses]--------------> HALF_OPEN
HALF_OPEN --[the probe succeeds]----------------------> CLOSED
HALF_OPEN --[the probe fails]--------------------------> OPEN
```

- **Closed.** Calls go through. A failure increments a counter; a success
  resets it to zero.
- **Open.** The threshold was reached. Every call is refused immediately,
  with `CircuitOpenError`, and the dependency is not contacted at all — a
  slow dependency that is not even asked cannot also consume every worker
  this service has.
- **Half-open.** The cool-down window has elapsed. Exactly *one* call is
  admitted as a probe; every other caller arriving during that same moment
  is refused, not sent at a dependency that has not yet proved it
  recovered. The probe succeeding closes the circuit; failing reopens it
  immediately, without waiting for a fresh run at the full failure
  threshold — the dependency has already shown it is unwell.

The state is derived from the clock on every read, never stored: nothing
has to notice the cool-down window expiring and flip a flag, so the
half-open transition simply happens the moment it is checked.

`CircuitOpenError` is deliberately its own type, distinct from whatever the
dependency itself raises: "we refused to try" and "it did not answer" are
different facts, and the adapter logs them under different event names
even though both become the same 503 to the caller — see
[Errors](../reference/errors.md).

There is deliberately **no readiness check registered for the payment
provider.** `/readyz` removing this instance from load balancing because
someone else's API is slow would turn their outage into this service's own
— and the breaker already handles that case correctly, by refusing calls
instantly instead of piling requests up behind a dependency that is down.

## The idempotency key

Every authorisation request carries an `Idempotency-Key` header, set to the
order's own id, generated once before the first attempt and unchanged
across every retry of that attempt. A gateway that honours it will not
authorise the same order twice, which is what makes the connect-phase and
pool-timeout retries above safe even against a gateway that only
*sometimes* honours the key.

**Be precise about what this key protects.** It covers retries *this
service* makes, internally, while trying to get one `PlaceOrder` call to
the gateway. It says nothing about a caller retrying its own
`POST /api/v1/orders` request — each such retry generates a fresh order id
and authorises a fresh payment. An inbound idempotency key, so a client's
own retry of that request is safe too, is the "idempotency keys" line in
the roadmap's M9 row: excluded from M3, not forgotten.

## Testing without a real upstream

`tests/recorded/test_payment_gateway_recorded.py` replays recorded HTTP
responses from `tests/cassettes/`, using
[VCR](../glossary.md) via pytest-recording. They run in the default `just
test` selection — replaying a cassette needs no Docker and no network, so
they are as fast and as portable as a unit test.

**Be plain about what a cassette does and does not prove.** The recordings
were made once, against `ops/payment-stub/`, a local
[WireMock](https://wiremock.org/) stub — two declarative JSON files that
answer an authorisation and a decline. That stub is static. Nothing about
it changes on its own, ever, so replaying it again next year proves
exactly what it proved the day it was recorded: that this adapter still
parses that wire format correctly, and nothing else.

**What the cassettes are good for:** keeping this tier fast and offline,
and catching a *code* regression in how the adapter builds a request or
reads a response.

**What they cannot do, at all: detect the real provider changing.** If the
actual payment provider renames a field, changes a status code, or
tightens a validation rule, every cassette-backed test keeps passing,
because nothing here ever asks the real provider anything. A reader who
believes these tests guard against upstream drift is worse off than one
who was told plainly that they do not — so: they do not.

Re-recording is manual today, `just test-record`, against the same local
stub — it re-proves the same thing, on demand, rather than on a schedule.
A weekly job that re-records against whatever the real provider currently
does, and fails the build when a cassette changes underneath it, is M5
work. Until then, this gap is a property of the test suite that a reader
should know about, not a defect to silently work around.

## The gap this milestone does not close: authorise, then save

`services/order.py`'s `PlaceOrder` authorises the payment **before**
saving the order. The other ordering — save first, authorise second —
leaves an order row behind for every declined card, for someone to notice
and clean up later. Authorising first avoids that, at the cost of a
narrower, still-real gap: if the process dies between a successful
authorisation and a successful save, the payment provider is holding an
authorisation with no order to match it.

**What that looks like when it happens:** an authorisation on the
provider's side — money reserved, sometimes money moved, depending on the
provider — with no corresponding row in this service's own database. No
error reaches the caller in the case that actually causes this: the
process is gone before it can answer at all.

**Why M3 does not close it.** Voiding the authorisation from inside the
same code path that just failed to save does not close the gap, it just
relocates it: that call can fail too, for the same reasons the save could,
and the service would then be holding *two* possible failure points
instead of one. Closing it properly means something outside this one
request path notices the mismatch after the fact — an outbox that records
the authorisation durably in the same transaction as the eventual save, or
a reconciliation job that periodically compares this service's orders
against the provider's authorisations and flags what does not match.
Either is its own design round, and message queues — the usual way an
outbox is implemented — are
[excluded from this project entirely](../roadmap.md#what-is-deliberately-excluded).

This is recorded here, in the documentation, because writing the gap down
precisely is not the same thing as closing it, and a reader is better
served by a plain description of when it happens than by a page that says
nothing. There is no on-call runbook yet to link this from — that is M5's
[roadmap](../roadmap.md) row — so it lives on this page until one exists.
