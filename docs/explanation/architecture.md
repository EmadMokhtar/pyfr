# Architecture

This page describes how a PyFr service is put together and why. For the rules
that keep the structure honest, see
[Layers and the dependency rule](layers.md).

## The shape

```
src/<package>/
  main.py             application factory and lifespan
  settings.py         configuration, validated at startup
  container.py        the composition root: builds adapters, wires them together

  domain/             imports nothing but Pydantic
    order.py            entity and value objects; invariants live here
    repositories.py     ports: what storage must be able to do
    errors.py           the domain error hierarchy

  services/
    order.py            application services and their command objects

  infrastructure/     adapters: the only code that knows a storage technology
    memory/             the in-memory repository (M0)

  api/                the only code that knows HTTP exists
    deps.py             FastAPI dependencies reading from application state
    errors.py           domain error to Problem Details
    middleware.py       correlation identifier, access log
    health.py           /healthz /readyz /startupz
    v1/                 router.py, schemas.py, mappers.py

  observability/
    logging.py          one processor chain for every log record
```

## A request, end to end

```
HTTP request
  → middleware          take or create the correlation id; bind it to the log context
  → api/v1/router       FastAPI validates the body against the api schema
  → api/v1/mappers      schema → service command
  → services/order      orchestrates; holds no business rules itself
  → domain/order        invariants enforced by the entity on construction
  → domain/repositories the port — an interface, not an implementation
  → infrastructure/     the only code that knows how storage works
```

The response retraces those steps outward. Errors take a different route: a
domain error travels up untouched, and one handler in the api layer turns it
into a [Problem Details](../reference/errors.md) response. **The domain layer
never learns that HTTP status codes exist.**

## The four layers

**`domain/`** holds the business model: what an order *is*, and what makes one
valid. It imports Pydantic and the standard library, nothing else. It has no
idea whether there is a web server or a database.

Pydantic is used here as a validation library, not as a web framework. It is
what makes the invariants declarative and impossible to bypass — an `Order`
whose total disagrees with its lines cannot be constructed.

**`services/`** holds application services: one business operation each. A
service turns a command into domain objects, lets the entity enforce its own
rules, and hands the result to a repository. It holds no business rules of its
own.

That distinction is easy to lose. If a rule can be stated without mentioning
storage or transport, it belongs in `domain/`. The service layer is
choreography.

**`infrastructure/`** holds adapters: the only code that knows a specific
technology. M0 ships an in-memory repository. M1 adds PostgreSQL behind the
identical interface, and nothing above this layer changes.

**`api/`** holds the only code that knows HTTP exists: routes, request and
response schemas, middleware, and the mapping from domain errors to status
codes.

## Ports and adapters

The domain declares what it needs as a `Protocol` — Python's *structural*
interface. A class satisfies a Protocol by having methods with the right
signatures. It does not inherit from anything, and it does not import the
Protocol.

```python
@runtime_checkable
class OrderRepository(Protocol):
    async def get(self, order_id: OrderId) -> Order | None: ...
    async def save(self, order: Order) -> None: ...
```

That last part is what keeps the arrow pointing inward. With an abstract base
class, the adapter would have to import from the domain to inherit — a
dependency in the wrong direction. With a Protocol, nothing needs importing at
all.

The `domain` package owns the interface. `infrastructure` provides an
implementation. `domain` never learns which one it got.

## Wiring: a composition root, not a dependency-injection framework

`container.py` is one plain module that constructs the adapters. The
application's lifespan builds it at startup, puts it on the application state,
and closes it at shutdown. `api/deps.py` holds small functions that read from
that state, and tests replace them with FastAPI's `dependency_overrides`.

A *composition root* is the single place where an application constructs and
connects its dependencies. Keeping it in one module means there is exactly one
place to look to see what a running service is actually made of.

No dependency-injection library is used. FastAPI's own `Depends` plus this one
module already does the job, and a dependency-injection container is a large
concept for every new team member to learn, for no gain at this size.

## Health, correlation, shutdown

Three pieces of runtime behaviour are worth naming, because each prevents a
class of incident rather than adding a feature:

- **[Three health endpoints](../reference/http-api.md#health-endpoints)**
  answering three different questions. Merging them is a way to turn a brief
  dependency problem into a full outage.
- **[Correlation identifiers](../reference/logging.md#correlation-identifiers)**
  binding one value to every log line a request produced.
- **Graceful shutdown.** On the shutdown signal, the server stops accepting
  new connections and lets in-flight requests finish, for up to 30 seconds.
  Without it, every rolling deployment drops live requests.

  That 30 seconds is only real if the orchestrator's own kill deadline is
  comfortably higher — otherwise requests still running when it expires are
  killed, not drained. See [Run in a container](../guides/run-in-a-container.md#the-shutdown-deadline-trap),
  which is where this bites in practice.

## What M0 does not have

No database, no cache, no object storage, no distributed tracing, no metrics.
Those arrive in M1 through M4 — see the [roadmap](../roadmap.md).

This is not an unfinished service. A service with no database is a real thing
people build: an API gateway, an aggregator, a webhook receiver. M0 is
deliberately useful on its own, and every later milestone adds to a service
that already runs.
