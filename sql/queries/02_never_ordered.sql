-- Answer: 3 drinks have never been ordered:
-- turmeric latte, rose cardamom, and affogato.

SELECT
    d.name
FROM drinks d
LEFT JOIN orders o
    ON d.id = o.drink_id
WHERE o.id IS NULL
ORDER BY d.name;
