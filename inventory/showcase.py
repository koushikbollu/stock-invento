"""Read recorded evidence for the dashboard without turning it into live claims."""

import json
import re
from pathlib import Path

from . import __version__


def build_showcase(root=None):
    root = Path(root) if root else Path(__file__).resolve().parents[1]
    evidence = root / "evidence"
    tests = dict(passed=False, count=None, scope="Recorded test evidence unavailable")
    log = evidence / "unit-tests.txt"
    if log.is_file():
        content = log.read_text(encoding="utf-8")
        match = re.search(r"Ran (\d+) tests? in", content)
        tests = dict(passed=bool(match and re.search(r"^OK\s*$", content, re.MULTILINE)),
                     count=int(match[1]) if match else None,
                     scope="Recorded automated execution; rerun tests to validate this laptop")
    benchmark = None
    path = evidence / "performance.json"
    if path.is_file():
        raw = json.loads(path.read_text(encoding="utf-8"))
        run, metrics = raw.get("first_run", {}), raw.get("metrics", {})
        benchmark = dict(physical_rows=raw.get("physical_rows"), seconds=raw.get("ingestion_and_reconciliation_seconds"),
                         accepted=run.get("accepted_count"), duplicates=run.get("duplicate_count"), rejected=run.get("rejected_count"),
                         daily_rows=metrics.get("daily_rows"), python=raw.get("python"), system=raw.get("system"), machine=raw.get("machine"),
                         seed=raw.get("seed"), measured_at=raw.get("measured_at"), scope=raw.get("scope"))
    coverage = None
    path = evidence / "generator-coverage.json"
    if path.is_file():
        coverage = json.loads(path.read_text(encoding="utf-8"))
    return dict(version=__version__, tests=tests, features=[
        dict(title="Import without a terminal", description="Preview movement CSVs, load reference catalogs, and publish with visible row outcomes.", status="implemented"),
        dict(title="See every correction's impact", description="Retained before/after balances show changed days, affected item/location series, and exact deltas.", status="implemented"),
        dict(title="Stress every item's full lifecycle", description="Generator v2 varies movement types, locations and dates, with separate coverage evidence.", status="implemented"),
        dict(title="Exact quantities and safe reruns", description="Integer thousandths, immutable revisions, and atomic publication preserve auditability.", status="implemented")],
        evidence=dict(tests=tests, benchmark=benchmark, generator=coverage), limitations=[
            "Recorded benchmark results describe one machine and dataset, not current live throughput or a measured speedup.",
            "AI generated the implementation and verification. Candidate personal review remains pending.",
            "Imports modify this laptop's local database. This application is not intended for public hosting."])
