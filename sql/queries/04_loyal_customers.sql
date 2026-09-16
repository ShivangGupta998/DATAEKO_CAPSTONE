-- Q4: Customers with more than 25 orders, with their order count and total spend
-- Answer: Customer customer_5291 with 28 orders and 9,020 INR total spend

SELECT 
    c.id AS customer_id,
    c.name,
    COUNT(o.id) AS order_count,
    SUM(o.qty * d.price_inr) AS total_spend
FROM customers c
JOIN orders o ON c.id = o.customer_id
JOIN drinks d ON o.drink_id = d.id
GROUP BY c.id, c.name
HAVING COUNT(o.id) > 25
ORDER BY order_count DESC, total_spend DESC;
