"""Deterministic, auditable synthetic expense vs budget pipeline."""

import csv
import hashlib
import json
import re
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "finance_demo.sqlite"
OUTPUT = ROOT / "output"
ACCOUNTS = (
    ("Engineering", "Payroll & Benefits", 245000),
    ("Engineering", "Contractors", 95000),
    ("Engineering", "Cloud Infrastructure", 60000),
    ("Sales & Marketing", "Payroll & Benefits", 125000),
    ("Sales & Marketing", "Demand Generation", 95000),
    ("G&A", "Payroll & Benefits", 100000),
    ("G&A", "Professional Services", 50000),
    ("IT", "Software Subscriptions", 80000),
)


def seed(db=DB):
    """Generate FY2026 example GL and budget; safe to rerun for demo data."""
    db = Path(db)
    db.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        conn.executescript("""
        DROP TABLE IF EXISTS actual_expenses;
        DROP TABLE IF EXISTS budgets;
        CREATE TABLE actual_expenses (
            transaction_id TEXT PRIMARY KEY,
            month TEXT NOT NULL,
            department TEXT NOT NULL,
            account TEXT NOT NULL,
            amount REAL NOT NULL
        );
        CREATE TABLE budgets (
            month TEXT NOT NULL,
            department TEXT NOT NULL,
            account TEXT NOT NULL,
            budget_amount REAL NOT NULL,
            version TEXT NOT NULL,
            PRIMARY KEY(month, department, account, version)
        );
        """)
        for m in range(1, 13):
            month = f"2026-{m:02d}"
            for i, (department, account, budget) in enumerate(ACCOUNTS):
                conn.execute("INSERT INTO budgets VALUES (?,?,?,?,?)",
                             (month, department, account, budget, "Approved"))
                # Split every monthly account total into two transactions.
                # Variations are deterministic and intentionally uneven.
                swing = ((m * 7 + i * 11) % 13 - 6) / 100
                actual = round(budget * (1 + swing), 2)
                if m == 9 and department == "Engineering" and account == "Contractors":
                    actual += 60000  # Material, intentional exception
                if m == 9 and department == "IT":
                    actual += 20000
                first = round(actual * 0.6, 2)
                for part, amount in enumerate((first, round(actual-first, 2)), 1):
                    conn.execute("INSERT INTO actual_expenses VALUES (?,?,?,?,?)",
                                 (f"TX-{m:02d}-{i:02d}-{part}", month,
                                  department, account, amount))
        # Separate unbudgeted spend, intentionally requiring mapping review.
        conn.execute("INSERT INTO actual_expenses VALUES (?,?,?,?,?)",
                     ("TX-09-UNBUDGETED", "2026-09", "G&A", "Recruiting One-Time", 7500))
    return db


def _write_csv(path, rows, columns):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def _cents(value):
    return int(round(value * 100))


