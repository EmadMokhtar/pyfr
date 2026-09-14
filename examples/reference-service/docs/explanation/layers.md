---
last_reviewed: 2026-09-11
covers:
  - .importlinter
---

# Layers and the dependency rule

## The rule

`infrastructure` and `api` import `domain`. **`domain` never imports either.**

Drawn as arrows, everything points inward, toward the business model:

```
   api  ─────┐
             ├──►  services  ──►  domain
infrastructure ────────────────────►
```

The payoff is concrete. Because the domain layer imports nothing but
Pydantic, business rules are tested with no database, no event loop, and no
fixtures. A test that needs a container to check a business rule is a signal
that a boundary has leaked.

## It is enforced, not requested

A rule that lives only in a document is a rule that erodes. This one is
checked by [import-linter](https://import-linter.readthedocs.io/), which reads
the import graph and fails the build when an arrow points the wrong way.

```bash
just imports
```

Two contracts are declared:

| Contract | Forbids |
| --- | --- |
| `domain-independence` | `domain` importing `api`, `services`, `infrastructure`, the container, the app factory, or any of: FastAPI, Starlette, SQLAlchemy, asyncpg, OpenTelemetry, httpx, stamina, redis, aioboto3 |
| `services-independence` | `services` importing `api`, `infrastructure`, the container, the app factory, or that same list of frameworks and drivers |

The list grows with the adapters: FastAPI and Starlette came first, and
every driver an adapter brought in was added with it, so that the layer rule
catches a new dependency leaking inward the same day it is introduced, not
only the two frameworks the project started with.

Add `import fastapi` to a domain module and `just check` fails with the
contract that broke and the import chain that broke it. Try it — the failure
message is the fastest way to understand what the rule protects.

!!! note "`include_external_packages` is load-bearing"

    The import-linter configuration sets `include_external_packages = True`.
    It is required whenever a contract names a third-party package, which
    every entry in the list above is. Without it the tool refuses to run at
    all — it does not silently skip the check, which would be worse.

There is also a test, `test_layer_purity.py`, that checks the same property
from a different angle. Two mechanisms for one rule is deliberate: the rule is
the foundation everything else rests on.

## What a port buys: the caching decorator

`CachedOrderRepository` is the clearest demonstration in this codebase of
what a port is actually for.

It satisfies `OrderRepository` — the same `Protocol` the in-memory and
PostgreSQL adapters satisfy — and it holds *another* `OrderRepository` inside
it:

```python
class CachedOrderRepository:
    def __init__(self, inner: OrderRepository, client: Redis, ttl_seconds: int) -> None:
        self._inner = inner
        self._client = client
        ...

    async def get(self, order_id: OrderId) -> Order | None:
        cached = await self._read(order_id)
        if cached is not None:
            return cached
        return await self._inner.get(order_id)
```

`get` checks Redis, and on a miss — or on any Redis failure at all — falls
through to `inner.get`. Nothing distinguishes a genuine cache miss from a
Redis outage at this call site, and that is deliberate: both cases have the
identical, correct answer, which is "ask the wrapped repository."

The part worth noticing is everything that stays unchanged. `GetOrder`,
`PlaceOrder`, the router, the domain — none of them import `redis`, none of
them know a cache exists, and none of them changed by one line when the cache
was added. `container.py` is the *only* file that knows: it decides whether
to wrap in one place —

```python
orders: OrderRepository = PostgresOrderRepository(...)
if settings.cache is not None:
    orders = CachedOrderRepository(orders, redis, settings.cache.ttl_seconds)
```

— and every caller above that line keeps holding an `OrderRepository` and
keeps calling `get` and `save` exactly as before. Adding the cache is writing
this decorator and wrapping it here. Removing the cache is deleting the
`if` block. Nothing three layers up notices either way.

That is the payoff a `Protocol` port is bought for: not that PostgreSQL can
be swapped for MySQL, but that an entirely *new* concern — a cache in front
of an existing adapter — can be introduced without touching the code that
uses the port at all. `infrastructure/cache/order_repository.py` is what
makes this safe to add in the first place: every Redis failure is logged and
swallowed, so a cache that cannot be reached degrades the service, and never
breaks it.

## Why domain models are frozen

Domain entities and value objects are immutable — `frozen=True`:

```python
class Money(BaseModel):
    model_config = ConfigDict(frozen=True)
    amount: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
```

An earlier draft used `validate_assignment=True` instead, reasoning that
re-running the validators on every assignment would stop an invalid object
existing after construction.

Implementing it proved that reasoning false. Pydantic's `validate_assignment`
assigns the new value **first** and runs the model validator **second**. When
the validator rejects the change, the assignment has already happened. The
raised error tells the caller "rejected" while the object itself now holds the
bad value.

`frozen=True` has no such ordering problem: it refuses the assignment before
any mutation occurs. There is no window in which a bad value has landed.

### Why `lines` is a tuple

`frozen=True` is *shallow*. It refuses to replace a field, but it cannot stop
you mutating an object the field already holds. If `lines` were a `list`, then
`order.lines.append(bad_line)` would corrupt the entity without ever going
through assignment at all.

A `tuple` has no `append`, which closes that gap independently. Pydantic still
accepts an ordinary list at construction time and converts it, so no calling
code has to change.

The same reasoning applies to `PlaceOrderCommand.lines` in the service layer,
which is a tuple for exactly the same reason.

## Why API schemas are separate

`api/v1/schemas.py` holds Pydantic models for requests and responses that are
distinct from the domain models, and `api/v1/mappers.py` holds plain functions
between them.

This costs mapping code. It buys three things:

**Internal fields cannot leak.** The `Order` entity has an `internal_note`
field. The response model does not, and the mapper names every field it
copies. Someone adding a field to the entity tomorrow does not publish it to
every client by accident. A test asserts this.

**The domain can be renamed without breaking clients.** Rename a domain field
and you update one mapper. Derive the schema from the domain model instead and
the rename is an unannounced breaking change to your published contract.

**Two API versions can share one domain model.** `v1` and `v2` of an endpoint
are two mappers over the same entity, not two entities.

The mappers are explicit functions rather than automatic derivation. Deriving
them would remove the exact decoupling the separation exists to create.

## Why the same constraint appears three times

`quantity > 0` is declared in the HTTP schema, in the service command object,
and in the domain model. That looks like duplication worth removing. It is
not.

Each layer must be correct on its own terms:

- The **HTTP schema** rejects bad input at the edge, producing a clean 422
  rather than an exception from somewhere deeper.
- The **command object** must stand alone, because a caller that is not HTTP
  — a scheduled job, a message consumer, a test — reaches the service layer
  without passing through the schema at all. A command that relied on the api
  layer having already filtered its input would be unsafe for those callers.
- The **domain model** enforces the rule last, because it is the layer that
  must never hold an invalid value, whatever route the data arrived by.

Removing any one of the three makes a layer depend on a caller behaving well.
That is precisely the dependency the layering exists to remove.
