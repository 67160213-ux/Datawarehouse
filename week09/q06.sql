SELECT province, category, SUM(amount) AS revenue
FROM sales
WHERE month = '2026-09' 
  AND category = 'Drink' 
  AND province IN ('Bangkok', 'Chonburi')
GROUP BY province, category
ORDER BY province;
