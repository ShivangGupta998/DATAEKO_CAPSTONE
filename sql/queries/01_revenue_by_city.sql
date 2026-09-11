-- Answer: Total collected-order revenue per city, highest first.
-- Revenue is calculated as qty * price_inr.

SELECT
    s.city,
    SUM(o.qty * d.price_inr) AS total_revenue_inr
FROM orders o
JOIN drinks d
    ON o.drink_id = d.id
JOIN stores s
    ON o.store_id = s.id
WHERE o.status = 'collected'
GROUP BY s.city
ORDER BY total_revenue_inr DESC;
