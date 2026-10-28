"""Reproduce tests, hand-computed sample checks, and a measured larger run.

Run: python3 scripts/verify.py --rows 100000 --out evidence
Only synthetic inputs and machine type/version (no hostname) are recorded.
"""

import argparse
import csv
import json
import platform
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from inventory.generate import generate
from inventory.pipeline import Inventory


def write_json(path, value):
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def oracle(actual, path):
    with path.open(newline="", encoding="utf-8") as stream:
        expected = list(csv.DictReader(stream))
    fields = list(expected[0])
    normalized = [{k: str(row[k]) for k in fields} for row in actual]
    key = lambda row: (row["balance_date"], row["item_id"], row["location_id"])
    expected.sort(key=key)
    normalized.sort(key=key)
    assert normalized == expected, f"hand-computed oracle mismatch: {path.name}"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rows", type=int, default=100000)
    parser.add_argument("--out", default="evidence")
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # Do not retain a previous overall PASS while a new verification is pending
    # or if this run later fails. Individual measurements remain historical.
    (output / "verification.json").unlink(missing_ok=True)
    tests = subprocess.run([sys.executable, str(ROOT / "scripts" / "run_tests.py"), "--out", str(output)],
                           cwd=ROOT, capture_output=True, text=True)
    if tests.returncode:
        print(tests.stderr, file=sys.stderr)
        return tests.returncode
    test_results = json.loads((output / "python-tests.json").read_text(encoding="utf-8"))
    with tempfile.TemporaryDirectory(prefix="inventory-verification-") as work:
        temp = Path(work)
        sample = ROOT / "data" / "sample"
        small = Inventory(temp / "small.db")
        small.load_catalogs(sample / "items.csv", sample / "locations.csv")
        initial = small.ingest(sample / "movements.csv", through="2026-01-04")
        oracle(small.report()["balances"], ROOT / "data" / "expected" / "initial_balances.csv")
        small.export(output / "initial")
        corrected = small.ingest(sample / "corrections.csv", through="2026-01-04")
        oracle(small.report()["balances"], ROOT / "data" / "expected" / "corrected_balances.csv")
        impact = small.changes(corrected["run_id"])
        assert impact["has_snapshot"] and impact["total"] == 4
        assert all(row["closing_delta"] == "10.000" for row in impact["rows"])
        small.export(output / "corrected")
        write_json(output / "correction-impact.json", impact)

        before = time.perf_counter()
        paths = generate(temp / "generated", rows=args.rows, seed=42)
        coverage = json.loads(Path(paths["coverage"]).read_text(encoding="utf-8"))
        write_json(output / "generator-coverage.json", coverage)
        generation_seconds = time.perf_counter() - before
        large = Inventory(temp / "large.db")
        large.load_catalogs(paths["items"], paths["locations"])
        before = time.perf_counter()
        run = large.ingest(paths["movements"])
        ingestion_seconds = time.perf_counter() - before
        report = large.report()
        assert all(c["passed"] for c in report["reconciliation"])
        # A rerun must produce identical business values. Operational lineage/run IDs differ.
        before_values = [{k: v for k, v in b.items() if k != "last_run_id"} for b in report["balances"]]
        before = time.perf_counter()
        rerun = large.ingest(paths["movements"])
        rerun_seconds = time.perf_counter() - before
        after_values = [{k: v for k, v in b.items() if k != "last_run_id"} for b in large.report()["balances"]]
        assert before_values == after_values
        assert rerun["accepted_count"] == 0
        assert large.changes(rerun["run_id"])["total"] == 0
        performance = dict(
            measured_at=datetime.now(timezone.utc).isoformat(), python=platform.python_version(),
            system=platform.system(), machine=platform.machine(), seed=42, physical_rows=args.rows,
            generation_seconds=round(generation_seconds, 6),
            ingestion_and_reconciliation_seconds=round(ingestion_seconds, 6),
            rows_per_second=round(args.rows / ingestion_seconds, 2),
            rerun_seconds=round(rerun_seconds, 6),
            first_run=run, rerun=rerun, metrics=report["metrics"],
            reconciliation=report["reconciliation"],
            business_output_identical_on_rerun=True,
            scope="Single local run with generator v2; includes CSV validation, audit/history writes, full target rebuild, reconciliation, retained balance comparisons and commit. Not a capacity guarantee or a measured speedup.",
            optimization="For larger histories, rebuild only affected item/location/date partitions while preserving atomic publication; measure first.")
        write_json(output / "performance.json", performance)
    write_json(output / "verification.json", dict(
        tests_passed=True, test_count=test_results["tests_run"],
        subtest_checks=test_results["subtest_checks"], initial_oracle_passed=True, corrected_oracle_passed=True,
        large_run_reconciliation_passed=True, rerun_business_outputs_identical=True,
        correction_impact_retained=True, generator_version=coverage["generator_version"],
        commands=["python3 -m unittest discover -s tests -v", f"python3 scripts/verify.py --rows {args.rows} --out {args.out}"],
        evidence=["unit-tests.txt", "python-tests.json", "junit.xml", "initial/report.json", "corrected/report.json", "performance.json", "correction-impact.json", "generator-coverage.json"]))
    print(json.dumps({"evidence": str(output), "physical_rows": args.rows,
                      "seconds": performance["ingestion_and_reconciliation_seconds"],
                      "accepted": run["accepted_count"], "duplicates": run["duplicate_count"],
                      "rejects": run["rejected_count"], "verified": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
