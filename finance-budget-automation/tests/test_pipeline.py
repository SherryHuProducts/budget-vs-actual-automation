import csv
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from budget_automation.pipeline import run, seed


class PipelineTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.addCleanup(self.tempdir.cleanup)
        self.root = Path(self.tempdir.name)
        self.db = self.root / "demo.sqlite"
        self.output = self.root / "output"
        seed(self.db)

    def test_end_to_end_reconciliation_and_exceptions(self):
        result = run("2026-09", self.db, self.output)
        self.assertGreater(result["exceptions"], 0)
        audit = json.loads((self.output / "run_audit.json").read_text())
        self.assertTrue(audit["source_reconciliation_passed"])
        self.assertAlmostEqual(audit["source_actual"], audit["output_actual"], places=2)
        self.assertAlmostEqual(audit["source_budget"], audit["output_budget"], places=2)
        with (self.output / "exceptions.csv").open(newline="") as file:
            records = list(csv.DictReader(file))
        self.assertTrue(any(r["status"] == "HIGH_RISK" for r in records))
        self.assertTrue(any(r["mapping_status"] == "UNBUDGETED" for r in records))

    def test_approved_version_only(self):
        with sqlite3.connect(self.db) as conn:
            conn.execute("INSERT INTO budgets VALUES (?,?,?,?,?)",
                         ("2026-09", "IT", "Software Subscriptions", 999999, "Draft"))
        result = run("2026-09", self.db, self.output)
        self.assertEqual(result["budget_ytd"], "$7,650,000.00")

    def test_full_year_baseline_forecast(self):
        run("2026-09", self.db, self.output)
        with (self.output / "forecast.csv").open(newline="") as file:
            records = list(csv.DictReader(file))
        for row in records:
            expected = float(row["actual_ytd"]) + float(row["remaining_budget"])
            self.assertAlmostEqual(float(row["forecast_eac"]), expected, places=2)

    def test_invalid_month_rejected(self):
        with self.assertRaises(ValueError):
            run("2027-13", self.db, self.output)

    def test_seed_idempotent(self):
        seed(self.db)
        with sqlite3.connect(self.db) as conn:
            transactions = conn.execute("SELECT COUNT(*) FROM actual_expenses").fetchone()[0]
        self.assertEqual(transactions, 12 * 8 * 2 + 1)


if __name__ == "__main__":
    unittest.main()
