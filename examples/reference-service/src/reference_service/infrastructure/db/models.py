"""SQLAlchemy table definitions.

These mirror `migrations/` exactly, and the drift gate in
tests/integration/test_schema_drift.py is what keeps them mirroring it. They
are deliberately NOT the domain models: `domain/order.py` imports nothing but
Pydantic, and `.importlinter` fails the build if SQLAlchemy ever appears
there. mappers.py moves data between the two.

golang-migrate owns the schema. Nothing here ever calls
`Base.metadata.create_all()` — two tools creating one schema is exactly the
situation spec section 6.1 rules out, and a test database built by
create_all() would be testing the models against themselves rather than
against the migrations production actually runs.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    CheckConstraint,
    ForeignKey,
    Integer,
    Numeric,
    Text,
    Uuid,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class OrderRow(Base):
    __tablename__ = "orders"
    __table_args__ = (
        # Mirrors migration 000002. Declared here as well as in SQL because the
        # drift gate compares this metadata against the real database.
        CheckConstraint("total_amount >= 0", name="orders_total_amount_non_negative"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True)
    customer_id: Mapped[uuid.UUID] = mapped_column(Uuid, nullable=False)
    # NUMERIC, never FLOAT: `Money.amount` is a Decimal with two places, and
    # binary floating point cannot represent 0.10 exactly. (14, 2) matches
    # Money's own max_digits=14, decimal_places=2.
    total_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    total_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
    internal_note: Mapped[str | None] = mapped_column(Text, nullable=True)


class OrderLineRow(Base):
    __tablename__ = "order_lines"
    __table_args__ = (
        CheckConstraint("quantity > 0", name="order_lines_quantity_positive"),
        CheckConstraint(
            "unit_amount >= 0", name="order_lines_unit_amount_non_negative"
        ),
    )

    order_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("orders.id", ondelete="CASCADE"), primary_key=True
    )
    # Part of the primary key, so line order is recorded in the schema rather
    # than left to insertion order. `Order.lines` is an ordered tuple.
    line_number: Mapped[int] = mapped_column(Integer, primary_key=True)
    sku: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), nullable=False)
    unit_currency: Mapped[str] = mapped_column(CHAR(3), nullable=False)
