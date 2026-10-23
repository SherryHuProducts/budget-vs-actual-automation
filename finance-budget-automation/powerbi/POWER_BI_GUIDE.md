# Power BI Build Guide

## 1 — Import CSV files

Run `python -m budget_automation seed` and `python -m budget_automation run --through 2026-09` at the repo root.

In Power BI Desktop, choose **Home → Get data → Text/CSV**, load:

- `output/variance_detail.csv` as `VarianceDetail`
- `output/department_summary.csv` as `DepartmentSummary`
- `output/forecast.csv` as `Forecast`
- `output/exceptions.csv` as `Exceptions`

These have different aggregation grains. Do not join them directly in this MVP; build each visual against the appropriate table. For a larger model, use conformed department and calendar dimension tables.

Set monetary columns to Decimal Number or Fixed Decimal Number, and format `variance_pct` as Percentage (do not multiply by 100). The `month` value is YYYY-MM text and sorts chronologically.

## 2 — Measures (Modeling → New measure)

```dax
Total Budget = SUM(VarianceDetail[budget])

Total Actual = SUM(VarianceDetail[actual])

Variance = [Total Actual] - [Total Budget]

Variance % = DIVIDE([Variance], [Total Budget])

High Risk Lines =
CALCULATE(
    COUNTROWS(VarianceDetail),
    VarianceDetail[status] = "HIGH_RISK"
)

Unbudgeted Amount =
CALCULATE(
    [Total Actual],
    VarianceDetail[mapping_status] = "UNBUDGETED"
)
```

## 3 — CFO Overview page

| Visual | Fields |
|---|---|
| Four KPI cards | Total Budget, Total Actual, Variance, Variance % |
| Clustered column | `month` + Budget / Actual |
| Clustered bar | `department` + Budget / Actual |
| Drill-down matrix | `department` → `account`, Budget / Actual / Variance / Variance % |
| Slicers | `month`, `department` |

These KPIs are cumulative over whatever months are selected. For YTD, filter Jan through the close month.

## 4 — Exception Review page

- Table from `Exceptions`: month, department, account, mapping_status, status, budget, actual, variance, variance_pct.
- Conditional formatting: red for HIGH_RISK, amber for DATA_REVIEW.
- Cards for High Risk Lines and Unbudgeted Amount from `VarianceDetail`.
- Flags are leads for review, not established causes. Investigate contracts, accruals and cutoffs.

## 5 — Forecast page

Use `Forecast` (not a join with `VarianceDetail`):

- Department comparison: `fy_budget` vs `forecast_eac`.
- Table: department, actual_ytd, remaining_budget, run_rate_adjustment, forecast_eac, forecast_variance.
- KPI: sum of `forecast_variance`.

The forecast uses remaining approved budget as a baseline and is not a validated statistical projection.

## 6 — Finishing the actual report

- Use white or warm beige canvas, restrained navy/blue accents, and red for unfavorable expenses.
- Include a visible label: **Synthetic FY2026 data | September close**.
- Save your finished Power BI Desktop report as `powerbi/Budget_Actual_Dashboard.pbix`.
- Add genuine screenshots to README only after building the report.
- Publish only if your Power BI tenant permits external sharing.
