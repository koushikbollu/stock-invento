"""Retained publication impact: business before/after values, not lineage churn."""

import csv
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import tempfile
import unittest

from inventory.impact import record_changes
from inventory.pipeline import Inventory, PipelineError
from tests.test_pipeline import HEADER, SAMPLE, event


QUANTITIES = {"opening", "receipts", "issues", "transfers_in", "transfers_out", "adjustments", "closing"}


class ChangeEvidenceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.inventory = Inventory(self.root / "inventory.db")
        self.inventory.load_catalogs(SAMPLE / "items.csv", SAMPLE / "locations.csv")
        self.files = 0

    def ingest(self, rows, **options):
        self.files += 1
        path = self.root / f"batch-{self.files}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADER)
            writer.writeheader()
            writer.writerows(rows)
        return self.inventory.ingest(path, through="2026-01-04", **options)

    def sample(self):
        return self.inventory.ingest(SAMPLE / "movements.csv", through="2026-01-04")

    def test_first_publication_records_all_added_business_rows(self):
        run = self.sample()
        changes = self.inventory.changes(run["run_id"])
        self.assertTrue(changes["has_snapshot"])
        self.assertEqual(changes["total"], 11)
        self.assertEqual(changes["summary"], {
            "changed_rows": 11, "affected_series": 3,
            "from_date": "2026-01-01", "through_date": "2026-01-04",
        })
        self.assertEqual(run["changed_balance_rows"], 11)
        self.assertTrue(all(row["change_type"] == "added" for row in changes["rows"]))
        for row in changes["rows"]:
            self.assertIsNone(row["before"])
            self.assertEqual(set(row["after"]), QUANTITIES)
            self.assertEqual(set(row["changed_fields"]), QUANTITIES)
            self.assertEqual(row["closing_delta"], row["after_closing"])

    def test_receipt_correction_changes_four_days_and_excludes_other_series(self):
        self.sample()
        run = self.inventory.ingest(SAMPLE / "corrections.csv", through="2026-01-04")
        result = self.inventory.changes(run["run_id"])
        self.assertEqual(result["total"], 4)
        self.assertEqual(result["summary"]["affected_series"], 1)
        self.assertEqual([row["balance_date"] for row in result["rows"]],
                         [f"2026-01-{day:02d}" for day in range(1, 5)])
        self.assertEqual([(row["before_closing"], row["after_closing"]) for row in result["rows"]],
                         [("100.000", "110.000")] + [("65.000", "75.000")] * 3)
        for row in result["rows"]:
            self.assertEqual((row["item_id"], row["location_id"]), ("ITEM-A", "WH-A"))
            self.assertEqual(row["closing_delta"], "10.000")
            self.assertEqual(row["change_type"], "updated")
            self.assertEqual(set(row["before"]), QUANTITIES)
            self.assertEqual(set(row["after"]), QUANTITIES)

    def test_identical_rerun_has_recorded_empty_snapshot(self):
        self.sample()
        rerun = self.sample()
        changes = self.inventory.changes(rerun["run_id"])
        self.assertTrue(changes["has_snapshot"])
        self.assertEqual(changes["total"], 0)
        self.assertEqual(changes["rows"], [])
        self.assertEqual(changes["summary"], {
            "changed_rows": 0, "affected_series": 0, "from_date": None, "through_date": None,
        })
        self.assertEqual(rerun["changed_balance_rows"], 0)

    def test_before_after_evidence_is_retained_after_later_publications(self):
        initial = self.sample()
        original = self.inventory.changes(initial["run_id"])
        corrected = self.inventory.ingest(SAMPLE / "corrections.csv", through="2026-01-04")
        correction_evidence = self.inventory.changes(corrected["run_id"])
        self.ingest([event(event_id="later", effective_date="2026-01-02", quantity="7")])
        self.assertEqual(self.inventory.changes(initial["run_id"]), original)
        self.assertEqual(self.inventory.changes(corrected["run_id"]), correction_evidence)
        self.assertEqual(correction_evidence["rows"][-1]["after_closing"], "75.000")

    def test_moving_date_and_location_records_removed_and_added_rows(self):
        self.ingest([event(quantity="10")])
        moved = self.ingest([event(revision="2", effective_date="2026-01-03", location_id="WH-B", quantity="10")])
        rows = self.inventory.changes(moved["run_id"])["rows"]
        removed = [row for row in rows if row["change_type"] == "removed"]
        added = [row for row in rows if row["change_type"] == "added"]
        self.assertEqual(len(rows), 6)
        self.assertEqual(len(removed), 4)
        self.assertEqual(len(added), 2)
        for row in removed:
            self.assertEqual(row["location_id"], "WH-A")
            self.assertIsNone(row["after"])
            self.assertEqual(row["before_closing"], "10.000")
            self.assertEqual(row["closing_delta"], "-10.000")
        for row in added:
            self.assertEqual(row["location_id"], "WH-B")
            self.assertGreaterEqual(row["balance_date"], "2026-01-03")
            self.assertIsNone(row["before"])
            self.assertEqual(row["closing_delta"], "10.000")

    def test_void_retains_before_values_for_removed_series(self):
        self.ingest([event(quantity="10")])
        voided = self.ingest([event(revision="2", quantity="10", is_void="true")])
        result = self.inventory.changes(voided["run_id"])
        self.assertEqual(result["total"], 4)
        self.assertEqual(self.inventory.report()["balances"], [])
        for row in result["rows"]:
            self.assertEqual(row["change_type"], "removed")
            self.assertEqual(set(row["before"]), QUANTITIES)
            self.assertIsNone(row["after"])
            self.assertEqual(row["closing_delta"], "-10.000")

    def test_same_closing_with_changed_movement_columns_is_still_a_change(self):
        self.ingest([event(quantity="10")])
        changed = self.ingest([event(revision="2", movement_type="ADJUSTMENT", quantity="10")])
        result = self.inventory.changes(changed["run_id"])
        self.assertEqual(result["total"], 1)
        row = result["rows"][0]
        self.assertEqual(row["balance_date"], "2026-01-01")
        self.assertEqual(row["before_closing"], "10.000")
        self.assertEqual(row["after_closing"], "10.000")
        self.assertEqual(row["closing_delta"], "0.000")
        self.assertEqual(set(row["changed_fields"]), {"receipts", "adjustments"})
        self.assertEqual(row["before"]["receipts"], "10.000")
        self.assertEqual(row["after"]["receipts"], "0.000")
        self.assertEqual(row["before"]["adjustments"], "0.000")
        self.assertEqual(row["after"]["adjustments"], "10.000")

    def test_failed_publication_has_no_snapshot_or_change_rows(self):
        successful = self.ingest([event(quantity="10")])
        before = self.inventory.changes(successful["run_id"])
        with self.assertRaises(PipelineError):
            self.ingest([event(revision="2", quantity="20")], fail_before_publish=True)
        failed = next(run for run in self.inventory.report()["runs"] if run["status"] == "failed")
        changes = self.inventory.changes(failed["run_id"])
        self.assertFalse(changes["has_snapshot"])
        self.assertEqual(changes["total"], 0)
        self.assertEqual(changes["rows"], [])
        self.assertEqual(self.inventory.changes(successful["run_id"]), before)
        with self.inventory.connect() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM balance_changes WHERE run_id=?", (failed["run_id"],)).fetchone()[0], 0)

    def test_pagination_returns_stable_rows_and_full_summary(self):
        run = self.sample()
        full = self.inventory.changes(run["run_id"], limit=500)
        page = self.inventory.changes(run["run_id"], limit=3, offset=3)
        self.assertEqual(page["rows"], full["rows"][3:6])
        self.assertEqual(page["summary"], full["summary"])
        self.assertEqual(page["total"], 11)
        self.assertEqual((page["limit"], page["offset"]), (3, 3))
        self.assertEqual(self.inventory.changes(run["run_id"], offset=100)["rows"], [])
        self.assertEqual(self.inventory.changes()["run_id"], run["run_id"])

    def test_pagination_and_unknown_run_validation(self):
        for limit in (0, -1, 501, True, 1.5, "1", None):
            with self.subTest(limit=limit), self.assertRaises(ValueError):
                self.inventory.changes(limit=limit)
        for offset in (-1, True, 1.5, "0", None):
            with self.subTest(offset=offset), self.assertRaises(ValueError):
                self.inventory.changes(offset=offset)
        with self.assertRaises(ValueError):
            self.inventory.changes("unknown-run")
        empty = self.inventory.changes()
        self.assertIsNone(empty["run_id"])
        self.assertFalse(empty["has_snapshot"])
        self.assertEqual(empty["rows"], [])

    def test_legacy_run_migration_distinguishes_unavailable_from_recorded_no_change(self):
        path = self.root / "legacy.db"
        with closing(sqlite3.connect(path)) as connection, connection:
            connection.execute("""CREATE TABLE runs (
                run_id TEXT PRIMARY KEY, source_file TEXT NOT NULL, started_at TEXT NOT NULL,
                finished_at TEXT, status TEXT NOT NULL, input_count INTEGER NOT NULL DEFAULT 0,
                accepted_count INTEGER NOT NULL DEFAULT 0, duplicate_count INTEGER NOT NULL DEFAULT 0,
                rejected_count INTEGER NOT NULL DEFAULT 0, rolled_back_count INTEGER NOT NULL DEFAULT 0,
                output_count INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER NOT NULL DEFAULT 0,
                error TEXT, published_through TEXT)""")
            connection.execute("INSERT INTO runs(run_id,source_file,started_at,finished_at,status) VALUES (?,?,?,?,?)",
                               ("legacy", "old.csv", "2026-01-01T00:00:00+00:00", "2026-01-01T00:00:01+00:00", "succeeded"))
        migrated = Inventory(path)
        old = migrated.changes("legacy")
        self.assertFalse(old["has_snapshot"])
        self.assertEqual(old["run"]["impact_recorded"], 0)
        self.assertEqual(old["total"], 0)
        self.inventory = migrated
        new = self.ingest([])
        self.assertTrue(migrated.changes(new["run_id"])["has_snapshot"])
        self.assertEqual(migrated.changes(new["run_id"])["total"], 0)
        self.assertFalse(migrated.changes("legacy")["has_snapshot"])

    def test_export_contains_change_headers_even_when_empty_and_retains_exact_rows(self):
        empty = self.inventory.export(self.root / "empty-export")
        self.assertIn("balance_changes.csv", empty["files"])
        path = self.root / "empty-export" / "balance_changes.csv"
        with path.open(newline="", encoding="utf-8") as stream:
            reader = csv.DictReader(stream)
            self.assertEqual(reader.fieldnames, ["run_id", "balance_date", "item_id", "location_id",
                                                "before_json", "after_json", "closing_delta_milli"])
            self.assertEqual(list(reader), [])
        self.ingest([event(quantity="10")])
        run = self.ingest([event(revision="2", quantity="11")])
        self.inventory.export(self.root / "populated-export")
        with (self.root / "populated-export" / "balance_changes.csv").open(newline="", encoding="utf-8") as stream:
            rows = [row for row in csv.DictReader(stream) if row["run_id"] == run["run_id"]]
        self.assertEqual(len(rows), 4)
        self.assertTrue(all(row["closing_delta_milli"] == "1000" for row in rows))
        self.assertEqual(json.loads(rows[0]["before_json"])["closing"], "10.000")
        self.assertEqual(json.loads(rows[0]["after_json"])["closing"], "11.000")

    def test_delta_between_int64_closings_preserves_wider_exact_integer(self):
        # A focused impact-store boundary fixture avoids generating millions of
        # valid bounded events merely to reach the SQLite aggregate limit.
        run = self.ingest([])
        old = dict.fromkeys(QUANTITIES, "0.000")
        old["opening"] = old["closing"] = "-9223372036854775.807"
        with self.inventory.connect() as connection:
            connection.execute("""INSERT INTO daily_balances VALUES
                ('2026-01-01','ITEM-A','WH-A',9223372036854775807,0,0,0,0,0,9223372036854775807,?)""", (run["run_id"],))
            record_changes(connection, run["run_id"], {("2026-01-01", "ITEM-A", "WH-A"): old})
        result = self.inventory.changes(run["run_id"])
        self.assertEqual(result["rows"][0]["closing_delta"], "18446744073709551.614")
        with self.inventory.connect() as connection:
            delta = connection.execute("SELECT closing_delta_milli,typeof(closing_delta_milli) FROM balance_changes").fetchone()
        self.assertEqual(tuple(delta), ("18446744073709551614", "text"))


if __name__ == "__main__":
    unittest.main()
