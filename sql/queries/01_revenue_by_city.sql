-- Q1: Total revenue per city, highest first
-- Answer:
--   Bengaluru: 15,592,590 INR
--   Hyderabad: 15,591,930 INR
--   Chennai:    9,328,900 INR
--   Pune:       9,328,660 INR
--   Delhi:      4,664,450 INR
--   Mumbai:     4,664,100 INR

SELECT 
    s.city,
    SUM(o.qty * d.price_inr) AS total_revenue
FROM orders o
JOIN stores s ON o.store_id = s.id
JOIN drinks d ON o.drink_id = d.id
WHERE o.status = 'collected'
GROUP BY s.city
ORDER BY total_revenue DESC;
