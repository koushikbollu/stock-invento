"""The default interactive demo has 50 curated events and safe repeat behavior."""

import contextlib
import csv
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from inventory.cli import main
from inventory.pipeline import Inventory, PipelineError
from inventory import demo as demo_module


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "data" / "demo"
SAMPLE = ROOT / "data" / "sample"


def csv_rows(path):
    with path.open(newline="", encoding="utf-8") as stream:
        return list(csv.DictReader(stream))


class DefaultDemoTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.out = Path(self.temporary.name) / "demo"

    def run_demo(self):
        captured = io.StringIO()
        with contextlib.redirect_stdout(captured), mock.patch("inventory.cli.logging.basicConfig"):
            status = main(["demo", "--out", str(self.out)])
        self.assertEqual(status, 0)
        return json.loads(captured.getvalue()), Inventory(self.out / "inventory.db")

    @staticmethod
    def business_balances(inventory):
        return [{key: value for key, value in row.items() if key != "last_run_id"}
                for row in inventory.report()["balances"]]

    def test_curated_file_has_exactly_fifty_distinct_events_and_preserves_sample_prefix(self):
        rows = csv_rows(DEMO / "movements.csv")
        self.assertEqual(len(rows), 50)
        self.assertEqual(len({row["event_id"] for row in rows}), 50)
        self.assertEqual({row["revision"] for row in rows}, {"1"})
        self.assertEqual(rows[:7], csv_rows(SAMPLE / "movements.csv"))
        self.assertEqual({row["item_id"] for row in rows[7:]}, {"ITEM-C", "ITEM-D", "ITEM-E"})
        self.assertEqual({row["item_id"] for row in rows}, {f"ITEM-{letter}" for letter in "ABCDE"})
        self.assertEqual({row["location_id"] for row in rows}, {"WH-A", "WH-B", "WH-C"})
        self.assertEqual({row["movement_type"] for row in rows}, {"RECEIPT", "ISSUE", "TRANSFER", "ADJUSTMENT"})
        self.assertEqual({row["effective_date"] for row in rows}, {f"2026-01-{day:02d}" for day in range(1, 5)})
        self.assertEqual({row["item_id"] for row in csv_rows(DEMO / "items.csv")}, {f"ITEM-{letter}" for letter in "ABCDE"})
        self.assertEqual({row["location_id"] for row in csv_rows(DEMO / "locations.csv")}, {"WH-A", "WH-B", "WH-C"})

    def test_fresh_default_demo_publishes_fifty_events_and_real_quality_examples(self):
        result, inventory = self.run_demo()
        initial, correction = result["runs"]
        self.assertEqual(initial["input_count"], 50)
        self.assertEqual(initial["accepted_count"], 50)
        self.assertEqual(initial["duplicate_count"], 0)
        self.assertEqual(initial["rejected_count"], 0)
        self.assertEqual(correction["accepted_count"], 1)
        report = inventory.report()
        self.assertEqual(report["metrics"]["current_events"], 50)
        self.assertEqual(report["metrics"]["history_versions"], 53)
        self.assertEqual(report["metrics"]["daily_rows"], 47)
        self.assertEqual(report["metrics"]["negative_balance_days"], 4)
        self.assertEqual(report["metrics"]["rejected_rows"], 3)
        self.assertEqual(len(report["runs"]), 7)
        self.assertEqual(sum(run["status"] == "failed" for run in report["runs"]), 1)
        self.assertTrue(all(check["passed"] for check in report["reconciliation"]))
        negative = {(row["balance_date"], row["item_id"], row["location_id"]): row["closing"]
                    for row in report["balances"] if row["is_negative"]}
        self.assertEqual(negative, {
            ("2026-01-02", "ITEM-D", "WH-C"): "-9.875",
            ("2026-01-03", "ITEM-D", "WH-C"): "-14.000",
            ("2026-01-04", "ITEM-D", "WH-C"): "-14.000",
            ("2026-01-04", "ITEM-E", "WH-B"): "-3.625",
        })
        self.assertTrue((self.out / "export" / "report.json").is_file())
        impact = inventory.changes(correction["run_id"])
        self.assertEqual(impact["total"], 4)
        self.assertTrue(all(row["closing_delta"] == "10.000" for row in impact["rows"]))
        self.assertTrue(all((row["item_id"], row["location_id"]) == ("ITEM-A", "WH-A") for row in impact["rows"]))

    def test_original_series_match_existing_oracle_and_new_series_match_hand_calculation(self):
        _, inventory = self.run_demo()
        report = inventory.report()
        expected = csv_rows(ROOT / "data" / "expected" / "corrected_balances.csv")
        fields = list(expected[0])
        original = [{key: row[key] for key in fields} for row in report["balances"] if row["item_id"] in {"ITEM-A", "ITEM-B"}]
        key = lambda row: (row["balance_date"], row["item_id"], row["location_id"])
        self.assertEqual(sorted(original, key=key), sorted(expected, key=key))
        closing = {(row["item_id"], row["location_id"]): row["closing"]
                   for row in report["balances"] if row["balance_date"] == "2026-01-04"}
        self.assertEqual(closing, {
            ("ITEM-A", "WH-A"): "75.000", ("ITEM-A", "WH-B"): "24.500", ("ITEM-B", "WH-A"): "10.000",
            ("ITEM-C", "WH-A"): "186.125", ("ITEM-C", "WH-B"): "57.500", ("ITEM-C", "WH-C"): "32.625",
            ("ITEM-D", "WH-A"): "82.625", ("ITEM-D", "WH-B"): "38.000", ("ITEM-D", "WH-C"): "-14.000",
            ("ITEM-E", "WH-A"): "129.125", ("ITEM-E", "WH-B"): "-3.625", ("ITEM-E", "WH-C"): "27.000",
        })

    def test_repeat_demo_accepts_no_new_versions_and_preserves_business_values(self):
        _, inventory = self.run_demo()
        before = self.business_balances(inventory)
        repeated, inventory = self.run_demo()
        self.assertEqual([run["accepted_count"] for run in repeated["runs"]], [0, 0])
        self.assertEqual([run["duplicate_count"] for run in repeated["runs"]], [50, 1])
        self.assertEqual(self.business_balances(inventory), before)
        report = inventory.report()
        self.assertEqual(report["metrics"]["history_versions"], 53)
        self.assertEqual(report["metrics"]["rejected_rows"], 3)
        self.assertEqual(sum(run["status"] == "failed" for run in report["runs"]), 1)
        self.assertEqual(len(report["runs"]), 9)
        self.assertTrue(all(inventory.changes(run["run_id"])["total"] == 0 for run in repeated["runs"]))

    def test_repeat_demo_retains_additional_existing_user_events(self):
        _, inventory = self.run_demo()
        custom = self.out / "additional.csv"
        custom.write_text("event_id,revision,effective_date,movement_type,item_id,location_id,to_location_id,quantity,is_void\n"
                          "local-added-event,1,2026-01-04,RECEIPT,ITEM-C,WH-A,,3,false\n", encoding="utf-8")
        inventory.ingest(custom, through="2026-01-04")
        before = self.business_balances(inventory)
        repeated, inventory = self.run_demo()
        self.assertEqual([run["accepted_count"] for run in repeated["runs"]], [0, 0])
        self.assertEqual(inventory.report()["metrics"]["current_events"], 51)
        self.assertEqual(self.business_balances(inventory), before)
        closing = next(row["closing"] for row in inventory.report()["balances"]
                       if (row["balance_date"], row["item_id"], row["location_id"]) == ("2026-01-04", "ITEM-C", "WH-A"))
        self.assertEqual(closing, "189.125")

    def test_review_revision_120_preserves_fifty_events_and_raises_original_series_to_85(self):
        _, inventory = self.run_demo()
        review = self.out / "review.csv"
        review.write_text("event_id,revision,effective_date,movement_type,item_id,location_id,to_location_id,quantity,is_void\n"
                          "receipt-a,3,2026-01-01,RECEIPT,ITEM-A,WH-A,,120,false\n", encoding="utf-8")
        run = inventory.ingest(review, through="2026-01-04")
        report = inventory.report()
        self.assertEqual(report["metrics"]["current_events"], 50)
        self.assertEqual(report["metrics"]["history_versions"], 54)
        closing = next(row["closing"] for row in report["balances"]
                       if (row["balance_date"], row["item_id"], row["location_id"]) == ("2026-01-04", "ITEM-A", "WH-A"))
        self.assertEqual(closing, "85.000")
        self.assertEqual(inventory.changes(run["run_id"])["total"], 4)

    def test_each_teaching_scenario_has_real_retained_run_evidence(self):
        result, inventory = self.run_demo()
        examples = result["demo_examples"]
        self.assertEqual(set(examples), {"version", "initial_movement_count", "expected_rejected_rows", "transfer_event_id", "runs"})
        self.assertEqual(examples["version"], 1)
        self.assertEqual(examples["initial_movement_count"], 50)
        self.assertEqual(examples["expected_rejected_rows"], 3)
        self.assertEqual(examples["transfer_event_id"], "demo-c-transfer-1")
        self.assertEqual(set(examples["runs"]), {"initial", "correction", "cancellation", "restoration", "validation", "failure", "recovery"})
        report = inventory.report()
        runs = {run["run_id"]: run for run in report["runs"]}
        self.assertEqual(set(examples["runs"].values()), set(runs))
        validation = runs[examples["runs"]["validation"]]
        self.assertEqual((validation["accepted_count"], validation["rejected_count"]), (0, 3))
        self.assertEqual(validation["status"], "succeeded_with_rejects")
        self.assertEqual({row["run_id"] for row in report["rejects"]}, {validation["run_id"]})
        failure = runs[examples["runs"]["failure"]]
        self.assertEqual(failure["status"], "failed")
        self.assertIn("unexpected schema:", failure["error"])
        self.assertFalse(inventory.changes(failure["run_id"])["has_snapshot"])
        recovery = runs[examples["runs"]["recovery"]]
        self.assertEqual(recovery["status"], "succeeded")
        self.assertEqual((recovery["accepted_count"], recovery["duplicate_count"]), (0, 50))
        self.assertEqual(inventory.changes(recovery["run_id"])["total"], 0)
        cancellation = inventory.changes(examples["runs"]["cancellation"])
        restoration = inventory.changes(examples["runs"]["restoration"])
        self.assertEqual((cancellation["total"], restoration["total"]), (8, 8))
        self.assertEqual({row["closing_delta"] for row in cancellation["rows"]}, {"20.000", "-20.000"})
        with inventory.connect() as connection:
            versions = [tuple(row) for row in connection.execute(
                "SELECT revision,is_void FROM movement_versions WHERE event_id=? ORDER BY revision", (examples["transfer_event_id"],))]
            current = connection.execute("SELECT revision,is_void FROM current_movements WHERE event_id=?", (examples["transfer_event_id"],)).fetchone()
            marker = connection.execute("SELECT value FROM settings WHERE key='demo_examples_v1'").fetchone()[0]
        self.assertEqual(versions, [(1, 0), (2, 1), (3, 0)])
        self.assertEqual(tuple(current), (3, 0))
        self.assertEqual(json.loads(marker), examples)
        repeated, _ = self.run_demo()
        self.assertEqual(repeated["demo_examples"], examples)

    def test_partial_scenario_failure_leaves_no_marker_and_business_retries_safely(self):
        original_ingest = Inventory.ingest

        def interrupted(instance, input_path, *args, **kwargs):
            if Path(input_path).name.startswith("demo_quality_examples."):
                raise OSError("synthetic interruption before validation examples")
            return original_ingest(instance, input_path, *args, **kwargs)

        with mock.patch.object(Inventory, "ingest", interrupted), mock.patch("inventory.cli.logging.basicConfig"), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["demo", "--out", str(self.out)]), 1)
        inventory = Inventory(self.out / "inventory.db")
        self.assertEqual(inventory.report()["metrics"]["current_events"], 50)
        self.assertEqual(inventory.report()["metrics"]["history_versions"], 53)
        with inventory.connect() as connection:
            self.assertIsNone(connection.execute("SELECT value FROM settings WHERE key='demo_examples_v1'").fetchone())
        _, inventory = self.run_demo()
        self.assertEqual(inventory.report()["metrics"]["current_events"], 50)
        self.assertEqual(inventory.report()["metrics"]["history_versions"], 53)
        self.assertEqual(inventory.report()["metrics"]["rejected_rows"], 3)
        self.assertTrue(all(check["passed"] for check in inventory.report()["reconciliation"]))

    def demo_progress(self, inventory):
        with inventory.connect() as connection:
            row = connection.execute("SELECT value FROM settings WHERE key='demo_examples_v1_progress'").fetchone()
        return json.loads(row[0]) if row else None

    def assert_teaching_counts(self, inventory):
        report = inventory.report()
        self.assertEqual(report["metrics"]["current_events"], 50)
        self.assertEqual(report["metrics"]["history_versions"], 53)
        self.assertEqual(report["metrics"]["daily_rows"], 47)
        self.assertEqual(report["metrics"]["negative_balance_days"], 4)
        self.assertEqual(report["metrics"]["rejected_rows"], 3)
        self.assertEqual(sum(run["status"] == "failed" for run in report["runs"]), 1)
        self.assertTrue(all(check["passed"] for check in report["reconciliation"]))

    def interrupted_demo(self, side_effect):
        with mock.patch.object(Inventory, "ingest", side_effect), mock.patch("inventory.cli.logging.basicConfig"), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["demo", "--out", str(self.out)]), 1)
        return Inventory(self.out / "inventory.db")

    def test_restart_immediately_before_recovery_reuses_diagnostic_runs(self):
        original_ingest = Inventory.ingest

        def before_recovery(instance, input_path, *args, **kwargs):
            if Path(input_path).stem.startswith("movements."):
                raise OSError("synthetic interruption before recovery")
            return original_ingest(instance, input_path, *args, **kwargs)

        inventory = self.interrupted_demo(before_recovery)
        self.assert_teaching_counts(inventory)
        progress = self.demo_progress(inventory)
        retained = {name: progress["scenarios"][name]["run_id"] for name in ("validation", "failure")}
        with inventory.connect() as connection:
            self.assertIsNone(connection.execute("SELECT value FROM settings WHERE key='demo_examples_v1'").fetchone())
        result, inventory = self.run_demo()
        self.assert_teaching_counts(inventory)
        self.assertEqual(result["demo_examples"]["runs"]["initial"], progress["initial_run_id"])
        for name, run_id in retained.items():
            self.assertEqual(result["demo_examples"]["runs"][name], run_id)

    def test_validation_commit_before_checkpoint_is_recovered_without_duplicate_rejects(self):
        original_ingest = Inventory.ingest

        def after_validation_commit(instance, input_path, *args, **kwargs):
            run = original_ingest(instance, input_path, *args, **kwargs)
            if Path(input_path).name.startswith("demo_quality_examples."):
                raise OSError("synthetic interruption after committed validation")
            return run

        inventory = self.interrupted_demo(after_validation_commit)
        progress = self.demo_progress(inventory)
        intent = progress["scenarios"]["validation"]
        self.assertNotIn("run_id", intent)
        with inventory.connect() as connection:
            committed = connection.execute("SELECT run_id FROM runs WHERE source_file=?", (intent["source_file"],)).fetchone()[0]
        self.assertEqual(inventory.report()["metrics"]["rejected_rows"], 3)
        result, inventory = self.run_demo()
        self.assert_teaching_counts(inventory)
        self.assertEqual(result["demo_examples"]["runs"]["validation"], committed)

    def test_expected_failure_commit_before_checkpoint_is_recovered_without_extra_failures(self):
        original_save = demo_module._save_progress

        def before_failure_checkpoint(inventory, progress):
            if progress["scenarios"].get("failure", {}).get("run_id"):
                raise OSError("synthetic interruption before failure checkpoint")
            return original_save(inventory, progress)

        with mock.patch.object(demo_module, "_save_progress", before_failure_checkpoint), mock.patch("inventory.cli.logging.basicConfig"), contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(main(["demo", "--out", str(self.out)]), 1)
        inventory = Inventory(self.out / "inventory.db")
        self.assert_teaching_counts(inventory)
        intent = self.demo_progress(inventory)["scenarios"]["failure"]
        self.assertNotIn("run_id", intent)
        with inventory.connect() as connection:
            committed = connection.execute("SELECT run_id FROM runs WHERE source_file=?", (intent["source_file"],)).fetchone()[0]
        result, inventory = self.run_demo()
        self.assert_teaching_counts(inventory)
        self.assertEqual(result["demo_examples"]["runs"]["failure"], committed)

    def test_coincidental_user_template_filenames_are_never_claimed_as_seeded_runs(self):
        inventory = Inventory(self.out / "inventory.db")
        inventory.load_catalogs(DEMO / "items.csv", DEMO / "locations.csv")
        unrelated_validation = inventory.ingest(DEMO / "demo_quality_examples.csv", through="2026-01-04")
        with self.assertRaises(PipelineError):
            inventory.ingest(DEMO / "demo_expected_schema_failure.csv", through="2026-01-04")
        unrelated_failure = next(run["run_id"] for run in inventory.report()["runs"] if run["status"] == "failed")
        result, inventory = self.run_demo()
        examples = result["demo_examples"]
        self.assertNotIn(unrelated_validation["run_id"], examples["runs"].values())
        self.assertNotIn(unrelated_failure, examples["runs"].values())
        report = inventory.report()
        self.assertEqual(report["metrics"]["current_events"], 50)
        self.assertEqual(report["metrics"]["history_versions"], 53)
        self.assertEqual(report["metrics"]["rejected_rows"], 6)
        self.assertEqual(sum(run["status"] == "failed" for run in report["runs"]), 2)
        for intent in self.demo_progress(inventory)["scenarios"].values():
            self.assertRegex(intent["source_file"], r"\.[a-f0-9]{12}\.csv$")
            self.assertEqual(len(intent["source_sha256"]), 64)

    def test_unexpected_pipeline_failure_still_propagates_without_completion_marker(self):
        original_ingest = Inventory.ingest

        def unexpected_failure(instance, input_path, *args, **kwargs):
            if Path(input_path).name.startswith("demo_expected_schema_failure."):
                raise PipelineError("synthetic unexpected storage failure")
            return original_ingest(instance, input_path, *args, **kwargs)

        inventory = self.interrupted_demo(unexpected_failure)
        with inventory.connect() as connection:
            self.assertIsNone(connection.execute("SELECT value FROM settings WHERE key='demo_examples_v1'").fetchone())
        self.assertNotIn("run_id", self.demo_progress(inventory)["scenarios"]["failure"])

    def test_completed_legacy_marker_does_not_require_private_progress(self):
        original, inventory = self.run_demo()
        with inventory.connect() as connection:
            connection.execute("DELETE FROM settings WHERE key='demo_examples_v1_progress'")
        repeated, inventory = self.run_demo()
        self.assertEqual(repeated["demo_examples"], original["demo_examples"])
        self.assert_teaching_counts(inventory)
        self.assertIsNone(self.demo_progress(inventory))


if __name__ == "__main__":
    unittest.main()