def run(close_month="2026-09", db=DB, output=OUTPUT):
    """Run controls before exporting, raising on reconciliation discrepancies."""
    if not re.fullmatch(r"2026-(0[1-9]|1[0-2])", close_month):
        raise ValueError("Close month must be 2026-01 through 2026-12")
    db, output = Path(db), Path(output)
    if not db.exists():
        raise FileNotFoundError("Database missing; first run python -m budget_automation seed")
    output.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db) as conn:
        query = (ROOT / "sql" / "variance.sql").read_text(encoding="utf-8")
        conn.row_factory = sqlite3.Row
        rows = [dict(r) for r in conn.execute(query, {"close_month": close_month})]
        source_actual = conn.execute(
            "SELECT COALESCE(SUM(amount),0) AS total FROM actual_expenses WHERE month <= ?",
            (close_month,)).fetchone()["total"]
        source_budget = conn.execute(
            "SELECT COALESCE(SUM(budget_amount),0) AS total FROM budgets "
            "WHERE month <= ? AND version='Approved'", (close_month,)
        ).fetchone()["total"]
        fy_budgets = [dict(r) for r in conn.execute(
            "SELECT department, SUM(budget_amount) AS fy_budget "
            "FROM budgets WHERE version='Approved' GROUP BY department"
        )]

    for row in rows:
        budget, actual = row["budget"], row["actual"]
        variance = round(actual - budget, 2)
        variance_pct = round(variance / budget, 6) if budget else ""
        if row["mapping_status"] != "MATCHED":
            status = "DATA_REVIEW"
        elif variance > 10000 and variance_pct > 0.10:
            status = "HIGH_RISK"
        elif variance > 0:
            status = "OVER_BUDGET"
        else:
            status = "ON_TRACK"
        row.update(variance=variance, variance_pct=variance_pct, status=status)

    actual_cents = sum(_cents(r["actual"]) for r in rows)
    budget_cents = sum(_cents(r["budget"]) for r in rows)
    if actual_cents != _cents(source_actual) or budget_cents != _cents(source_budget):
        raise AssertionError("Source to output control totals do not reconcile")

    summary = defaultdict(lambda: [0, 0])
    for row in rows:
        totals = summary[row["department"]]
        totals[0] += _cents(row["budget"])
        totals[1] += _cents(row["actual"])
    dept_rows = [dict(department=k, budget_ytd=v[0]/100, actual_ytd=v[1]/100,
                      variance_ytd=round((v[1]-v[0])/100, 2))
                 for k, v in sorted(summary.items())]

    forecast = []
    for entry in fy_budgets:
        name = entry["department"]
        ytd_budget, ytd_actual = summary.get(name, [0, 0])
        fy_budget = round(entry["fy_budget"], 2)
        remaining = round(fy_budget - ytd_budget/100, 2)
        eac = round(ytd_actual/100 + remaining, 2)
        forecast.append(dict(department=name, close_month=close_month,
                             fy_budget=fy_budget, actual_ytd=ytd_actual/100,
                             remaining_budget=remaining, run_rate_adjustment=0,
                             forecast_eac=eac,
                             forecast_variance=round(eac-fy_budget, 2)))

    exceptions = [r for r in rows if r["status"] in ("DATA_REVIEW", "HIGH_RISK")]
    detail_cols = ["month", "department", "account", "budget", "actual",
                   "variance", "variance_pct", "mapping_status", "status"]
    files = {
        "variance_detail.csv": (rows, detail_cols),
        "department_summary.csv": (dept_rows, ["department", "budget_ytd", "actual_ytd", "variance_ytd"]),
        "forecast.csv": (forecast, ["department", "close_month", "fy_budget", "actual_ytd",
                                     "remaining_budget", "run_rate_adjustment", "forecast_eac", "forecast_variance"]),
        "exceptions.csv": (exceptions, detail_cols),
    }
    for filename, (content, columns) in files.items():
        _write_csv(output / filename, content, columns)

    now = datetime.now(timezone.utc).isoformat()
    audit = {
        "run_timestamp_utc": now,
        "close_month": close_month,
        "data_classification": "SYNTHETIC",
        "source_actual": round(source_actual, 2),
        "source_budget": round(source_budget, 2),
        "output_actual": actual_cents / 100,
        "output_budget": budget_cents / 100,
        "source_reconciliation_passed": True,
        "detail_rows": len(rows),
        "exception_rows": len(exceptions),
        "sha256": {filename: hashlib.sha256((output / filename).read_bytes()).hexdigest()
                   for filename in files},
    }
    (output / "run_audit.json").write_text(json.dumps(audit, indent=2) + "\n", encoding="utf-8")
    return {"close_month": close_month,
            "budget_ytd": f"${budget_cents/100:,.2f}",
            "actual_ytd": f"${actual_cents/100:,.2f}",
            "variance_ytd": f"${(actual_cents-budget_cents)/100:,.2f}",
            "exceptions": len(exceptions), "output": str(output)}
