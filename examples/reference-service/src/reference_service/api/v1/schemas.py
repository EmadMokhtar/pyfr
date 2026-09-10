"""HTTP request and response schemas.

These are deliberately separate from the domain models. The wire contract can
then change independently of the business model: a domain field can be
renamed without breaking clients, and an internal field cannot leak simply
because someone added it to the entity.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Self
from uuid import UUID

from pydantic import (
    BaseModel,
    BeforeValidator,
    Field,
    StringConstraints,
    WithJsonSchema,
    model_validator,
)

# NUMERIC(14, 2) in migrations/000001: twelve integer digits and two
# decimal places. One name for it, because three files need the same
# number and a second literal is a second thing to forget.
MAX_MONEY = Decimal("999999999999.99")

# The schema is written out rather than inferred, and that is the point.
#
# Pydantic renders a constrained Decimal as a two-branch anyOf, and the
# inferred version is wrong in both branches. The NUMBER branch gets only
# `minimum`: `max_digits` and `decimal_places` have no JSON Schema
# equivalent and are simply dropped, so the contract said any number >= 0
# was acceptable. The STRING branch gets a regex whose first alternative,
# `\d{0,12}`, has no closing `$` — and JSON Schema's `pattern` is
# explicitly a PARTIAL match, so "070" followed by arbitrary junk
# satisfies it. Both gaps were found by Schemathesis generating values the
# contract permitted and the model refused.
#
# Keeping this in step with the Field() constraints above it is exactly
# what the conformance gate does, on every run, by generating from this
# schema and asserting the model accepts the result. That is why it is
# safe to state it by hand here and nowhere else.
UnitAmount = Annotated[
    Decimal,
    Field(ge=0, le=MAX_MONEY, max_digits=14, decimal_places=2),
    WithJsonSchema(
        {
            "anyOf": [
                {
                    "type": "number",
                    "minimum": 0,
                    # float(MAX_MONEY), not the literal typed out a second
                    # time: a hand-typed duplicate of MAX_MONEY is exactly
                    # the kind of schema-versus-model drift this hand-
                    # written block exists to prevent, and it is drift the
                    # conformance gate cannot catch — a schema that is
                    # STRICTER than the model only ever generates values
                    # the model already accepts, so nothing here would
                    # ever fail. `float()` is safe for this one value only
                    # because MAX_MONEY has two decimal places and no
                    # binary-float rounding changes it at this magnitude —
                    # confirmed: float(MAX_MONEY) == 999999999999.99 in
                    # Python's own double precision.
                    "maximum": float(MAX_MONEY),
                    "multipleOf": 0.01,
                },
                {
                    "type": "string",
                    "pattern": r"^(0|[1-9][0-9]{0,11})(\.[0-9]{1,2})?$",
                },
            ],
            "title": "Unit Amount",
        }
    ),
]


def _integral_float_to_int(value: object) -> object:
    """Accept a JSON number with a zero fractional part as the integer it is.

    JSON Schema defines `integer` as any number whose fractional part is
    zero, so `2.0` satisfies this field's published `"type": "integer"` —
    and clients whose language serialises numbers as doubles send exactly
    that. `strict=True` on the field below rejects a float outright, so
    without this the API would refuse a request its own contract declares
    valid: the same "rejected schema-compliant request" defect the
    conformance gate exists to catch, reached from the other direction.
    Confirmed against the committed contract with the same validator
    Schemathesis uses: `{"type": "integer"}` accepts 2.0 and rejects 2.5.

    `bool` is tested FIRST and returned untouched. `bool` is an `int`
    subclass, so it never reaches the float branch anyway — but being
    explicit is the point: `strict=True` exists to stop `True` being read
    as `1`, and nothing here may weaken that. A non-integral float such as
    2.5 is also returned untouched, so the strict validator rejects it,
    which is right: the contract rejects it too.
    """
    if isinstance(value, bool):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class MoneyOut(BaseModel):
    amount: Decimal
    currency: str


class OrderLineIn(BaseModel):
    sku: Annotated[str, StringConstraints(min_length=1, max_length=64)]
    # le=2_147_483_647 mirrors order_lines.quantity's storage type, INTEGER
    # (PostgreSQL int4, max 2_147_483_647), in
    # migrations/000001_create_orders_tables.up.sql. Without it, a quantity
    # the column cannot hold passes this schema and the service command and
    # blows up as asyncpg.exceptions.DataError deep inside the adapter
    # instead of a 422 at the edge — the same failure mode unit_amount's
    # bounds below exist to prevent for Money.amount / NUMERIC(14, 2).
    #
    # strict=True closes a gap the published schema never had: `type:
    # integer` in the rendered JSON Schema already excludes JSON booleans
    # (they are their own, disjoint type there), but pydantic's default
    # LAX int validation does not — `bool` is an `int` subclass in Python,
    # so without `strict=True` this field accepted `{"quantity": true}` as
    # `1`, a 201 for a request the contract says must be rejected. Found
    # by Schemathesis's negative-data check generating schema-violating
    # `quantity: true` and getting 201 back instead of 422 — the same
    # class of gap unit_amount's WithJsonSchema block exists to prevent,
    # just in the other direction: here the schema was already exact and
    # the model was too permissive, rather than the reverse. `strict=True`
    # does not change the rendered JSON Schema (verified: identical output
    # from `model_json_schema()` with and without it) because it is a
    # pydantic validation-time behaviour, not a schema-shape one — so this
    # needs no `just openapi` regeneration.
    quantity: Annotated[
        int,
        Field(gt=0, le=2_147_483_647, strict=True),
        BeforeValidator(_integral_float_to_int),
    ]
    # Mirrors domain.order.Money.amount: without these bounds, a value the
    # domain rejects (e.g. "10.123", three decimal places) passes this
    # schema and blows up as an unhandled ValidationError deep inside the
    # use case instead of a 422 at the edge. See UnitAmount's docstring
    # above for why the published JSON Schema is written out by hand.
    unit_amount: UnitAmount
    currency: Annotated[str, StringConstraints(pattern=r"^[A-Z]{3}$")]


class OrderLineOut(BaseModel):
    sku: str
    quantity: int
    unit_price: MoneyOut
    subtotal: MoneyOut


class PlaceOrderRequest(BaseModel):
    customer_id: UUID
    lines: Annotated[list[OrderLineIn], Field(min_length=1)]

    @model_validator(mode="after")
    def lines_must_share_one_currency(self) -> Self:
        # A relationship BETWEEN lines, not a property of one, so no
        # per-field constraint can express it. Without this, two
        # individually valid lines in different currencies reach
        # `domain.order.total_of`, whose `Money.__add__` raises a plain
        # `ValueError` — neither a `DomainError` nor a pydantic
        # `ValidationError` — and fall through to the catch-all 500
        # handler for ordinary, schema-valid client input.
        currencies = {line.currency for line in self.lines}
        if len(currencies) > 1:
            raise ValueError(
                f"all lines must share one currency, got {sorted(currencies)}"
            )
        return self

    @model_validator(mode="after")
    def total_must_fit_in_money(self) -> Self:
        # A relationship between two fields of two different lines, so no
        # per-field constraint can express it — the same reason
        # lines_must_share_one_currency above exists. quantity and
        # unit_amount each satisfy their own bound while their PRODUCT
        # exceeds what NUMERIC(14, 2) can hold; Money then refuses to be
        # constructed inside PlaceOrder, which wrapped it as a
        # ServiceDefectError and returned 500 for ordinary client input.
        total = sum(
            (line.unit_amount * line.quantity for line in self.lines), Decimal(0)
        )
        if total > MAX_MONEY:
            raise ValueError(
                f"order total {total} exceeds the maximum representable "
                f"amount {MAX_MONEY}"
            )
        return self


class OrderResponse(BaseModel):
    id: UUID
    customer_id: UUID
    lines: list[OrderLineOut]
    total: MoneyOut


class ReceiptLine(BaseModel):
    """One line of a receipt. Money fields are STRINGS — see ReceiptResponse."""

    sku: str
    quantity: int
    unit_price: str
    subtotal: str


class ReceiptResponse(BaseModel):
    """The receipt document, as published in the contract.

    This model documents the response; it never serialises one. The endpoint
    returns the exact bytes that were stored, because re-serialising them
    through a model would mean the receipt a client reads is not the object
    that was written. tests/api/test_receipts.py's
    test_the_documented_schema_matches_what_the_renderer_produces is what
    keeps the two in step.

    Every money field is a `str`, not a `Decimal` or a `float`, and that is
    the document's shape rather than a limitation of this model — see
    domain/receipt_render.py for why a financial document must not travel as
    an IEEE 754 double.
    """

    schema_version: int
    order_id: UUID
    customer_id: UUID
    authorisation_id: str | None
    currency: str
    total: str
    lines: list[ReceiptLine]
