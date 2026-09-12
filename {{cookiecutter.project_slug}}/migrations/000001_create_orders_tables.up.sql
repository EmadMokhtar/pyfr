CREATE TABLE orders (
    id UUID PRIMARY KEY,
    customer_id UUID NOT NULL,
    total_amount NUMERIC(14, 2) NOT NULL,
    total_currency CHAR(3) NOT NULL,
    internal_note TEXT
);

CREATE TABLE order_lines (
    order_id UUID NOT NULL REFERENCES orders (id) ON DELETE CASCADE,
    line_number INTEGER NOT NULL,
    sku TEXT NOT NULL,
    quantity INTEGER NOT NULL,
    unit_amount NUMERIC(14, 2) NOT NULL,
    unit_currency CHAR(3) NOT NULL,
    PRIMARY KEY (order_id, line_number)
);
