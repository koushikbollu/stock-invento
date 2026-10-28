"""Behavioral tests with independent arithmetic and full-rebuild comparisons."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
import json
from pathlib import Path
import random
import tempfile
import unittest

from inventory.generate import HEADER, generate
from inventory.pipeline import Inventory, PipelineError


SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"
EXPECTED = Path(__file__).resolve().parents[1] / "data" / "expected"
BALANCE_COLUMNS = (
    "balance_date", "item_id", "location_id", "opening", "receipts", "issues",
    "transfers_in", "transfers_out", "adjustments", "closing",
)


def event(event_id="event", revision="1", effective_date="2026-01-01",
          movement_type="RECEIPT", item_id="ITEM-A", location_id="WH-A",
          to_location_id="", quantity="10", is_void="false"):
    return dict(zip(HEADER, (event_id, revision, effective_date, movement_type,
                            item_id, location_id, to_location_id, quantity, is_void)))


def balance_rows(report):
    return sorted(
        ({key: row[key] for key in BALANCE_COLUMNS} for row in report["balances"]),
        key=lambda row: (row["balance_date"], row["item_id"], row["location_id"]),
    )


class InventoryTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.engine = Inventory(self.path / "inventory.sqlite")
        self.engine.load_catalogs(SAMPLE / "items.csv", SAMPLE / "locations.csv")
        self.file_counter = 0

    def csv(self, rows, header=HEADER):
        self.file_counter += 1
        path = self.path / f"movements-{self.file_counter}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=header)
            writer.writeheader()
            writer.writerows(rows)
        return path

    def ingest(self, rows, **options):
        return self.engine.ingest(self.csv(rows), through="2026-01-04", **options)

    def balances(self):
        return {
            (row["balance_date"], row["item_id"], row["location_id"]): row
            for row in self.engine.report()["balances"]
        }

    def closing(self, day, location="WH-A", item="ITEM-A"):
        return self.balances()[(f"2026-01-{day:02d}", item, location)]["closing"]

    def test_sample_matches_hand_computed_oracle_and_equation(self):
        summary = self.engine.ingest(SAMPLE / "movements.csv", through="2026-01-04")
        self.assertEqual(summary["status"], "succeeded")
        self.assertEqual(summary["input_count"], 7)
        self.assertEqual(summary["accepted_count"], 7)
        self.assertEqual(summary["rejected_count"], 0)
        with (EXPECTED / "initial_balances.csv").open(newline="", encoding="utf-8") as stream:
            expected = list(csv.DictReader(stream))
        expected.sort(key=lambda row: (row["balance_date"], row["item_id"], row["location_id"]))
        self.assertEqual(balance_rows(self.engine.report()), expected)
        self.assertEqual(summary["output_count"], 11)
        # Integer arithmetic independently verifies every published equation.
        for row in self.balances().values():
            def milli(key):
                return int(row[key].replace(".", ""))
            self.assertEqual(milli("closing"), milli("opening") + milli("receipts")
                             - milli("issues") + milli("transfers_in")
                             - milli("transfers_out") + milli("adjustments"))

    def test_correction_sample_matches_separate_hand_computed_oracle(self):
        self.engine.ingest(SAMPLE / "movements.csv", through="2026-01-04")
        self.engine.ingest(SAMPLE / "corrections.csv", through="2026-01-04")
        with (EXPECTED / "corrected_balances.csv").open(newline="", encoding="utf-8") as stream:
            expected = list(csv.DictReader(stream))
        expected.sort(key=lambda row: (row["balance_date"], row["item_id"], row["location_id"]))
        self.assertEqual(balance_rows(self.engine.report()), expected)

    def test_header_only_input_is_valid(self):
        summary = self.ingest([])
        self.assertEqual(summary["status"], "succeeded")
        self.assertEqual(summary["input_count"], 0)
        self.assertEqual(summary["accepted_count"], 0)
        self.assertEqual(self.engine.report()["balances"], [])

    def test_empty_batch_preserves_existing_balances(self):
        self.ingest([event()])
        before = balance_rows(self.engine.report())
        self.ingest([])
        self.assertEqual(balance_rows(self.engine.report()), before)

    def test_duplicate_import_is_idempotent_including_decimal_normalization(self):
        self.ingest([event(quantity="1"), event(quantity="1.000")])
        before = balance_rows(self.engine.report())
        second = self.ingest([event(quantity="1.0")])
        self.assertEqual(second["accepted_count"], 0)
        self.assertEqual(second["duplicate_count"], 1)
        self.assertEqual(balance_rows(self.engine.report()), before)
        self.assertEqual(self.closing(4), "1.000")

    def test_conflicting_same_version_is_quarantined(self):
        first = self.ingest([event(quantity="5")])
        second = self.ingest([event(quantity="99")])
        self.assertNotEqual(first["run_id"], second["run_id"])
        self.assertEqual(second["status"], "succeeded_with_rejects")
        self.assertEqual(second["accepted_count"], 0)
        self.assertEqual(second["rejected_count"], 1)
        self.assertEqual(self.closing(4), "5.000")
        self.assertTrue(self.engine.report()["rejects"])

    def test_older_revision_arriving_later_cannot_replace_newer_revision(self):
        self.ingest([event(revision="2", quantity="30", effective_date="2026-01-02")])
        summary = self.ingest([event(revision="1", quantity="10")])
        self.assertEqual(summary["accepted_count"], 1)
        self.assertEqual(self.closing(2), "30.000")
        self.assertEqual(self.closing(4), "30.000")

    def test_backdated_quantity_correction_recalculates_later_days(self):
        self.engine.ingest(SAMPLE / "movements.csv", through="2026-01-04")
        self.ingest([event(event_id="receipt-a", revision="2", quantity="120")])
        self.assertEqual([self.closing(day) for day in range(1, 5)],
                         ["120.000", "85.000", "85.000", "85.000"])
        self.assertEqual(self.closing(4, "WH-B"), "24.500")
        self.assertEqual(self.closing(4, item="ITEM-B"), "10.000")

    def test_correction_replaces_date_type_and_location(self):
        self.ingest([
            event(event_id="anchor-a", quantity="1"),
            event(event_id="anchor-b", quantity="1", location_id="WH-B"),
            event(event_id="change", quantity="10", effective_date="2026-01-02"),
        ])
        self.ingest([event(event_id="change", revision="2", quantity="-3",
                           movement_type="ADJUSTMENT", effective_date="2026-01-03",
                           location_id="WH-B")])
        self.assertEqual([self.closing(day) for day in range(1, 5)], ["1.000"] * 4)
        self.assertEqual([self.closing(day, "WH-B") for day in range(1, 5)],
                         ["1.000", "1.000", "-2.000", "-2.000"])

    def test_transfer_correction_updates_both_legs(self):
        self.ingest([
            event(event_id="stock", quantity="100"),
            event(event_id="dest-anchor", quantity="1", location_id="WH-B"),
            event(event_id="move", movement_type="TRANSFER", to_location_id="WH-B",
                  effective_date="2026-01-02", quantity="20"),
        ])
        self.ingest([event(event_id="move", revision="2", movement_type="TRANSFER",
                           to_location_id="WH-B", effective_date="2026-01-03", quantity="30")])
        self.assertEqual(self.closing(2), "100.000")
        self.assertEqual(self.closing(2, "WH-B"), "1.000")
        self.assertEqual(self.closing(4), "70.000")
        self.assertEqual(self.closing(4, "WH-B"), "31.000")

    def test_void_replaces_contribution_and_later_revision_can_restore(self):
        self.ingest([event(event_id="anchor", quantity="1"), event(event_id="void-me", quantity="9")])
        self.ingest([event(event_id="void-me", revision="2", quantity="9", is_void="true")])
        self.assertEqual(self.closing(4), "1.000")
        self.ingest([event(event_id="void-me", revision="3", quantity="4", is_void="false")])
        self.assertEqual(self.closing(4), "5.000")

    def test_malformed_rows_are_quarantined_while_valid_rows_commit(self):
        invalid = [
            event(event_id=""),
            event(event_id="null-quantity", quantity=""),
            event(event_id="null-date", effective_date=""),
            event(event_id="bad-date", effective_date="2026-02-30"),
            event(event_id="unknown-item", item_id="UNKNOWN"),
            event(event_id="unknown-location", location_id="UNKNOWN"),
            event(event_id="unknown-destination", movement_type="TRANSFER", to_location_id="UNKNOWN"),
            event(event_id="precision", quantity="1.0001"),
            event(event_id="nan", quantity="NaN"),
            event(event_id="over-limit", quantity="1000000000.001"),
            event(event_id="negative-receipt", quantity="-1"),
            event(event_id="zero-issue", movement_type="ISSUE", quantity="0"),
            event(event_id="zero-adjustment", movement_type="ADJUSTMENT", quantity="0"),
            event(event_id="missing-destination", movement_type="TRANSFER"),
            event(event_id="same-location", movement_type="TRANSFER", to_location_id="WH-A"),
            event(event_id="unknown-type", movement_type="MAGIC"),
            event(event_id="bad-bool", is_void="maybe"),
            event(event_id="bad-revision", revision="first"),
            event(event_id="invalid-void", quantity="", is_void="true"),
        ]
        summary = self.ingest([event(event_id="valid", quantity="2.125")] + invalid)
        self.assertEqual(summary["status"], "succeeded_with_rejects")
        self.assertEqual(summary["input_count"], len(invalid) + 1)
        self.assertEqual(summary["accepted_count"], 1)
        self.assertEqual(summary["rejected_count"], len(invalid))
        self.assertEqual(len(self.engine.report()["rejects"]), len(invalid))
        self.assertEqual(self.closing(4), "2.125")

    def test_wrong_row_width_rejects_only_bad_rows(self):
        path = self.path / "bad-width.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADER)
            writer.writerow(list(event(event_id="good").values()))
            writer.writerow(["too", "short"])
            writer.writerow(list(event(event_id="long").values()) + ["extra"])
        summary = self.engine.ingest(path, through="2026-01-04")
        self.assertEqual(summary["accepted_count"], 1)
        self.assertEqual(summary["rejected_count"], 2)
        self.assertEqual(self.closing(4), "10.000")

    def test_changed_missing_duplicate_or_empty_header_fails_observably(self):
        headers = [HEADER[:-1], HEADER + ("new_column",), HEADER[:-1] + ("quantity",), ()]
        for header in headers:
            with self.subTest(header=header):
                path = self.csv([], header=header)
                with self.assertRaises(PipelineError):
                    self.engine.ingest(path, through="2026-01-04")
                self.assertEqual(self.engine.report()["runs"][-1]["status"], "failed")
        self.assertEqual(self.engine.report()["balances"], [])

    def test_failure_rolls_back_ledger_and_publication_then_retry_succeeds(self):
        self.ingest([event(event_id="existing", quantity="5")])
        before = balance_rows(self.engine.report())
        batch = self.csv([event(event_id="new", quantity="7")])
        with self.assertRaises(PipelineError):
            self.engine.ingest(batch, through="2026-01-04", fail_before_publish=True)
        report = self.engine.report()
        self.assertEqual(balance_rows(report), before)
        failed = [run for run in report["runs"] if run["status"] == "failed"]
        self.assertTrue(failed)
        self.assertEqual(failed[-1]["rolled_back_count"], 1)
        result = self.engine.ingest(batch, through="2026-01-04")
        self.assertEqual(result["accepted_count"], 1)
        self.assertEqual(result["duplicate_count"], 0)
        self.assertEqual(self.closing(4), "12.000")

    def test_fatal_csv_after_valid_row_rolls_back_and_retains_raw_audit(self):
        self.ingest([event(event_id="existing", quantity="5")])
        before = balance_rows(self.engine.report())
        path = self.path / "unterminated.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.writer(stream)
            writer.writerow(HEADER)
            writer.writerow(event(event_id="pending", quantity="7").values())
            stream.write('"unterminated,1,2026-01-01,RECEIPT,ITEM-A,WH-A,,2,false\n')
        with self.assertRaises(PipelineError):
            self.engine.ingest(path, through="2026-01-04")
        self.assertEqual(balance_rows(self.engine.report()), before)
        with self.engine.connect() as connection:
            run = dict(connection.execute("SELECT * FROM runs WHERE source_file='unterminated.csv'").fetchone())
            raw = [dict(row) for row in connection.execute("SELECT * FROM raw_records WHERE run_id=?", (run["run_id"],))]
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM movement_versions WHERE event_id='pending'").fetchone()[0], 0)
        self.assertEqual(run["status"], "failed")
        self.assertEqual(run["input_count"], 1)
        self.assertEqual(run["accepted_count"], 0)
        self.assertEqual(run["rolled_back_count"], 1)
        self.assertEqual(len(raw), 1)
        self.assertEqual(raw[0]["outcome"], "rolled_back")
        self.assertIn('"event_id": "pending"', raw[0]["raw_json"])
        retry = self.ingest([event(event_id="pending", quantity="7")])
        self.assertEqual(retry["accepted_count"], 1)
        self.assertEqual(self.closing(4), "12.000")

    def test_invalid_horizon_fails_before_mutation_with_zero_consumed_rows(self):
        self.ingest([event(event_id="existing", quantity="5")])
        before = balance_rows(self.engine.report())
        path = self.csv([event(event_id="pending", quantity="7")])
        with self.assertRaises(PipelineError):
            self.engine.ingest(path, through="2026-02-30")
        self.assertEqual(balance_rows(self.engine.report()), before)
        with self.engine.connect() as connection:
            failed = dict(connection.execute("SELECT * FROM runs WHERE status='failed'").fetchone())
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM raw_records WHERE run_id=?", (failed["run_id"],)).fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM movement_versions WHERE event_id='pending'").fetchone()[0], 0)
        self.assertEqual(failed["input_count"], 0)
        self.assertEqual(failed["rolled_back_count"], 0)

    def test_raw_record_outcomes_and_accounting_survive_mixed_batch_failure_retry(self):
        self.ingest([event(event_id="existing", quantity="5")])
        path = self.csv([
            event(event_id="existing", quantity="5"),
            event(event_id="new", quantity="7"),
            event(event_id="invalid", quantity="NaN"),
        ])
        with self.assertRaises(PipelineError):
            self.engine.ingest(path, through="2026-01-04", fail_before_publish=True)
        retry = self.engine.ingest(path, through="2026-01-04")
        with self.engine.connect() as connection:
            runs = [dict(row) for row in connection.execute("SELECT * FROM runs")]
            raw_by_run = {
                run["run_id"]: [row[0] for row in connection.execute(
                    "SELECT outcome FROM raw_records WHERE run_id=? ORDER BY row_number", (run["run_id"],))]
                for run in runs
            }
        failed = next(run for run in runs if run["status"] == "failed")
        self.assertEqual(raw_by_run[failed["run_id"]], ["duplicate", "rolled_back", "rejected"])
        self.assertEqual(raw_by_run[retry["run_id"]], ["duplicate", "accepted", "rejected"])
        for run in runs:
            self.assertEqual(run["input_count"], len(raw_by_run[run["run_id"]]))
            self.assertEqual(run["input_count"], sum(run[name] for name in
                             ("accepted_count", "duplicate_count", "rejected_count", "rolled_back_count")))
        self.assertEqual(self.closing(4), "12.000")
        self.assertTrue(all(check["passed"] for check in self.engine.report()["reconciliation"]))

    def test_catalog_duplicate_and_unit_changes_rollback_all_catalog_additions(self):
        locations = self.path / "locations.csv"
        locations.write_text("location_id\nNEW-WH\n", encoding="utf-8")
        items = self.path / "items.csv"
        items.write_text("item_id,unit\nNEW-ITEM,EA\nITEM-A,KG\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.engine.load_catalogs(items, locations)
        with self.engine.connect() as connection:
            self.assertIsNone(connection.execute("SELECT * FROM items WHERE item_id='NEW-ITEM'").fetchone())
            self.assertIsNone(connection.execute("SELECT * FROM locations WHERE location_id='NEW-WH'").fetchone())
            self.assertEqual(connection.execute("SELECT unit FROM items WHERE item_id='ITEM-A'").fetchone()[0], "EA")
        items.write_text("item_id,unit\nNEW-ITEM,EA\nNEW-ITEM,EA\n", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.engine.load_catalogs(items, locations)
        with self.engine.connect() as connection:
            self.assertIsNone(connection.execute("SELECT * FROM items WHERE item_id='NEW-ITEM'").fetchone())

    def test_later_through_cannot_truncate_published_horizon(self):
        self.ingest([event()])
        self.engine.ingest(self.csv([event(revision="2", quantity="11")]), through="2026-01-02")
        self.assertEqual(self.closing(4), "11.000")

    def test_latest_event_extends_horizon_and_gap_days(self):
        self.engine.ingest(self.csv([event(), event(event_id="later", effective_date="2026-01-07", quantity="2")]),
                           through="2026-01-04")
        self.assertEqual(self.closing(6), "10.000")
        self.assertEqual(self.closing(7), "12.000")

    def test_maximum_quantity_and_fraction_are_exact(self):
        self.ingest([event(event_id="max", quantity="1000000000"),
                     event(event_id="small", movement_type="ISSUE", quantity="0.001")])
        self.assertEqual(self.closing(4), "999999999.999")

    def test_calendar_gap_includes_leap_day(self):
        self.engine.ingest(self.csv([
            event(event_id="before-leap", effective_date="2024-02-28", quantity="2"),
            event(event_id="after-leap", effective_date="2024-03-01", quantity="3"),
        ]), through="2024-03-01")
        rows = self.balances()
        self.assertEqual(rows[("2024-02-29", "ITEM-A", "WH-A")]["closing"], "2.000")
        self.assertEqual(rows[("2024-03-01", "ITEM-A", "WH-A")]["opening"], "2.000")
        self.assertEqual(len(rows), 3)

    def test_last_supported_calendar_date_can_be_published(self):
        summary = self.engine.ingest(self.csv([event(effective_date="9999-12-31")]), through="9999-12-31")
        self.assertEqual(summary["status"], "succeeded")
        self.assertEqual(self.balances()[("9999-12-31", "ITEM-A", "WH-A")]["closing"], "10.000")

    def test_negative_stock_is_allowed_and_visibly_flagged(self):
        self.ingest([event(movement_type="ISSUE", quantity="1")])
        report = self.engine.report()
        self.assertEqual(self.closing(4), "-1.000")
        self.assertEqual(report["metrics"]["negative_balance_days"], 4)
        self.assertTrue(all(row["is_negative"] for row in report["balances"]))
        self.assertTrue(all(check["passed"] for check in report["reconciliation"]))

    def test_reconciliation_detects_same_net_daily_measure_corruption(self):
        self.ingest([event(quantity="10")])
        with self.engine.connect() as connection:
            # A same-net alteration preserves daily equations, continuity, and
            # global closing. Posting-to-daily comparison must still detect it.
            connection.execute("""UPDATE daily_balances SET receipts_milli=receipts_milli+1000,
                issues_milli=issues_milli+1000 WHERE balance_date='2026-01-01'""")
        self.assertTrue(any(not check["passed"] for check in self.engine.report()["reconciliation"]))

    def test_shuffled_revisions_and_split_batches_match_single_rebuild(self):
        rows = [event(event_id=f"r{i}", quantity=str(i + 1), effective_date=f"2026-01-{i % 4 + 1:02d}")
                for i in range(20)]
        rows += [event(event_id=f"r{i}", revision="2", movement_type="ADJUSTMENT",
                       quantity=str(-i - 1), location_id="WH-B",
                       effective_date=f"2026-01-{(i + 1) % 4 + 1:02d}") for i in range(0, 20, 3)]
        rng = random.Random(72)
        rng.shuffle(rows)
        for offset in range(0, len(rows), 5):
            self.ingest(rows[offset:offset + 5])
        other = Inventory(self.path / "full-rebuild.sqlite")
        other.load_catalogs(SAMPLE / "items.csv", SAMPLE / "locations.csv")
        other.ingest(self.csv(rows), through="2026-01-04")
        self.assertEqual(balance_rows(self.engine.report()), balance_rows(other.report()))


class GeneratorTest(unittest.TestCase):
    def test_reproducible_row_count_types_and_intentional_quality_cases(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            first = generate(root / "first", rows=2000, seed=42)
            second = generate(root / "second", rows=2000, seed=42)
            for key in first:
                self.assertEqual(Path(first[key]).read_bytes(), Path(second[key]).read_bytes())
            with Path(first["movements"]).open(newline="", encoding="utf-8") as stream:
                reader = csv.DictReader(stream)
                self.assertEqual(tuple(reader.fieldnames), HEADER)
                rows = list(reader)
            self.assertEqual(len(rows), 2000)
            self.assertEqual({row["movement_type"] for row in rows},
                             {"RECEIPT", "ISSUE", "TRANSFER", "ADJUSTMENT"})
            self.assertTrue(any(row["quantity"] == "1.0001" for row in rows))
            self.assertTrue(any(row["revision"] == "2" for row in rows))
            self.assertLess(len({(row["event_id"], row["revision"]) for row in rows}), len(rows))
            self.assertNotEqual([row["effective_date"] for row in rows],
                                sorted(row["effective_date"] for row in rows))

    def test_100k_generator_covers_all_types_and_source_locations_for_every_item(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = generate(temporary, rows=100000, seed=42)
            metadata = json.loads(Path(paths["coverage"]).read_text(encoding="utf-8"))
            per_item = defaultdict(lambda: {"types": Counter(), "locations": set(), "rows": 0})
            actual_counts = Counter(new=0, duplicate=0, invalid_precision=0, revision=0)
            first_cycle = []
            adjustment_signs = Counter(positive=0, negative=0)
            with Path(paths["movements"]).open(newline="", encoding="utf-8") as stream:
                for ordinal, row in enumerate(csv.DictReader(stream), 1):
                    quality = ("duplicate" if ordinal % 101 == 0 else
                               "invalid_precision" if ordinal % 127 == 0 else
                               "revision" if ordinal % 503 == 0 else "new")
                    actual_counts[quality] += 1
                    if quality != "new":
                        continue
                    account = per_item[row["item_id"]]
                    account["types"][row["movement_type"]] += 1
                    account["locations"].add(row["location_id"])
                    account["rows"] += 1
                    if len(first_cycle) < 400:
                        first_cycle.append((row["item_id"], row["movement_type"]))
                    if row["movement_type"] == "ADJUSTMENT":
                        adjustment_signs["negative" if row["quantity"].startswith("-") else "positive"] += 1
            self.assertEqual(len(first_cycle), 400)
            self.assertEqual(len(set(first_cycle)), 400)
            self.assertEqual(actual_counts, {"new": 98034, "duplicate": 990,
                                             "invalid_precision": 780, "revision": 196})
            self.assertEqual(metadata["counts"], actual_counts)
            self.assertEqual(metadata["generator_version"], "2")
            self.assertEqual(metadata["seed"], 42)
            self.assertEqual(metadata["physical_rows"], 100000)
            self.assertGreater(metadata["arrival_order"]["adjacent_date_inversions"], 0)
            coverage = metadata["normal_coverage"]
            self.assertEqual(coverage["items_with_all_movement_types"], 100)
            self.assertEqual(coverage["items_with_all_source_locations"], 100)
            self.assertEqual(coverage["distinct_item_source_locations"], 800)
            self.assertEqual(coverage["adjustment_signs"], adjustment_signs)
            self.assertGreater(adjustment_signs["positive"], 0)
            self.assertGreater(adjustment_signs["negative"], 0)
            self.assertEqual(len(per_item), 100)
            for item, actual in per_item.items():
                with self.subTest(item=item):
                    self.assertEqual(set(actual["types"]), {"RECEIPT", "ISSUE", "TRANSFER", "ADJUSTMENT"})
                    self.assertEqual(len(actual["locations"]), 8)
                    recorded = coverage["per_item"][item]
                    self.assertEqual(recorded["type_counts"], actual["types"])
                    self.assertEqual(recorded["source_locations"], sorted(actual["locations"]))
                    self.assertEqual(recorded["normal_rows"], actual["rows"])

    def test_zero_and_invalid_row_counts(self):
        with tempfile.TemporaryDirectory() as temporary:
            paths = generate(temporary, rows=0)
            with Path(paths["movements"]).open(newline="", encoding="utf-8") as stream:
                self.assertEqual(list(csv.DictReader(stream)), [])
            coverage = json.loads(Path(paths["coverage"]).read_text(encoding="utf-8"))
            self.assertEqual(sum(coverage["counts"].values()), 0)
            self.assertEqual(coverage["normal_coverage"]["items_with_normal_rows"], 0)
            self.assertEqual(coverage["date_range"], {"first": None, "last": None})
            for count in (-1, 1.5, True):
                with self.subTest(count=count), self.assertRaises(ValueError):
                    generate(temporary, rows=count)


if __name__ == "__main__":
    unittest.main()
