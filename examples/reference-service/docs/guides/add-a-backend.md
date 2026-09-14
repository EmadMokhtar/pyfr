---
last_reviewed: 2026-09-10
---

# Add a backend

PyFr ships a deliberately narrow set of adapters: PostgreSQL, Redis, and
S3-compatible object storage. MySQL, MongoDB, Memcached, Google Cloud Storage
and Azure Blob are not included — [the reasoning is
here](https://emadmokhtar.github.io/pyfr/explanation/why-a-template/#the-narrow-backend-matrix).

If you need one of those, you write one adapter. This guide is the shape of
that work.

!!! note "Worked examples in the codebase"

    Three real adapters follow the structure below exactly, and are worth
    reading beside it: `infrastructure/db/order_repository.py`
    (`PostgresOrderRepository`, an ordinary adapter over SQLAlchemy — the
    version of this guide to copy from for a plain storage port),
    `infrastructure/storage/receipt_store.py` (`S3ReceiptStore`, the same
    shape over `aioboto3`, and the worked example of "one adapter per
    S3-compatible provider" rather than one adapter per vendor), and
    `infrastructure/cache/order_repository.py` (`CachedOrderRepository`, a
    *decorating* adapter — it satisfies `OrderRepository` by holding another
    `OrderRepository` rather than a driver. See [what a port
    buys](../explanation/layers.md#what-a-port-buys-the-caching-decorator)
    for why that shape is worth understanding even if the backend you are
    adding is not a cache).

## What you are actually writing

You are not extending a framework. You are writing a class that satisfies an
interface the domain layer already declared.

The domain owns the interface, called a **port**. Your class is an
**adapter**. Nothing above the storage layer changes when you add one —
that is the whole point of the [dependency
rule](../explanation/layers.md).

## 1. Read the port

In `domain/repositories.py`:

```python
@runtime_checkable
class OrderRepository(Protocol):
    async def get(self, order_id: OrderId) -> Order | None:
        """Return the order, or None when it does not exist."""

    async def save(self, order: Order) -> None:
        """Persist the order, creating or replacing it."""
```

That is your specification. Note that it is stated in domain terms —
`Order`, not rows; `get`, not `SELECT`.

`get` returning `None` for a missing order, rather than raising, is part of
the contract. Deciding that a missing order is an error is the *service*
layer's decision, and it makes it by raising `OrderNotFoundError`.

## 2. Write the adapter

Put it in `infrastructure/<technology>/`. For example
`infrastructure/mysql/order_repository.py`.

**Do not inherit from the Protocol.** A Protocol is satisfied structurally —
by having methods with the right signatures. Inheriting would make your
adapter import from the domain in order to subclass it, and the dependency
would point the wrong way.

```python
class MySQLOrderRepository:
    def __init__(self, pool: Pool) -> None:
        self._pool = pool

    async def get(self, order_id: OrderId) -> Order | None:
        ...

    async def save(self, order: Order) -> None:
        ...
```

Two rules for this file:

- **Translate at the boundary.** Rows go in; domain objects come out. A
  database row must never travel further up than this module, and a domain
  object must never carry a driver's type.
- **Never let a driver exception escape.** A `MySQLError` reaching the service
  layer makes that layer depend on MySQL, which is exactly what the port
  exists to prevent. Catch it and raise a domain error instead.

## 3. Add its settings

In `settings.py`, as a nested model:

```python
class MySQLSettings(BaseModel):
    model_config = ConfigDict(frozen=True)
    dsn: SecretStr
    pool_size: int = 10
```

Use `SecretStr` for anything that is a credential. Its printed form is
`**********`, so it cannot reach a log line or a traceback by accident.

Set `frozen=True` on the nested model explicitly. Freezing the top-level
settings does **not** freeze the models nested inside it — see
[Configuration](../reference/configuration.md#settings-are-frozen-with-one-gap).

Add the variables to `.env.example` with a comment each, and to the table in
[Configuration](../reference/configuration.md#variables). The documentation
freshness check will remind you if you forget.

## 4. Register it in the composition root

`container.py` is the single place that decides which adapter a running
service actually uses:

```python
def build_container(settings: Settings) -> Container:
    pool = create_pool(settings.mysql.dsn.get_secret_value())
    return Container(settings=settings, orders=MySQLOrderRepository(pool))
```

Release the resource in `close_container`. It runs at shutdown, after
in-flight requests have finished.

## 5. Register a readiness check — and choose the right tier

A dependency that can be unavailable belongs in
[`/readyz`](../reference/http-api.md#get-readyz-readiness), but which of its
two tiers depends on what losing the dependency actually costs, not on how
important it feels.

**`register`** is gating: a failure returns 503 and takes the instance out of
load balancing.

```python
container.readiness.register("mysql", check_mysql)
```

**`register_informational`** is reported but never changes the status code —
the choice made for both the cache and the object store:

```python
container.readiness.register_informational("cache", check_redis)
```

Ask two questions before picking. **Does losing it make this instance unable
to do useful work?** If yes — the primary datastore, say — gate on it. **Is
it shared across every pod, and does the code already survive its loss?** If
so, gating is actively harmful: every pod fails the check in the same
instant, and a degradation the service was built to tolerate becomes a total
outage instead. That is exactly the cache's situation —
`CachedOrderRepository` fails open, so PostgreSQL already answers every
request when Redis is down — and it is why the cache is informational, not
gating. The object store is informational for a related but distinct reason:
losing it breaks one endpoint, not the whole instance, so taking all traffic
off the pod to protect that one endpoint would cost more than it saves.

Checks in both tiers run concurrently, each under a short timeout, so
registering in either never multiplies the endpoint's worst-case latency.

Do **not** add either tier to `/healthz`. A liveness probe that checks a
dependency restarts every instance at once when that dependency hiccups,
turning a small problem into an outage — the same reasoning that keeps a
gating `/readyz` check off Redis, one level more severe.

## 6. Test it

- **Unit tests** keep using the fake repository. They must not change at all —
  if adding an adapter forces a domain or service test to change, something
  has leaked upward, and that is the signal to look for.
- **Integration tests** exercise the real adapter against the real technology,
  started in Docker for the test session. Test through the port: save an
  order, get it back, and check it round-trips unchanged.

The round-trip test is the one that matters. It catches the errors adapters
actually make — a `Decimal` silently becoming a float, a timezone dropped, a
`None` stored as the string `"None"`.

## 7. Check the rule still holds

```bash
just imports
```

If your adapter accidentally imported from `api/` or `services/`, this fails
with the contract that broke and the import chain that broke it.
