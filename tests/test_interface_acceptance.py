"""Acceptance at real CLI/HTTP boundaries, extending focused pipeline unit tests.

Scenario IDs are stable names for the verification report. Every database and
server is temporary. Browser interaction and visual rendering are verified
separately; these tests execute no browser and never use the running demo port.
"""

from concurrent.futures import ThreadPoolExecutor
import csv
import http.client
from http.cookies import SimpleCookie
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest import mock

from inventory.model import FIELDS
from inventory.pipeline import Inventory
from inventory.web import MAX_CSV_BYTES, create_server


ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"
EXPECTED = ROOT / "data" / "expected"
HEADER = ",".join(FIELDS) + "\n"


def csv_text(rows):
    stream = io.StringIO(newline="")
    writer = csv.writer(stream)
    writer.writerow(FIELDS)
    writer.writerows(rows)
    return stream.getvalue()


def business_rows(report):
    """Exclude publication lineage, retaining every actual balance value."""
    return [{key: value for key, value in row.items() if key != "last_run_id"}
            for row in report["balances"]]


def event(event_id="acceptance-receipt", quantity="10", item="ITEM-A", kind="RECEIPT", day="2026-01-01"):
    return [event_id, "1", day, kind, item, "WH-A", "", quantity, "false"]


class CliAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="inventory-cli-acceptance-")
        self.addCleanup(self.temporary.cleanup)
        self.directory = Path(self.temporary.name) / "path with spaces"
        self.directory.mkdir()
        self.db = self.directory / "inventory data.db"
        result = self.cli("init", "--db", self.db, "--items", SAMPLE / "items.csv", "--locations", SAMPLE / "locations.csv")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout), {"items": 2, "locations": 2})

    def cli(self, *arguments):
        return subprocess.run([sys.executable, "-m", "inventory", *map(str, arguments)],
                              cwd=ROOT, capture_output=True, text=True, timeout=30)

    def report(self):
        result = self.cli("report", "--db", self.db)
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def run_csv(self, content, filename="acceptance.csv"):
        source = self.directory / filename
        source.write_text(content, encoding="utf-8", newline="")
        return self.cli("run", "--db", self.db, "--input", source, "--through", "2026-01-04")

    def load_sample(self):
        result = self.cli("run", "--db", self.db, "--input", SAMPLE / "movements.csv", "--through", "2026-01-04")
        self.assertEqual(result.returncode, 0, result.stderr)
        return json.loads(result.stdout)

    def test_cli_a01_documented_workflow_matches_oracle_and_exports(self):
        """CLI-A01: executable commands, exact outputs, paths with spaces, export."""
        first = self.load_sample()
        self.assertEqual((first["accepted_count"], first["input_count"]), (7, 7))
        correction = self.cli("run", "--db", self.db, "--input", SAMPLE / "corrections.csv", "--through", "2026-01-04")
        self.assertEqual(correction.returncode, 0, correction.stderr)
        self.assertEqual(json.loads(correction.stdout)["accepted_count"], 1)
        report = self.report()
        self.assertEqual(report["metrics"]["current_events"], 7)
        self.assertEqual(report["metrics"]["history_versions"], 8)
        self.assertEqual(report["metrics"]["daily_rows"], 11)
        self.assertTrue(all(check["passed"] for check in report["reconciliation"]))
        with (EXPECTED / "corrected_balances.csv").open(newline="", encoding="utf-8") as stream:
            oracle = list(csv.DictReader(stream))
        grain = lambda row: (row["balance_date"], row["item_id"], row["location_id"])
        self.assertEqual(sorted([{key: row[key] for key in oracle[0]} for row in report["balances"]], key=grain),
                         sorted(oracle, key=grain))
        output = self.directory / "review export"
        exported = self.cli("export", "--db", self.db, "--out", output)
        self.assertEqual(exported.returncode, 0, exported.stderr)
        files = json.loads(exported.stdout)["files"]
        self.assertEqual(set(files), {"daily_balances.csv", "runs.csv", "reconciliation.csv", "raw_records.csv",
                                      "movement_versions.csv", "postings.csv", "balance_changes.csv", "report.json"})
        self.assertTrue(all((output / name).is_file() for name in files))
        saved = json.loads((output / "report.json").read_text(encoding="utf-8"))
        self.assertEqual(business_rows(saved), business_rows(report))
        with (output / "daily_balances.csv").open(newline="", encoding="utf-8") as stream:
            published = list(csv.DictReader(stream))
        self.assertEqual(sorted([{key: row[key] for key in oracle[0]} for row in published], key=grain),
                         sorted(oracle, key=grain))

    def test_cli_a02_exit_two_publishes_valid_rows_and_safe_replay(self):
        """CLI-A02: exit2 is partial acceptance; replay preserves business balances."""
        rows = [event(), event(), event("unknown-item", item="UNKNOWN"),
                event("acceptance-issue", quantity="12", kind="ISSUE", day="2026-01-02")]
        result = self.run_csv(csv_text(rows), "mixed rows.csv")
        self.assertEqual(result.returncode, 2, result.stderr)
        summary = json.loads(result.stdout)
        self.assertEqual(summary["status"], "succeeded_with_rejects")
        self.assertEqual((summary["input_count"], summary["accepted_count"], summary["duplicate_count"], summary["rejected_count"]),
                         (4, 2, 1, 1))
        before = self.report()
        self.assertEqual(before["metrics"]["current_events"], 2)
        self.assertEqual(before["metrics"]["negative_balance_days"], 3)
        self.assertEqual(before["rejects"][0]["source_file"], "mixed rows.csv")
        self.assertEqual(before["rejects"][0]["row_number"], 4)
        self.assertIn("UNKNOWN", before["rejects"][0]["raw_json"])
        replay = self.run_csv(csv_text(rows), "mixed rows.csv")
        self.assertEqual(replay.returncode, 2, replay.stderr)
        replayed = json.loads(replay.stdout)
        self.assertEqual((replayed["accepted_count"], replayed["duplicate_count"], replayed["rejected_count"]), (0, 3, 1))
        self.assertEqual(replayed["changed_balance_rows"], 0)
        after = self.report()
        self.assertEqual(business_rows(after), business_rows(before))
        self.assertTrue(all(check["passed"] for check in after["reconciliation"]))

    def test_cli_a03_malformed_csv_rolls_back_then_retry_succeeds(self):
        """CLI-A03: fatal parsing after a valid row rolls back, audits, exits1; retry0."""
        self.load_sample()
        before = self.report()
        good = csv_text([event("pending-cli", quantity="7")])
        broken = good + '"unterminated,1,2026-01-01,RECEIPT,ITEM-A,WH-A,,2,false\n'
        failed = self.run_csv(broken, "interrupted batch.csv")
        self.assertEqual(failed.returncode, 1)
        self.assertEqual(failed.stdout, "")
        self.assertNotIn("Traceback", failed.stderr)
        self.assertIn("failed", json.loads(failed.stderr.splitlines()[-1])["error"])
        after = self.report()
        self.assertEqual(business_rows(after), business_rows(before))
        self.assertEqual(after["metrics"]["history_versions"], before["metrics"]["history_versions"])
        run = next(row for row in after["runs"] if row["source_file"] == "interrupted batch.csv")
        self.assertEqual((run["status"], run["accepted_count"], run["rolled_back_count"], run["impact_recorded"]),
                         ("failed", 0, 1, 0))
        retry = self.run_csv(good, "interrupted batch.csv")
        self.assertEqual(retry.returncode, 0, retry.stderr)
        self.assertEqual(json.loads(retry.stdout)["accepted_count"], 1)
        final = self.report()
        self.assertEqual(final["metrics"]["current_events"], 8)
        self.assertTrue(all(check["passed"] for check in final["reconciliation"]))

    def test_cli_a04_schema_and_invalid_horizon_are_observable_without_state_loss(self):
        """CLI-A04: file/header and date configuration failures do not publish."""
        self.load_sample()
        before = self.report()
        result = self.run_csv("unexpected_header\nvalue\n", "schema changed.csv")
        self.assertEqual(result.returncode, 1)
        self.assertIn("schema", result.stderr)
        source = self.directory / "valid horizon input.csv"
        source.write_text(csv_text([event("never-read")]), encoding="utf-8")
        result = self.cli("run", "--db", self.db, "--input", source, "--through", "2026-99-99")
        self.assertEqual(result.returncode, 1)
        self.assertNotIn("Traceback", result.stderr)
        after = self.report()
        self.assertEqual(business_rows(after), business_rows(before))
        failures = [row for row in after["runs"] if row["status"] == "failed"]
        self.assertEqual(len(failures), 2)
        self.assertTrue(all(row["input_count"] == 0 and row["error"] for row in failures))

    def test_cli_a05_missing_database_fails_without_creating_it(self):
        """CLI-A05: a configuration error exits1 and creates no database."""
        missing = self.directory / "not-created" / "missing.db"
        result = self.cli("run", "--db", missing, "--input", SAMPLE / "movements.csv")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stdout, "")
        self.assertIn("database does not exist", json.loads(result.stderr)["error"])
        self.assertFalse(missing.exists())
        self.assertFalse(missing.parent.exists())


class HttpAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="inventory-http-acceptance-")
        self.addCleanup(self.temporary.cleanup)
        self.db = Path(self.temporary.name) / "inventory.db"
        self.inventory = Inventory(self.db)
        self.inventory.load_catalogs(SAMPLE / "items.csv", SAMPLE / "locations.csv")
        self.inventory.ingest(SAMPLE / "movements.csv", through="2026-01-04")
        self.server = create_server(self.db, port=0)
        self.server.RequestHandlerClass.log_message = lambda *_args: None
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.port = self.server.server_port
        self.origin = f"http://127.0.0.1:{self.port}"
        self.cookies = {}
        self.token = self.request("GET", "/api/login-session")[1]["csrf_token"]
        self.assertEqual(self.request("POST", "/api/login", {"username": "admin", "password": "admin123"})[0], 200)
        self.token = self.request("GET", "/api/session")[1]["csrf_token"]

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def request(self, method, path, payload=None, raw=None, cookie=True):
        headers = {}
        if cookie and self.cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in self.cookies.items())
        body = raw
        if method == "POST":
            headers.update({"Origin": self.origin, "X-Stockline-Token": self.token, "Content-Type": "application/json"})
            if payload is not None:
                body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=30)
        try:
            connection.request(method, path, body=body, headers=headers)
            response = connection.getresponse()
            content = response.read()
            for name, value in response.getheaders():
                if name.lower() == "set-cookie":
                    parsed = SimpleCookie(value)
                    for key, morsel in parsed.items():
                        if not morsel.value or morsel["max-age"] == "0":
                            self.cookies.pop(key, None)
                        else:
                            self.cookies[key] = morsel.value
            result = json.loads(content) if content else None
            return response.status, result, dict(response.getheaders())
        finally:
            connection.close()

    def post_csv(self, content, filename="http-acceptance.csv"):
        return self.request("POST", "/api/import", {"filename": filename, "csv_text": content, "through": "2026-01-04"})

    def test_http_b01_malformed_json_utf8_and_wrong_shapes_are_nonmutating(self):
        """HTTP-B01: invalid transport bodies return400, with no ingestion/audit attempt."""
        before = self.inventory.report()
        for body in (b'{"filename":', b"\xff", b"[]", b"null", b'"string"'):
            with self.subTest(body=repr(body)):
                status, result, _ = self.request("POST", "/api/import", raw=body)
                self.assertEqual(status, 400)
                self.assertTrue(result["error"])
        for payload in ({"filename": "missing-text.csv"}, {"filename": "number.csv", "csv_text": 7}):
            with self.subTest(payload=payload):
                self.assertEqual(self.request("POST", "/api/import", payload)[0], 400)
        after = self.inventory.report()
        self.assertEqual(after["runs"], before["runs"])
        self.assertEqual(business_rows(after), business_rows(before))
        self.assertEqual(self.request("GET", "/api/report")[0], 200)

    def test_http_b02_malformed_csv_after_valid_row_is_atomic_and_retryable(self):
        """HTTP-B02: authoritative CSV parse failure returns400, audits rollback, unlocks retry."""
        before = self.inventory.report()
        valid = csv_text([event("pending-http", quantity="9")])
        status, result, _ = self.post_csv(valid + '"unterminated\n', "broken.csv")
        self.assertEqual(status, 400)
        self.assertIn("failed", result["error"])
        after = self.inventory.report()
        self.assertEqual(business_rows(after), business_rows(before))
        self.assertEqual(after["metrics"]["history_versions"], before["metrics"]["history_versions"])
        run = next(row for row in after["runs"] if row["source_file"] == "broken.csv")
        self.assertEqual((run["status"], run["rolled_back_count"], run["impact_recorded"]), ("failed", 1, 0))
        status, retry, _ = self.post_csv(valid, "broken.csv")
        self.assertEqual(status, 200)
        self.assertEqual(retry["run"]["accepted_count"], 1)
        self.assertTrue(all(check["passed"] for check in self.inventory.report()["reconciliation"]))

    def test_http_b03_ten_mib_utf8_boundary_is_enforced_over_http(self):
        """HTTP-B03: exactly10MiB accepted; a multi-byte character beyond it rejected before ingestion."""
        prefix = "\ufeff" + HEADER
        content = prefix + "\n" * (MAX_CSV_BYTES - len(prefix.encode("utf-8")))
        self.assertEqual(len(content.encode("utf-8")), MAX_CSV_BYTES)
        before = business_rows(self.inventory.report())
        status, accepted, _ = self.post_csv(content, "boundary.csv")
        self.assertEqual(status, 200)
        self.assertEqual(accepted["run"]["input_count"], 0)
        self.assertEqual(accepted["run"]["status"], "succeeded")
        count = len(self.inventory.report()["runs"])
        status, rejected, _ = self.post_csv(content + "é", "over-boundary.csv")
        self.assertEqual(status, 400)
        self.assertIn("10 MiB", rejected["error"])
        report = self.inventory.report()
        self.assertEqual(len(report["runs"]), count)
        self.assertEqual(business_rows(report), before)

    def test_http_b04_reader_sees_old_snapshot_while_import_is_atomic_and_busy(self):
        """HTTP-B04: WAL reader stays consistent during a real held writer; second import409."""
        before = self.inventory.report()
        entered, release = threading.Event(), threading.Event()
        rebuild = Inventory._rebuild

        def pause_inside_transaction(engine, *args, **kwargs):
            entered.set()
            if not release.wait(timeout=15):
                raise RuntimeError("acceptance synchronization timed out")
            return rebuild(engine, *args, **kwargs)

        content = (SAMPLE / "corrections.csv").read_text(encoding="utf-8")
        with mock.patch.object(Inventory, "_rebuild", pause_inside_transaction), ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(self.post_csv, content, "held-correction.csv")
            try:
                self.assertTrue(entered.wait(timeout=10), "writer did not enter its transaction")
                status, snapshot, _ = self.request("GET", "/api/report")
                self.assertEqual(status, 200)
                self.assertEqual(business_rows(snapshot), business_rows(before))
                self.assertTrue(all(check["passed"] for check in snapshot["reconciliation"]))
                status, busy, _ = self.post_csv(content, "competing.csv")
                self.assertEqual(status, 409)
                self.assertIn("Another import", busy["error"])
            finally:
                release.set()
            status, committed, _ = future.result(timeout=15)
        self.assertEqual(status, 200)
        self.assertEqual(committed["run"]["accepted_count"], 1)
        report = self.inventory.report()
        self.assertFalse(any(run["source_file"] == "competing.csv" for run in report["runs"]))
        self.assertEqual(next(row["closing"] for row in report["balances"] if
                              (row["item_id"], row["location_id"], row["balance_date"]) == ("ITEM-A", "WH-A", "2026-01-04")), "75.000")
        self.assertTrue(all(check["passed"] for check in report["reconciliation"]))

    def test_http_b05_publication_failure_preserves_state_and_releases_import_lock(self):
        """HTTP-B05: internal failure before commit returns a failed run; next real request succeeds."""
        before = self.inventory.report()
        content = csv_text([event("retry-after-publication-failure", quantity="5")])
        with mock.patch("inventory.pipeline.record_changes", side_effect=RuntimeError("acceptance injected publication failure")):
            status, result, _ = self.post_csv(content, "publication.csv")
        self.assertEqual(status, 400)
        self.assertIn("publication failure", result["error"])
        after = self.inventory.report()
        self.assertEqual(business_rows(after), business_rows(before))
        failed = next(row for row in after["runs"] if row["source_file"] == "publication.csv")
        self.assertEqual((failed["status"], failed["rolled_back_count"], failed["impact_recorded"]), ("failed", 1, 0))
        status, success, _ = self.post_csv(content, "publication.csv")
        self.assertEqual(status, 200)
        self.assertEqual(success["run"]["accepted_count"], 1)
        self.assertTrue(all(check["passed"] for check in self.inventory.report()["reconciliation"]))

    def test_http_b06_html_like_source_values_stay_data_with_browser_defenses(self):
        """HTTP-B06: hostile-looking values remain JSON/audit data; browser rendering is separately audited."""
        payload = '<img src=x onerror=alert(1)>'
        status, result, headers = self.post_csv(csv_text([event(payload)]), "quotes & examples.csv")
        self.assertEqual(status, 200)
        self.assertEqual(result["run"]["rejected_count"], 1)
        self.assertTrue(headers["Content-Type"].startswith("application/json"))
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertNotIn("unsafe-inline", headers["Content-Security-Policy"])
        status, report, headers = self.request("GET", "/api/report")
        self.assertEqual(status, 200)
        rejected = next(row for row in report["rejects"] if row["source_file"] == "quotes & examples.csv")
        self.assertEqual(json.loads(rejected["raw_json"])["event_id"], payload)
        self.assertTrue(all(check["passed"] for check in report["reconciliation"]))
