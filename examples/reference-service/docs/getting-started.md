---
last_reviewed: 2026-09-14
covers:
  - justfile
  - src/reference_service/seed.py
---

# Getting started

This walks you through running the service and placing an order
through it. It takes about five minutes.

The service is a complete, running microservice.

## What you need

| Tool | Why |
| --- | --- |
| [uv](https://docs.astral.sh/uv/) | The only Python tool required. It installs Python itself, resolves dependencies, and runs commands. |
| [just](https://github.com/casey/just) | A command runner. Every task in this project is a `just` recipe. |
| Docker | Only for `just up`, in [Start with data in it](#start-with-data-in-it). Nothing else below needs it. |

You do **not** need to install Python separately. `uv` reads
`.python-version` and fetches the right interpreter.

## Run it

```bash
uv sync
```

`uv sync` installs exactly the versions recorded in `uv.lock`, so you get the
same dependency tree the tests and the container image use.

Install the git hooks once. They check formatting and commit messages before
a commit is created:

```bash
uv run pre-commit install
```

Now start the service:

```bash
just dev
```

That serves on <http://localhost:8000> with auto-reload: edit a file and the
server restarts itself. Interactive API documentation is at
<http://localhost:8000/docs>.

## Start with data in it

`just dev` starts empty. With Docker, the container stack starts with five
orders already in it. Stop `just dev` first (Ctrl-C) — both serve on port
8000 — then:

```bash
just up
```

That builds the image, starts PostgreSQL, Redis, MinIO and a payment stub,
applies the migrations, and starts the API. Once the API reports healthy, a
one-shot `seed` container creates five fixed orders through the HTTP API and
exits. The line to look for in the output is:

```
seed-1 exited with code 0
```

The orders it created, with the ids the service assigned them:

```bash
docker compose logs seed
```

```
seed-1  | espresso-beans  c8e7aa28-be07-4916-9b1e-eb2cae1f654a     37.00 EUR  created
seed-1  | filter-papers   603394d1-950d-4c6f-a388-d4c8eee60f0e     12.75 EUR  created
seed-1  | grinder         eba6a954-cee1-45c5-ba74-3804a4d55af6    249.00 EUR  created
seed-1  | mixed-basket    6d580aeb-2dbd-4240-9bfd-20a890d324f1     52.00 EUR  created
seed-1  | bulk-order      ac7eefb7-d04c-4fdc-8af5-34afffcb6f78    462.50 USD  created
```

Any of those ids answers a `GET` straight away, before you have placed
anything yourself:

```bash
curl -s http://localhost:8000/api/v1/orders/c8e7aa28-be07-4916-9b1e-eb2cae1f654a | jq
```

The ids differ on every machine — the service assigns them — so copy one
from your own `seed` output rather than from this page.

The seed is idempotent (running it again changes nothing): the ids it issued
are kept in a small state file, and a second `just up` finds every order still
there and prints `exists` instead of `created`. `just down` removes the state
with the database, so the next `just up` seeds again.

The same five orders are available without Docker. With `just dev` running in
one terminal, in another:

```bash
just seed
```

That runs the same module against `localhost:8000`, keeps its state in
`.seed-state.json` (ignored by git), and prints the same five lines. `just dev`
holds orders in memory, so after a restart `just seed` finds them gone and
creates them again.

## Check that it is alive

<!-- exec -->
```bash
response=$(curl -si http://localhost:8000/healthz)
echo "$response"
grep -q '^HTTP/1.1 200' <<< "$response"
grep -q '"status":"ok"' <<< "$response"
```

```http
HTTP/1.1 200 OK
content-type: application/json
x-request-id: 3d4cd25c9d334f65b6fb555d12dac32e

{"status":"ok","version":"0.1.0"}
```

Note `x-request-id`. Every response carries one. It is the **correlation
identifier** — a single value that ties together every log line one request
produced. You did not send one, so the service generated it. Send your own
and the service uses that instead, which is how you follow one request across
several services.

There are three health endpoints, not one, and they answer three different
questions. [HTTP API](reference/http-api.md#health-endpoints) explains why
that distinction prevents an outage.

## Place an order

<!-- exec -->
```bash
response=$(curl -si -X POST http://localhost:8000/api/v1/orders -H 'Content-Type: application/json' -d '{"customer_id":"3fa85f64-5717-4562-b3fc-2c963f66afa6","lines":[{"sku":"WIDGET-1","quantity":2,"unit_amount":"9.99","currency":"EUR"}]}')
echo "$response"
grep -q '^HTTP/1.1 201' <<< "$response"
grep -q '"amount":"19.98"' <<< "$response"
```

```http
HTTP/1.1 201 Created
content-type: application/json
location: /api/v1/orders/cac0acf8-ea5c-4936-97b4-3b0c113f8a8f
x-request-id: f69a9e6446c34a8387327ebf80482709

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

Three things happened that are worth naming.

**`subtotal` and `total` were computed, not accepted.** You sent a unit price
and a quantity. The `Order` entity works out the rest and refuses to exist if
the total disagrees with its lines.

**Money is a JSON string, not a number.** `"19.98"`, not `19.98`. Amounts are
`Decimal` values, and rendering one as a JSON number would route it through a
binary floating-point type, where `0.1 + 0.2` is not `0.3`. A string crosses
the wire exactly.

**The response is not the stored entity.** The stored `Order` also has an
`internal_note` field. It is absent above, and it cannot leak by accident,
because the response is built by a mapper function that lists what goes out.
That is [why API schemas are separate](explanation/layers.md#why-api-schemas-are-separate).

## Ask for one that does not exist

<!-- exec -->
```bash
response=$(curl -si http://localhost:8000/api/v1/orders/3fa85f64-5717-4562-b3fc-2c963f66afa6)
echo "$response"
grep -q '^HTTP/1.1 404' <<< "$response"
grep -q '^content-type: application/problem+json' <<< "$response"
```

```http
HTTP/1.1 404 Not Found
content-type: application/problem+json

{
  "type": "https://errors.example.com/order_not_found",
  "title": "Order not found",
  "status": 404,
  "detail": "no order with id 3fa85f64-5717-4562-b3fc-2c963f66afa6",
  "instance": "/api/v1/orders/3fa85f64-5717-4562-b3fc-2c963f66afa6"
}
```

The content type is `application/problem+json`, not `application/json`. This
is [RFC 9457 Problem Details](reference/errors.md) — the internet standard
shape for an error body, so a client can read errors from any service the
same way.

The domain layer never chose `404`. It raised `OrderNotFoundError`, which
says which business rule broke. One module in the api layer decides that
"not found" means 404. That separation is [the dependency
rule](explanation/layers.md) at work.

!!! note "Orders do not survive a restart of `just dev`"

    With no database configured, the service stores orders in memory, on
    purpose. Restart `just dev` and the order is gone — `just seed` puts the
    five fixed ones back. `just up` runs PostgreSQL behind the same
    interface, and nothing above the storage layer changes when it does.

## Run the checks

One command runs everything a pull request must pass:

```bash
just check
```

That is lint, type-check, the import rule, the tests, and the git hooks — then
`git diff --exit-code`. The last part matters: several hooks *rewrite* files,
so a run that reformatted your code but exited 0 would look like a pass. The
diff check turns that into a loud failure. Every command is listed in
[Commands](reference/commands.md).

## Where to go next

- [Add an endpoint](guides/add-an-endpoint.md) — build your own feature
  through all four layers.
- [Architecture](explanation/architecture.md) — how the pieces fit and why.
- [Configuration](reference/configuration.md) — every environment variable.
