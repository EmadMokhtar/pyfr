---
last_reviewed: 2026-09-10
covers:
  - src/reference_service/api/errors.py
---

# Errors

Every error response uses [RFC 9457 Problem Details](https://www.rfc-editor.org/rfc/rfc9457),
the internet standard shape for a JSON error body. A client can then read
errors from any service the same way, instead of learning a bespoke error
format per service.

The content type is `application/problem+json`, not `application/json`.

## The shape

```json
{
  "type": "https://errors.example.com/order_not_found",
  "title": "Order not found",
  "status": 404,
  "detail": "no order with id 3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "instance": "/api/v1/orders/3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

| Field | Meaning |
| --- | --- |
| `type` | A stable identifier for the *kind* of error. This is what code should branch on. |
| `title` | A short human-readable summary of the kind. Does not change between occurrences. |
| `status` | The HTTP status code, repeated in the body so a logged body is self-contained. |
| `detail` | What went wrong *this time*. Omitted when there is nothing to add. |
| `instance` | The path of the request that failed. |

Match on `type`, never on `title` or `detail`. `title` is prose and may be
reworded; `detail` varies per occurrence.

`type` is a URL by convention, not a promise that anything is served there.
The service uses `https://errors.example.com/<code>`, which is a
placeholder — a real service should point it at documentation it actually
publishes.

## Errors the service returns

| Status | `type` suffix | When |
| --- | --- | --- |
| 400 | `http_error` | The request could not be read at all — for example, a body that is not valid UTF-8. Raised by the framework itself, before routing gets a chance to run. |
| 402 | `payment_declined` | The payment provider declined the card. |
| 404 | `order_not_found` | No order has that id. |
| 404 | `http_error` | No route matches this path. **Same status as the row above, different `type`** — see the warning below. |
| 405 | `http_error` | The path exists, but not for this HTTP method. Carries an `Allow` header naming the methods that do work. |
| 422 | `validation_error` | The request body broke a rule. |
| 500 | `internal_error` | An unhandled failure. |
| 503 | `payment_unavailable` | The payment provider could not be reached, or its circuit breaker is open. Carries a `Retry-After` header set from the configured breaker cool-down. |

422 is used for a request that is well-formed JSON but breaks a rule —
a quantity of zero, a currency of `eur`, two lines in different currencies.

402 and 503 are specific to `POST /api/v1/orders`, the only route that talks
to a payment provider — see [HTTP API](http-api.md#post-apiv1orders) and
[Outbound HTTP calls](../guides/outbound-http.md).

The 400, 404 `http_error` and 405 rows are not raised by this service's own
route handlers at all — they come from the framework, before a route handler
ever runs: an unreadable body, an unmatched path, or a path matched to the
wrong method. All three share the one `type` suffix, `http_error`, because
they are the same kind of fact — "the framework could not even dispatch
this request" — reported at three different statuses.

!!! warning "Two different 404s, one status, two `type`s"

    `order_not_found` and this `http_error` row both answer 404, and that is
    not a coincidence to resolve — they are genuinely different facts that
    happen to share a status code. `order_not_found` means "the path was
    valid and led to a real route, but no order has that id." `http_error`
    means "no route matches this path at all." A client that branches on
    `type`, per the rule stated above ("Match on `type`, never on `title`
    or `detail`"), sees the two correctly as unrelated. A client that
    branches on `status` alone — which that rule does not cover, because
    until now nothing on this page needed two `type`s behind one status —
    cannot tell them apart. Treat `status` the same way: never the sole
    thing you branch on.

### A 500 tells you nothing about the internals

```json
{
  "type": "https://errors.example.com/internal_error",
  "title": "Internal server error",
  "status": 500,
  "instance": "/api/v1/orders"
}
```

There is no `detail`. The full exception and traceback go to the log as one
structured record, keyed by the same correlation identifier the response
carries in `X-Request-ID`. So give that header value to whoever reports the
problem: it is enough to find the exact traceback, and it reveals nothing to
the client.

## How a status code is chosen

The domain layer never mentions HTTP. It raises errors that say which
*business rule* broke:

```python
class DomainError(Exception):
    code: str = "domain_error"
    title: str = "Domain rule violated"

class OrderNotFoundError(DomainError):
    code = "order_not_found"
    title = "Order not found"
```

One module in the api layer maps those onto status codes. Deciding that "not
found" means 404 is a statement about a transport protocol, so it lives with
the transport. The same domain error would map to a different code in a
message-queue consumer, and the domain does not have to care.

A domain error with no explicit mapping becomes **422**.

The mapping walks the class hierarchy rather than looking up the exact class,
so a subclass inherits its parent's status. A future
`OrderAlreadyShippedError` subclassing `OrderNotFoundError` answers 404,
rather than silently falling through to the 422 default.

## Known rough edge: `detail` on a 422

The `detail` field of a validation error currently contains the Python
representation of the validator's error list:

```json
{
  "detail": "[{'type': 'greater_than', 'loc': ('body', 'lines', 0, 'quantity'), 'msg': 'Input should be greater than 0', 'input': 0, 'ctx': {'gt': 0}}]"
}
```

Note the single quotes and the tuple: that is Python syntax, not JSON. It is
readable by a person but awkward for a client to parse, and it is recorded
here as a known limitation rather than presented as a designed format. Treat
`type` and `status` as the contract; treat `detail` on a 422 as a diagnostic
for humans.

## A deliberate mislabel, recorded on purpose

One handler catches *every* validation error raised anywhere in the
application, wherever it comes from, and reports 422.

That is right for the case it exists for: input that passed the edge schema
and was rejected by a deeper validator. It is wrong for a validation error
with no connection to client input at all — a service constructing a domain
object from a value it computed itself, incorrectly. That is a server defect
and deserves a 500, but nothing in the exception distinguishes the two, so it
is currently reported as a client fault.

The real fix is translating validation at the service-layer boundary, so a
service's own bugs surface as 500s and only genuinely bad client input reaches
the handler. M0's services are too thin for that boundary to pay for itself,
so it is scheduled for M1. Every occurrence is logged at `warning` level with
the correlation identifier, so the case is loud rather than silent.
