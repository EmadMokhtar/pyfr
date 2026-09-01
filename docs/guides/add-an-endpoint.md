# Add an endpoint

This guide adds one feature through all four layers, so you see where each
piece of code goes and why. It follows the shipped orders slice, which is the
worked example you copy from.

Work from `examples/reference-service/`. Read
[Layers and the dependency rule](../explanation/layers.md) first if you have
not.

Build it in this order — inward first, outward last. Each step is testable
before the next one exists.

## 1. The domain model

`src/reference_service/domain/`. This layer imports Pydantic and the standard
library. Nothing else.

Put the rules that are true regardless of how the data arrived here:

```python
class Money(BaseModel):
    model_config = ConfigDict(frozen=True)
    amount: Annotated[Decimal, Field(ge=0, max_digits=14, decimal_places=2)]
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]
```

Three habits to copy from `order.py`:

- **`frozen=True`** on entities and value objects. Not
  `validate_assignment=True` — [the reason is specific and
  counter-intuitive](../explanation/layers.md#why-domain-models-are-frozen).
- **`tuple`, not `list`,** for a collection field, so its contents cannot be
  mutated past the validators.
- **Cross-field rules as a model validator**, not as a check in a service. An
  `Order` whose total disagrees with its lines must be impossible to
  construct, not merely unusual.

Add a domain error if the operation can fail for a business reason. It carries
a stable `code` and a `title`, and **no HTTP status code**:

```python
class OrderNotFoundError(DomainError):
    code = "order_not_found"
    title = "Order not found"
```

## 2. The port

If the feature needs storage, declare *what* it needs in
`domain/repositories.py` as a `Protocol` — an interface satisfied by having
the right methods, with no inheritance:

```python
@runtime_checkable
class OrderRepository(Protocol):
    async def get(self, order_id: OrderId) -> Order | None: ...
    async def save(self, order: Order) -> None: ...
```

Describe it in domain terms. `get` and `save`, not `select_one` and `upsert`.

## 3. The application service

`src/reference_service/services/`. One file per aggregate, one callable class
per operation.

A service takes a command, builds domain objects, lets them enforce their own
rules, and calls the port. **It holds no business rules itself.**

```python
class PlaceOrder:
    def __init__(self, orders: OrderRepository) -> None:
        self._orders = orders

    async def __call__(self, command: PlaceOrderCommand) -> Order:
        lines = tuple(OrderLine(...) for item in command.lines)
        order = Order(id=OrderId(uuid4()), lines=lines, total=total_of(lines))
        await self._orders.save(order)
        return order
```

The dependency arrives through `__init__`, so a test constructs the service
with a fake and never touches infrastructure.

Define the command object in the same file. A command is **not** an HTTP
schema and **not** a domain entity — it is the service layer's own input type.
Restate its constraints here, even though the HTTP schema also has them: a
caller that is not HTTP reaches this layer directly, and the command must be
safe for that caller too. [Why the same constraint appears three
times](../explanation/layers.md#why-the-same-constraint-appears-three-times).

## 4. The adapter

`src/reference_service/infrastructure/`. The only code that knows a storage
technology.

Implement the port. Do not inherit from it — a Protocol is satisfied
structurally, and inheriting would point an import at the domain from the
wrong direction.

M0 has only the in-memory adapter. For a real backend, see
[Add a backend](add-a-backend.md).

## 5. Wire it up

`container.py` builds the adapters. `api/deps.py` exposes them to routes:

```python
def get_place_order(orders: OrdersDep) -> PlaceOrder:
    return PlaceOrder(orders)

PlaceOrderDep = Annotated[PlaceOrder, Depends(get_place_order)]
```

If the feature adds a dependency that can be unavailable, register a readiness
check for it on the container's registry. It then appears in
[`/readyz`](../reference/http-api.md#get-readyz-readiness) automatically.

## 6. The HTTP schema and the mapper

`api/v1/schemas.py` holds request and response models — separate from the
domain models, [on purpose](../explanation/layers.md#why-api-schemas-are-separate).

Mirror the domain's constraints on the request model. Without that, a value
the domain rejects passes the edge and fails deeper, as a 500 rather than a
clean 422.

For a rule *between* fields, use a model validator:

```python
@model_validator(mode="after")
def lines_must_share_one_currency(self) -> Self:
    currencies = {line.currency for line in self.lines}
    if len(currencies) > 1:
        raise ValueError(f"all lines must share one currency, got {sorted(currencies)}")
    return self
```

`api/v1/mappers.py` holds plain functions between the schemas and the service
layer. Write them by hand and name every field. That is what stops an
internal field reaching a client the day someone adds it to the entity.

## 7. The route

`api/v1/router.py`:

```python
@router.post("", response_model=OrderResponse, status_code=status.HTTP_201_CREATED)
async def place_order(
    request: PlaceOrderRequest, place: PlaceOrderDep, response: Response
) -> OrderResponse:
    order = await place(to_command(request))
    response.headers["Location"] = f"/api/v1/orders/{order.id}"
    return to_response(order)
```

The route maps in, calls the service, maps out. No business logic.

**Document an error only on the routes that can produce it.** 422 and 500 are
declared once, globally, because any route can hit them. A 404 is declared on
the specific route that can raise it:

```python
@router.get(
    "/{order_id}",
    response_model=OrderResponse,
    responses={status.HTTP_404_NOT_FOUND: problem_response("Order not found")},
)
```

Registering an exception handler does **not** change what the OpenAPI document
says. Without the `responses` entry, a client generated from your published
contract disagrees with what the service actually returns.

## 8. Map the error to a status code

If you added a domain error, map it in `api/errors.py`:

```python
_STATUS_BY_ERROR: dict[type[DomainError], int] = {
    OrderNotFoundError: status.HTTP_404_NOT_FOUND,
}
```

An unmapped domain error becomes 422. The lookup walks the class hierarchy, so
a subclass inherits its parent's status.

## 9. Tests

- **`tests/unit/`** — the domain rules and the service, using a fake
  repository. No application, no HTTP.
- **`tests/api/`** — the route over ASGI, using the `client` fixture. Assert
  the status, the body, and — for anything that must not be published — its
  *absence*.

Write the failing test first; that is how the reference service was built.

## 10. Check it

```bash
just check
```

Lint, types, the import rule, tests, hooks, and the no-changes check. If
`just imports` fails, an import points the wrong way — the message names the
contract and the chain.
