-- Nullable with no default and no backfill. Rows written before this
-- migration were placed with no payment provider configured, and
-- inventing an authorisation reference for them would be a lie recorded
-- in the database forever. NULL says exactly what is true: unknown.
ALTER TABLE orders
ADD COLUMN authorisation_id TEXT;
