-- Full-key join preserves lines missing from one side.
WITH actual AS (
    SELECT month, department, account, ROUND(SUM(amount), 2) AS actual
    FROM actual_expenses WHERE month <= :close_month
    GROUP BY month, department, account
), budget AS (
    SELECT month, department, account, ROUND(SUM(budget_amount), 2) AS budget
    FROM budgets WHERE version='Approved' AND month <= :close_month
    GROUP BY month, department, account
), all_keys AS (
    SELECT month, department, account FROM actual
    UNION SELECT month, department, account FROM budget
)
SELECT k.month, k.department, k.account,
       COALESCE(b.budget, 0) AS budget,
       COALESCE(a.actual, 0) AS actual,
       CASE WHEN b.budget IS NULL THEN 'UNBUDGETED'
            WHEN a.actual IS NULL THEN 'NO_ACTUAL'
            ELSE 'MATCHED' END AS mapping_status
FROM all_keys k
LEFT JOIN actual a USING (month, department, account)
LEFT JOIN budget b USING (month, department, account)
ORDER BY k.month, k.department, k.account;
