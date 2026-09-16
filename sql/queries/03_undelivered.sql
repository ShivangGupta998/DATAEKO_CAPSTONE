-- Q3: How many orders have no delivery row at all?
-- Answer: 80,000 orders (exact seeded anti-join count, 20% of 400,000 orders)

SELECT COUNT(*) AS undelivered_orders_count
FROM orders o
LEFT JOIN deliveries del ON o.id = del.order_id
WHERE del.id IS NULL;
