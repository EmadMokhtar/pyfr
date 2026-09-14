---
last_reviewed: 2026-09-10
covers:
  - src/{{ cookiecutter.package_name }}/api/
---

# HTTP API

Interactive documentation is served by the running service at `/docs`, and
the machine-readable OpenAPI document at `/openapi.json`. This page covers
what those two cannot express.

Every response carries an `X-Request-ID` header — see
[correlation identifiers](logging.md#correlation-identifiers).

## Health endpoints

Three endpoints, three genuinely different questions. Wiring them to the same
answer is a real way to turn a small problem into a large one.

| Path | Question | Checks dependencies? |
| --- | --- | --- |
| `GET /healthz` | Is this process alive? | **Never** |
| `GET /readyz` | Can this instance serve traffic right now? | Yes, with short timeouts |
| `GET /startupz` | Has startup finished? | No |

### `GET /healthz` — liveness

```json
{"status": "ok", "version": "0.1.0"}
```

Always 200 while the process runs.

**This endpoint must never check a database.** An orchestrator restarts a
container whose liveness probe fails. If liveness checked the database, then
a database hiccup would fail the probe on *every* instance at once, and the
orchestrator would restart the entire service — converting a brief dependency
problem into a full outage, and removing the capacity that might have
recovered.

### `GET /readyz` — readiness
{%- set _checks = '"database": "ok"' if cookiecutter.database == "postgres" else '' %}
{%- set _deps = (['"cache": "ok"'] if cookiecutter.cache == "redis" else []) + (['"storage": "ok"'] if cookiecutter.object_storage == "s3" else []) %}

```json
{"status": "ok", "checks": {{ '{' ~ _checks ~ '}' }}, "dependencies": {{ '{' ~ (_deps | join(', ')) ~ '}' }}}
```

<!-- exec -->
```bash
curl -sf http://localhost:{{ cookiecutter.http_port }}/readyz | grep -q '"status":"ok"'
```

Two tiers, and which tier a dependency belongs in is a judgement about
**blast radius**, not about importance.

`checks` is **gating**: it decides the status code. Returns 200 when every
gating check passes, and **503** when any fails. A failing readiness probe
removes the instance from load balancing but does not restart it, which is
{%- if cookiecutter.database == "postgres" %}
the correct response to "my database is unreachable". The database is the
only entry in `checks` — a failure looks like this:

```json
{"status": "unavailable", "checks": {"database": "error: TimeoutError"}, "dependencies": {}}
```
{%- else %}
moot here: nothing is ever registered in `checks` in this service, so
`GET /readyz` can never fail on that account, and always returns 200 as far
as `checks` is concerned.
{%- endif %}

`dependencies` is **informational**: it is reported and never changes the
{%- if cookiecutter.cache == "redis" and cookiecutter.object_storage == "s3" %}
status code, whatever it says. The cache and the object store live here, and
both stay `"ok"` or degrade independently of `checks` — losing either never
turns into a 503.

```json
{"status": "ok", "checks": {{ '{' ~ _checks ~ '}' }}, "dependencies": {"cache": "error: TimeoutError", "storage": "ok"}}
```
{%- elif cookiecutter.cache == "redis" %}
status code, whatever it says. The cache lives here, and stays `"ok"` or
degrades independently of `checks` — losing it never turns into a 503.

```json
{"status": "ok", "checks": {{ '{' ~ _checks ~ '}' }}, "dependencies": {"cache": "error: TimeoutError"}}
```
{%- elif cookiecutter.object_storage == "s3" %}
status code, whatever it says. The object store lives here, and stays
`"ok"` or degrades independently of `checks` — losing it never turns into a
503.

```json
{"status": "ok", "checks": {{ '{' ~ _checks ~ '}' }}, "dependencies": {"storage": "error: TimeoutError"}}
```
{%- else %}
status code, whatever it says — but nothing is registered here in this
service, so `dependencies` is always `{}`.
{%- endif %}
{%- if cookiecutter.cache == "redis" and cookiecutter.object_storage == "s3" %}
{%- if cookiecutter.database == "postgres" %}

**Why gate on the database but not the other two.** This is worth
remembering, because it is not the obvious choice.
{%- else %}

**Why the cache and the object store never gate.** This is worth
remembering, because it is not the obvious choice.
{%- endif %}
{%- elif cookiecutter.cache == "redis" %}
{%- if cookiecutter.database == "postgres" %}

**Why gate on the database but not the cache.** This is worth remembering,
because it is not the obvious choice.
{%- else %}

**Why the cache never gates.** This is worth remembering, because it is
not the obvious choice.
{%- endif %}
{%- elif cookiecutter.object_storage == "s3" %}
{%- if cookiecutter.database == "postgres" %}

**Why gate on the database but not the object store.** This is worth
remembering, because it is not the obvious choice.
{%- else %}

**Why the object store never gates.** This is worth remembering, because
it is not the obvious choice.
{%- endif %}
{%- endif %}
{%- if cookiecutter.cache == "redis" %}

The cache is informational because it **fails open**: `CachedOrderRepository`
{%- if cookiecutter.database == "postgres" %}
swallows every Redis error and falls through to PostgreSQL, so a Redis outage
{%- else %}
swallows every Redis error and falls through to the order repository beneath
it, so a Redis outage
{%- endif %}
never produces a wrong answer, only a slower one. Redis is also **shared
across every pod** — gating on it would make every pod fail the check in the
same second, taking the whole service out of the load balancer over a
degradation it was specifically built to survive. A cache that can take the
service down is worse than no cache at all.
{%- endif %}
{%- if cookiecutter.object_storage == "s3" %}

Object storage is informational for a different reason with the same answer.
Losing it breaks exactly one endpoint, `GET /orders/{id}/receipt` — see below
— so pulling 100% of traffic off a pod to protect that one slice costs far
more than it saves.
{%- endif %}
{%- if cookiecutter.database == "postgres" and cookiecutter.cache == "redis" and cookiecutter.object_storage == "s3" %}

`checks` is empty and `dependencies` is empty when no database, cache, or
storage is configured — a service can run with none of the three, on the
in-memory repository, no cache decorator, and the in-memory receipt store.
{%- else %}

`checks` is empty and `dependencies` is empty whenever none of this project's
optional backends is configured — the service runs on its in-memory
adapters either way.
{%- endif %}

Two further details are deliberate.

**Checks run concurrently, not one after another.** Run in sequence, the
worst case would be the number of dependencies multiplied by the timeout —
three checks at two seconds each is a six-second response, which the
orchestrator's own probe timeout kills first, marking the instance unready
for entirely the wrong reason. Concurrent, the worst case is one timeout no
matter how many dependencies exist.

**The exception message is not in the response.** You get the exception's
type name (`TimeoutError`), never its message. `/readyz` is reachable from
inside a cluster, and a database driver's exception message routinely carries
hostnames, connection strings, or credentials. The full exception and its
traceback go to the log, where an operator can still read them.

### `GET /startupz` — startup

```json
{"status": "ok", "version": "0.1.0"}
```

200 once the application's startup has finished, 503 (`"status": "starting"`)
before that. This covers slow first starts — a service that needs 40 seconds
to warm caches should not be declared dead at second 10.

## Orders

An example slice, included so the pattern is copied rather than reinvented.

### `POST /api/v1/orders`

Request:

```json
{
  "customer_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "lines": [
    {"sku": "WIDGET-1", "quantity": 2, "unit_amount": "9.99", "currency": "EUR"}
  ]
}
```

| Field | Rule |
| --- | --- |
| `customer_id` | A UUID. |
| `lines` | At least one line. Every line must use the **same** currency. |
| `lines[].sku` | 1 to 64 characters. |
| `lines[].quantity` | An integer greater than 0. |
| `lines[].unit_amount` | 0 or more, at most 2 decimal places, at most 14 digits. |
| `lines[].currency` | Exactly three uppercase letters, such as `EUR`. |

Responds **201 Created** with a `Location` header pointing at the new order,
and the order as the body. `subtotal` and `total` are computed by the service.

Placing an order authorises payment first, so it can also answer:

- **402 Payment Required** — the payment provider declined the card. A
  successful call with a negative answer, not a failure on this service's
  part; it is never retried automatically. See
  [Outbound HTTP calls](../guides/outbound-http.md#the-retry-rule-and-why-it-is-narrow).
- **503 Service Unavailable** — the payment provider could not be reached,
  or its circuit breaker is open. Carries a `Retry-After` header, whose
  value is the configured breaker cool-down
  (`APP_PAYMENT__BREAKER_RESET_AFTER_SECONDS`, 30 seconds by default,
  rounded up to a whole number of seconds); waiting that long and
  retrying is the correct client behaviour, not treating this as a
  permanent failure. See
  [Outbound HTTP calls](../guides/outbound-http.md#the-breakers-three-states).

Both use the same [Problem Details](errors.md) body shape as every other
error. `GET /api/v1/orders/{order_id}` cannot produce either — it never
talks to the payment provider.

### `GET /api/v1/orders/{order_id}`

Responds 200 with the order, or [404](errors.md) when no order has that id.

<!-- exec -->
```bash
order_id=$(curl -sf -X POST http://localhost:{{ cookiecutter.http_port }}/api/v1/orders \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"3fa85f64-5717-4562-b3fc-2c963f66afa6","lines":[{"sku":"WIDGET-1","quantity":2,"unit_amount":"9.99","currency":"EUR"}]}' \
  | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
curl -sf "http://localhost:{{ cookiecutter.http_port }}/api/v1/orders/$order_id" | grep -q '"amount":"19.98"'
```

### `GET /api/v1/orders/{order_id}/receipt`

Responds 200 with the receipt document, `Content-Type: application/json`:

```json
{
  "schema_version": 1,
  "order_id": "cac0acf8-ea5c-4936-97b4-3b0c113f8a8f",
  "customer_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "authorisation_id": "auth_9f2c1e",
  "currency": "EUR",
  "total": "19.98",
  "lines": [
    {"sku": "WIDGET-1", "quantity": 2, "unit_price": "9.99", "subtotal": "19.98"}
  ]
}
```

<!-- exec -->
```bash
order_id=$(curl -sf -X POST http://localhost:{{ cookiecutter.http_port }}/api/v1/orders \
  -H 'Content-Type: application/json' \
  -d '{"customer_id":"3fa85f64-5717-4562-b3fc-2c963f66afa6","lines":[{"sku":"WIDGET-1","quantity":2,"unit_amount":"9.99","currency":"EUR"}]}' \
  | grep -o '"id":"[^"]*"' | head -1 | cut -d'"' -f4)
curl -sf "http://localhost:{{ cookiecutter.http_port }}/api/v1/orders/$order_id/receipt" | grep -q '"schema_version":1'
```
{%- if cookiecutter.object_storage == "s3" %}

Also [404](errors.md) when no order has that id — checked first, so an
unknown id never touches object storage at all — and **503 Service
Unavailable** when the receipt store cannot be reached. Carries a
`Retry-After` header too, like the payment provider's 503 above, but here
the value is a fixed 30 seconds rather than derived from a setting — there
is no circuit breaker in front of object storage for it to read a cool-down
from.

**Rendered on demand, not written when the order is placed.** The first
request for a receipt renders it from the order and stores the result; every
request after that serves the stored bytes unchanged. This is deliberate:
`PlaceOrder` never touches object storage, so a storage outage can degrade
one read endpoint but can never fail a payment. The cost is one slower first
request per order — rendering is pure and cheap, so in practice that cost is
small.
{%- else %}

Also [404](errors.md) when no order has that id — checked first. The
contract publishes **503 Service Unavailable** for this route too, for a
receipt store that cannot be reached; this service keeps its receipts in
memory, so that response never occurs here, and a client written against
the contract handles it all the same.

**Rendered on demand, not written when the order is placed.** The first
request for a receipt renders it from the order and stores the result; every
request after that serves the stored bytes unchanged. This is deliberate:
`PlaceOrder` never touches the receipt store, so the store can never fail a
payment. The cost is one slower first request per order — rendering is pure
and cheap, so in practice that cost is small.
{%- endif %}

Every amount in the document is a JSON string, for the same reason as the
order response below. The document carries no timestamp — a receipt is
stored once and served unchanged afterwards, and a `generated_at` field
would make a re-rendering after a cache eviction produce different bytes for
"the same" receipt. `internal_note` is absent for the same reason it is
absent from the order response: the renderer names every field it emits
rather than dumping the entity.

### Response shape

```json
{
  "id": "cac0acf8-ea5c-4936-97b4-3b0c113f8a8f",
  "customer_id": "3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "lines": [
    {
      "sku": "WIDGET-1",
      "quantity": 2,
      "unit_price": {"amount": "9.99", "currency": "EUR"},
      "subtotal": {"amount": "19.98", "currency": "EUR"}
    }
  ],
  "total": {"amount": "19.98", "currency": "EUR"}
}
```

**Amounts are JSON strings.** `"19.98"`, not `19.98`. They are `Decimal`
values; emitting one as a JSON number would push it through binary floating
point, where 0.1 + 0.2 is not exactly 0.3. A string crosses the wire exactly.
Parse it into your own decimal type, not into a float.

**The response omits `internal_note`.** That field exists on the stored
entity. It never reaches a client, because the response is assembled by a
mapper function that names each field that goes out — so a field added to the
entity tomorrow is not published by accident.

## Two constraints checked in more than one place

The same rules appear in the HTTP schema, in the service command object, and
in the domain model. That is intentional, not an oversight.

Each layer must be correct on its own. The HTTP schema catches bad input at
the edge and returns a clean 422. The command object must also stand on its
own, because a caller that is not HTTP — a scheduled job, a message consumer
— reaches the service layer without passing through the schema at all. The
domain model enforces the rule last, because it is the layer that must never
hold an invalid value.

Two rules in particular exist as *whole-request* checks rather than per-field
ones:

- **All lines share one currency.** This is a relationship *between* lines,
  so no single-field constraint can express it. Without it, two individually
  valid lines in different currencies reach the money arithmetic, which raises
  a plain `ValueError` — neither a domain error nor a validation error — and
  falls through to the catch-all handler as a 500 for input that was merely
  wrong, not exceptional.
- **The total matches the sum of the lines.** Enforced by the `Order` entity
  itself, so an order whose total disagrees with its lines cannot be
  constructed at all.
