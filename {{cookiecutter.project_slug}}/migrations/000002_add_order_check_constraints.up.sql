ALTER TABLE order_lines
ADD CONSTRAINT order_lines_quantity_positive CHECK (quantity > 0);

ALTER TABLE order_lines
ADD CONSTRAINT order_lines_unit_amount_non_negative CHECK (unit_amount >= 0);

ALTER TABLE orders
ADD CONSTRAINT orders_total_amount_non_negative CHECK (total_amount >= 0);
