"""Independent business acceptance checks; no pipeline derivation helpers used.

The reference model simulates integer-thousandth stock transitions by calendar
day from immutable domain events. It knows nothing about SQLite postings or the
pipeline's materialization functions. Six fixed seeds make failures reproducible.
"""

from collections import Counter, defaultdict
import csv
from dataclasses import dataclass, replace
from datetime import date, timedelta
from decimal import Decimal
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest import mock

from inventory.pipeline import Inventory, PipelineError


HEADER = ("event_id", "revision", "effective_date", "movement_type", "item_id",
          "location_id", "to_location_id", "quantity", "is_void")
MEASURES = ("opening", "receipts", "issues", "transfers_in", "transfers_out", "adjustments", "closing")
ITEMS = ("ITEM-A", "ITEM-B", "ITEM-C")
LOCATIONS = ("LOC-1", "LOC-2", "LOC-3")
THROUGH = "2026-01-10"
SEEDS = (3, 17, 42, 73, 101, 2026)


def quantity(milli):
    """Independent exact serialization; no runtime formatting helper imported."""
    return format(Decimal(milli) / Decimal(1000), ".3f")


@dataclass(frozen=True)
class Movement:
    key: str
    revision: int
    day: str
    kind: str
    item: str
    source: str
    milli: int
    destination: str = ""
    void: bool = False

    def source_row(self):
        return dict(zip(HEADER, (self.key, str(self.revision), self.day, self.kind,
                                self.item, self.source, self.destination,
                                quantity(self.milli), str(self.void).lower())))


def active_events(accepted_versions):
    current = {}
    for event in accepted_versions:
        previous = current.get(event.key)
        if previous is None or event.revision > previous.revision:
            current[event.key] = event
    return [event for event in current.values() if not event.void]


def independent_daily_oracle(accepted_versions, through=THROUGH):
    """Simulate on-hand stock and daily counters directly from domain events."""
    current = active_events(accepted_versions)
    if not current:
        return {}
    first = {}
    schedule = defaultdict(list)
    for event in current:
        schedule[event.day].append(event)
        touched = [(event.item, event.source)]
        if event.kind == "TRANSFER":
            touched.append((event.item, event.destination))
        for account in touched:
            first[account] = min(first.get(account, event.day), event.day)
    on_hand = defaultdict(int)
    answer = {}
    day = date.fromisoformat(min(first.values()))
    last = date.fromisoformat(through)
    while day <= last:
        business_day = day.isoformat()
        opening = dict(on_hand)
        counters = defaultdict(Counter)
        for event in schedule[business_day]:
            source = event.item, event.source
            if event.kind == "RECEIPT":
                on_hand[source] += event.milli
                counters[source]["receipts"] += event.milli
            elif event.kind == "ISSUE":
                on_hand[source] -= event.milli
                counters[source]["issues"] += event.milli
            elif event.kind == "ADJUSTMENT":
                on_hand[source] += event.milli
                counters[source]["adjustments"] += event.milli
            elif event.kind == "TRANSFER":
                target = event.item, event.destination
                on_hand[source] -= event.milli
                on_hand[target] += event.milli
                counters[source]["transfers_out"] += event.milli
                counters[target]["transfers_in"] += event.milli
            else:
                raise AssertionError("invalid kind in reference scenario")
        for account in first:
            if first[account] > business_day:
                continue
            fields = dict(counters[account])
            fields["opening"] = opening.get(account, 0)
            fields["closing"] = on_hand[account]
            answer[(business_day, *account)] = {
                **{name: quantity(fields.get(name, 0)) for name in MEASURES},
                "is_negative": fields["closing"] < 0,
            }
        day += timedelta(days=1)
    return answer


def anchors():
    return [Movement(f"anchor-{item}-{location}", 1, "2026-01-01", "RECEIPT", item, location, 5000)
            for item in ITEMS for location in LOCATIONS]


def seeded_events(seed):
    rng = random.Random(seed)
    events = anchors()
    for item in ITEMS:
        for index in range(24):
            kind = ("RECEIPT", "ISSUE", "TRANSFER", "ADJUSTMENT")[index % 4]
            source = rng.choice(LOCATIONS)
            destination = rng.choice([location for location in LOCATIONS if location != source]) if kind == "TRANSFER" else ""
            amount = rng.randint(1, 40000)
            if kind == "ADJUSTMENT" and index % 8 == 3:
                amount = -amount
            events.append(Movement(f"seed-{seed}-{item}-{index}", 1, f"2026-01-{rng.randint(2, 9):02d}",
                                   kind, item, source, amount, destination))
    # Deliberately oversold: no random subset can conceal all negative stock.
    events.append(Movement(f"seed-{seed}-oversold", 1, "2026-01-02", "ISSUE", "ITEM-A", "LOC-1", 1000000))
    rng.shuffle(events)
    return events


class InventoryAcceptanceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.sequence = 0
        (self.root / "items.csv").write_text("item_id,unit\nITEM-A,EA\nITEM-B,KG\nITEM-C,L\n", encoding="utf-8")
        (self.root / "locations.csv").write_text("location_id\nLOC-1\nLOC-2\nLOC-3\n", encoding="utf-8")

    def inventory(self):
        self.sequence += 1
        inventory = Inventory(self.root / f"inventory-{self.sequence}.db")
        inventory.load_catalogs(self.root / "items.csv", self.root / "locations.csv")
        return inventory

    def source(self, events_or_rows):
        self.sequence += 1
        path = self.root / f"batch-{self.sequence}.csv"
        with path.open("w", newline="", encoding="utf-8") as stream:
            writer = csv.DictWriter(stream, fieldnames=HEADER)
            writer.writeheader()
            for value in events_or_rows:
                writer.writerow(value.source_row() if isinstance(value, Movement) else value)
        return path

    def ingest(self, inventory, events_or_rows, **options):
        return inventory.ingest(self.source(events_or_rows), through=THROUGH, **options)

    def assert_oracle(self, inventory, accepted_versions):
        report = inventory.report()
        actual = {(row["balance_date"], row["item_id"], row["location_id"]):
                  {name: row[name] for name in (*MEASURES, "is_negative")} for row in report["balances"]}
        expected = independent_daily_oracle(accepted_versions)
        self.assertEqual(actual, expected)
        self.assertEqual(report["metrics"]["negative_balance_days"], sum(row["is_negative"] for row in expected.values()))
        self.assertTrue(all(check["passed"] for check in report["reconciliation"]), report["reconciliation"])
        # Quantities are conserved independently per item; EA, KG and L are never
        # combined into an asserted physical total. Transfers have no external net.
        expected_external = Counter()
        for event in active_events(accepted_versions):
            if event.kind in {"RECEIPT", "ADJUSTMENT"}:
                expected_external[event.item] += event.milli
            elif event.kind == "ISSUE":
                expected_external[event.item] -= event.milli
        last_by_account = {}
        for grain, row in sorted(actual.items()):
            last_by_account[grain[1:]] = row
        actual_by_item = Counter()
        for (item, _), row in last_by_account.items():
            actual_by_item[item] += int(Decimal(row["closing"]) * 1000)
        for item in ITEMS:
            self.assertEqual(actual_by_item[item], expected_external[item], f"external net mismatch for {item}")
        return report

    def test_seeded_shuffled_batches_match_independent_integer_daily_oracle(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                inventory = self.inventory()
                events = seeded_events(seed)
                self.assertEqual(len(events), 82)
                self.assertEqual({event.kind for event in events}, {"RECEIPT", "ISSUE", "TRANSFER", "ADJUSTMENT"})
                accepted = []
                for offset in range(0, len(events), 11):
                    with self.subTest(seed=seed, batch=offset // 11):
                        batch = events[offset:offset + 11]
                        run = self.ingest(inventory, batch)
                        self.assertEqual(run["accepted_count"], len(batch))
                        accepted.extend(batch)
                        self.assert_oracle(inventory, accepted)
                self.assertGreater(inventory.report()["metrics"]["negative_balance_days"], 0)

    def test_full_replacement_revision_matrix_is_arrival_order_independent(self):
        revisions = [
            Movement("replace-me", 1, "2026-01-03", "RECEIPT", "ITEM-A", "LOC-1", 20000),
            Movement("replace-me", 2, "2026-01-05", "TRANSFER", "ITEM-B", "LOC-2", 7125, "LOC-3"),
            Movement("replace-me", 3, "2026-01-02", "TRANSFER", "ITEM-B", "LOC-3", 3375, "LOC-1"),
            Movement("replace-me", 4, "2026-01-04", "ADJUSTMENT", "ITEM-C", "LOC-2", -4125),
            Movement("replace-me", 5, "2026-01-06", "ADJUSTMENT", "ITEM-C", "LOC-2", 6250),
            Movement("replace-me", 6, "2026-01-06", "ADJUSTMENT", "ITEM-C", "LOC-2", 6250, void=True),
            Movement("replace-me", 7, "2026-01-02", "ADJUSTMENT", "ITEM-C", "LOC-2", -2500),
        ]
        final_outputs = []
        for order in ((1, 2, 3, 4, 5, 6, 7), (1, 3, 2, 5, 4, 6, 7), (7, 6, 5, 4, 3, 2, 1)):
            with self.subTest(arrival_order=order):
                inventory = self.inventory()
                accepted = anchors()
                self.ingest(inventory, accepted)
                self.assert_oracle(inventory, accepted)
                for revision in order:
                    self.ingest(inventory, [revisions[revision - 1]])
                    accepted.append(revisions[revision - 1])
                    report = self.assert_oracle(inventory, accepted)
                    self.assertEqual(report["metrics"]["history_versions"], len(accepted))
                final_outputs.append(independent_daily_oracle(accepted))
                self.assertEqual(final_outputs[-1][("2026-01-10", "ITEM-C", "LOC-2")]["closing"], "2.500")
        self.assertEqual(final_outputs[0], final_outputs[1])
        self.assertEqual(final_outputs[1], final_outputs[2])

    def test_canonical_duplicates_conflicts_and_rejected_rows_do_not_replace_accepted_versions(self):
        inventory = self.inventory()
        original = seeded_events(17)
        self.ingest(inventory, original)
        before = self.assert_oracle(inventory, original)
        duplicates = []
        for event in original:
            row = event.source_row()
            row["quantity"] = row["quantity"].rstrip("0").rstrip(".")
            row["is_void"] = " FALSE "
            row["item_id"] = " " + row["item_id"] + " "
            duplicates.append(row)
        conflict = replace(original[0], milli=original[0].milli + 1000).source_row()
        malformed = [
            Movement("invalid-item", 1, "2026-01-02", "RECEIPT", "UNKNOWN", "LOC-1", 1000).source_row(),
            {**Movement("invalid-precision", 1, "2026-01-02", "RECEIPT", "ITEM-A", "LOC-1", 1000).source_row(), "quantity": "1.0001"},
            Movement("invalid-transfer", 1, "2026-01-02", "TRANSFER", "ITEM-A", "LOC-1", 1000, "LOC-1").source_row(),
        ]
        run = self.ingest(inventory, duplicates + [conflict] + malformed)
        self.assertEqual((run["input_count"], run["accepted_count"], run["duplicate_count"], run["rejected_count"]), (86, 0, 82, 4))
        after = self.assert_oracle(inventory, original)
        self.assertEqual(after["metrics"]["history_versions"], before["metrics"]["history_versions"])
        self.assertTrue(any("conflicting payload" in row["reason"] for row in after["rejects"]))
        correction = replace(original[0], revision=2, milli=original[0].milli + 1000)
        corrected = self.ingest(inventory, [correction])
        self.assertEqual(corrected["accepted_count"], 1)
        self.assert_oracle(inventory, original + [correction])

    def test_negative_stock_carries_exact_fractional_quantities_through_gap_days(self):
        inventory = self.inventory()
        events = [
            Movement("opening-ea", 1, "2026-01-01", "RECEIPT", "ITEM-A", "LOC-1", 2125),
            Movement("oversold-ea", 1, "2026-01-02", "ISSUE", "ITEM-A", "LOC-1", 3250),
            Movement("late-receipt-ea", 1, "2026-01-05", "RECEIPT", "ITEM-A", "LOC-1", 125),
            Movement("signed-adjustment-ea", 1, "2026-01-07", "ADJUSTMENT", "ITEM-A", "LOC-1", -375),
            Movement("separate-kg", 1, "2026-01-01", "RECEIPT", "ITEM-B", "LOC-2", 1500),
        ]
        self.ingest(inventory, list(reversed(events)))
        report = self.assert_oracle(inventory, events)
        series = {row["balance_date"]: row for row in report["balances"] if row["item_id"] == "ITEM-A"}
        self.assertEqual(report["metrics"]["negative_balance_days"], 9)
        self.assertEqual([series[f"2026-01-{day:02d}"]["closing"] for day in range(1, 11)],
                         ["2.125", "-1.125", "-1.125", "-1.125", "-1.000", "-1.000", "-1.375", "-1.375", "-1.375", "-1.375"])
        self.assertEqual(series["2026-01-04"]["opening"], "-1.125")
        self.assertEqual(series["2026-01-04"]["receipts"], "0.000")

    def test_per_item_reconciliation_detects_errors_hidden_by_unchanged_global_checksum(self):
        inventory = self.inventory()
        events = [Movement("ea", 1, "2026-01-01", "RECEIPT", "ITEM-A", "LOC-1", 10000),
                  Movement("kg", 1, "2026-01-01", "RECEIPT", "ITEM-B", "LOC-2", 20000)]
        self.ingest(inventory, events)
        self.assert_oracle(inventory, events)
        with inventory.connect() as connection:
            connection.execute("UPDATE daily_balances SET closing_milli=closing_milli+1000 WHERE balance_date=? AND item_id='ITEM-A'", (THROUGH,))
            connection.execute("UPDATE daily_balances SET closing_milli=closing_milli-1000 WHERE balance_date=? AND item_id='ITEM-B'", (THROUGH,))
        checks = {check["check_name"]: check for check in inventory.report()["reconciliation"]}
        self.assertTrue(checks["global_closing_stock"]["passed"])
        self.assertFalse(checks["item_closing_stock_violations"]["passed"])
        self.assertEqual(checks["item_closing_stock_violations"]["actual"], "2")

    def test_atomic_backdated_transfer_replacement_rolls_back_every_account_and_retries(self):
        inventory = self.inventory()
        original = anchors() + [Movement("replace-on-retry", 1, "2026-01-05", "RECEIPT", "ITEM-A", "LOC-1", 20000)]
        self.ingest(inventory, original)
        self.assert_oracle(inventory, original)
        correction = Movement("replace-on-retry", 2, "2026-01-02", "TRANSFER", "ITEM-B", "LOC-3", 12500, "LOC-1")
        new_receipt = Movement("new-on-retry", 1, "2026-01-04", "RECEIPT", "ITEM-C", "LOC-2", 500)
        invalid = Movement("reject-on-retry", 1, "2026-01-02", "RECEIPT", "UNKNOWN", "LOC-1", 1000)
        batch = self.source([correction, new_receipt, original[0], invalid])
        with self.assertRaises(PipelineError):
            inventory.ingest(batch, through=THROUGH, fail_before_publish=True)
        failed_report = self.assert_oracle(inventory, original)
        failed = next(run for run in failed_report["runs"] if run["status"] == "failed")
        self.assertEqual((failed["input_count"], failed["accepted_count"], failed["duplicate_count"], failed["rejected_count"], failed["rolled_back_count"]), (4, 0, 1, 1, 2))
        self.assertFalse(inventory.changes(failed["run_id"])["has_snapshot"])
        with inventory.connect() as connection:
            outcomes = [row[0] for row in connection.execute("SELECT outcome FROM raw_records WHERE run_id=? ORDER BY row_number", (failed["run_id"],))]
        self.assertEqual(outcomes, ["rolled_back", "rolled_back", "duplicate", "rejected"])
        retry = inventory.ingest(batch, through=THROUGH)
        self.assertEqual((retry["accepted_count"], retry["duplicate_count"], retry["rejected_count"]), (2, 1, 1))
        report = self.assert_oracle(inventory, original + [correction, new_receipt])
        self.assertEqual(report["metrics"]["history_versions"], 12)

    def test_replacement_void_and_restore_remove_obsolete_series_and_leading_days(self):
        inventory = self.inventory()
        accepted = []
        versions = [
            Movement("moving-series", 1, "2026-01-01", "RECEIPT", "ITEM-A", "LOC-1", 3000),
            Movement("moving-series", 2, "2026-01-05", "RECEIPT", "ITEM-B", "LOC-3", 4500),
            Movement("moving-series", 3, "2026-01-05", "RECEIPT", "ITEM-B", "LOC-3", 4500, void=True),
            Movement("moving-series", 4, "2026-01-03", "RECEIPT", "ITEM-B", "LOC-3", 5250),
        ]
        for version, expected_rows in zip(versions, (10, 6, 0, 8)):
            with self.subTest(revision=version.revision):
                self.ingest(inventory, [version])
                accepted.append(version)
                report = self.assert_oracle(inventory, accepted)
                self.assertEqual(report["metrics"]["daily_rows"], expected_rows)
                self.assertEqual(report["published_through"], THROUGH)
        self.assertTrue(all(row["item_id"] == "ITEM-B" and row["location_id"] == "LOC-3" for row in report["balances"]))

    def test_export_keeps_one_snapshot_when_another_writer_commits_mid_export(self):
        exporting = self.inventory()
        initial_events = [
            Movement("snapshot-receipt", 1, "2026-01-01", "RECEIPT", "ITEM-A", "LOC-1", 10000),
            Movement("snapshot-transfer", 1, "2026-01-02", "TRANSFER", "ITEM-A", "LOC-1", 2000, "LOC-2"),
        ]
        initial = self.ingest(exporting, initial_events)
        writer = Inventory(exporting.db_path)
        correction = replace(initial_events[0], revision=2, milli=15000)
        later_receipt = Movement("snapshot-later", 1, "2026-01-03", "RECEIPT", "ITEM-B", "LOC-3", 5000)
        original_report = exporting.report
        committed_runs = []

        def read_report_then_commit(*args, **kwargs):
            self.assertIsNotNone(kwargs.get("_connection"), "export must share its read transaction with report")
            snapshot = original_report(*args, **kwargs)
            # Commit synchronously after JSON values are read but before export
            # reads its remaining raw/version/posting/change CSV datasets.
            committed_runs.append(self.ingest(writer, [correction, later_receipt]))
            return snapshot

        directory = self.root / "snapshot-export"
        with mock.patch.object(exporting, "report", side_effect=read_report_then_commit):
            exported = exporting.export(directory)
        self.assertEqual(len(committed_runs), 1)
        self.assertIn("balance_changes.csv", exported["files"])
        snapshot = json.loads((directory / "report.json").read_text(encoding="utf-8"))
        self.assertEqual((snapshot["metrics"]["current_events"], snapshot["metrics"]["history_versions"]), (2, 2))
        self.assertEqual({run["run_id"] for run in snapshot["runs"]}, {initial["run_id"]})
        self.assertTrue(all(check["passed"] for check in snapshot["reconciliation"]))

        def csv_dataset(name):
            with (directory / (name + ".csv")).open(newline="", encoding="utf-8") as stream:
                return list(csv.DictReader(stream))

        daily = csv_dataset("daily_balances")
        exported_business = {
            (row["balance_date"], row["item_id"], row["location_id"]):
            {**{name: row[name] for name in MEASURES}, "is_negative": row["is_negative"] == "True"}
            for row in daily
        }
        self.assertEqual(exported_business, independent_daily_oracle(initial_events))
        self.assertEqual(len(daily), 19)
        self.assertEqual({row["last_run_id"] for row in daily}, {initial["run_id"]})
        self.assertEqual({row["run_id"] for row in csv_dataset("runs")}, {initial["run_id"]})
        raw = csv_dataset("raw_records")
        self.assertEqual(len(raw), 2)
        self.assertEqual({row["run_id"] for row in raw}, {initial["run_id"]})
        self.assertEqual({json.loads(row["raw_json"])["event_id"] for row in raw}, {event.key for event in initial_events})
        versions = csv_dataset("movement_versions")
        self.assertEqual({(row["event_id"], row["revision"]) for row in versions},
                         {("snapshot-receipt", "1"), ("snapshot-transfer", "1")})
        self.assertEqual({row["run_id"] for row in versions}, {initial["run_id"]})
        postings = csv_dataset("postings")
        self.assertEqual(len(postings), 3)
        self.assertEqual({(row["event_id"], row["revision"]) for row in postings},
                         {("snapshot-receipt", "1"), ("snapshot-transfer", "1")})
        self.assertEqual(sum(int(row["receipts_milli"]) for row in postings), 10000)
        self.assertEqual(sum(int(row["transfers_in_milli"]) for row in postings), 2000)
        self.assertEqual(sum(int(row["transfers_out_milli"]) for row in postings), 2000)
        changes = csv_dataset("balance_changes")
        self.assertEqual(len(changes), 19)
        self.assertEqual({row["run_id"] for row in changes}, {initial["run_id"]})
        self.assertTrue(all(row["before_json"] == "" for row in changes))
        self.assertTrue(all(row["passed"] == "True" for row in csv_dataset("reconciliation")))

        live = self.assert_oracle(writer, initial_events + [correction, later_receipt])
        self.assertEqual((live["metrics"]["current_events"], live["metrics"]["history_versions"]), (3, 4))
        self.assertEqual(len(live["runs"]), 2)
        live_last = {(row["item_id"], row["location_id"]): row["closing"]
                     for row in live["balances"] if row["balance_date"] == THROUGH}
        self.assertEqual(live_last, {("ITEM-A", "LOC-1"): "13.000", ("ITEM-A", "LOC-2"): "2.000", ("ITEM-B", "LOC-3"): "5.000"})
        self.assertNotIn(committed_runs[0]["run_id"], {row["run_id"] for row in versions + raw + changes})


if __name__ == "__main__":
    unittest.main()
