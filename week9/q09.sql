SELECT month, SUM(amount) AS revenue
FROM sales
GROUP BY month
UNION ALL
SELECT 'ALL', SUM(amount) AS revenue
FROM sales;
