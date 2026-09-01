ALTER TABLE orders
DROP CONSTRAINT orders_total_amount_non_negative;

ALTER TABLE order_lines
DROP CONSTRAINT order_lines_unit_amount_non_negative;

ALTER TABLE order_lines
DROP CONSTRAINT order_lines_quantity_positive;
