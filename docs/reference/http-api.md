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

```json
{"status": "ok", "checks": {}}
```

Returns 200 when every registered check passes, and **503** when any fails.
A failing readiness probe removes the instance from load balancing but does
not restart it, which is the correct response to "my database is unreachable".

`checks` is empty in M0 because there are no dependencies yet. With a
database registered, a failure looks like this:

```json
{"status": "unavailable", "checks": {"postgres": "error: TimeoutError"}}
```

Two details are deliberate.

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

### `GET /api/v1/orders/{order_id}`

Responds 200 with the order, or [404](errors.md) when no order has that id.

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
