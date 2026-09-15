SELECT 'Before JOIN (fact)' AS stage, COUNT(*) AS row_count, SUM(quantity * unit_price) AS total_amount FROM fact_sales
UNION ALL
SELECT 'After JOIN (sales)' AS stage, COUNT(*) AS row_count, SUM(amount) AS total_amount FROM sales;
