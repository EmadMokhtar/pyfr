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
| `domain-independence` | `domain` importing `api`, `services`, `infrastructure`, the container, the app factory, FastAPI, or Starlette |
| `services-independence` | `services` importing `api`, `infrastructure`, the container, the app factory, FastAPI, or Starlette |

Add `import fastapi` to a domain module and `just check` fails with the
contract that broke and the import chain that broke it. Try it — the failure
message is the fastest way to understand what the rule protects.

!!! note "`include_external_packages` is load-bearing"

    The import-linter configuration sets `include_external_packages = True`.
    It is required whenever a contract names a third-party package, and
    FastAPI and Starlette are both named above. Without it the tool refuses
    to run at all — it does not silently skip the check, which would be
    worse.

There is also a test, `test_layer_purity.py`, that checks the same property
from a different angle. Two mechanisms for one rule is deliberate: the rule is
the foundation everything else rests on.

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
