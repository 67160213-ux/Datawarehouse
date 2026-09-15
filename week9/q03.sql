SELECT month, province, SUM(amount) AS revenue
FROM sales
GROUP BY month, province
ORDER BY month, province;
