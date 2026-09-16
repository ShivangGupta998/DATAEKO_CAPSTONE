-- Migration 001: Add index on orders(customer_id) to optimize customer lookup queries
CREATE INDEX IF NOT EXISTS idx_orders_customer_id ON orders(customer_id);
