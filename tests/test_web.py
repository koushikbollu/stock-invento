"""Local HTTP workflows: import publication, audit visibility and origin guards."""

import csv
import http.client
from http.cookies import SimpleCookie
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path

from inventory.pipeline import Inventory
from inventory.showcase import build_showcase
from inventory.web import MAX_CSV_BYTES, MAX_REQUEST_BYTES, _csv_input, create_server

ROOT = Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "data" / "sample"


class WebTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.db = Path(self.temp.name) / "inventory.db"
        self.inventory = Inventory(self.db)
        self.inventory.load_catalogs(SAMPLE / "items.csv", SAMPLE / "locations.csv")
        self.inventory.ingest(SAMPLE / "movements.csv", through="2026-01-04")
        self.server = create_server(self.db, port=0)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.origin = f"http://127.0.0.1:{self.port}"
        self.cookies = {}
        status, login_session = self.request("GET", "/api/login-session")
        self.assertEqual(status, 200)
        status, _ = self.request("POST", "/api/login", {"username": "admin", "password": "admin123"},
                                 {"Origin": self.origin, "X-Stockline-Token": login_session["csrf_token"]})
        self.assertEqual(status, 200)
        _, session = self.request("GET", "/api/session")
        self.token = session["csrf_token"]

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)
        self.temp.cleanup()

    def request(self, method, path, payload=None, headers=None, cookie=True):
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        body = json.dumps(payload) if payload is not None else None
        values = dict(headers or {})
        if cookie and self.cookies:
            values.setdefault("Cookie", "; ".join(f"{name}={value}" for name, value in self.cookies.items()))
        if payload is not None:
            values.setdefault("Content-Type", "application/json")
        connection.request(method, path, body=body, headers=values)
        response = connection.getresponse()
        content = response.read()
        status = response.status
        for name, value in response.getheaders():
            if name.lower() == "set-cookie":
                parsed = SimpleCookie(value)
                for key, morsel in parsed.items():
                    if not morsel.value or morsel["max-age"] == "0":
                        self.cookies.pop(key, None)
                    else:
                        self.cookies[key] = morsel.value
        connection.close()
        try:
            result = json.loads(content)
        except ValueError:
            result = content.decode("utf-8")
        return status, result

    def post(self, path, payload, **overrides):
        headers = {"Origin": self.origin, "X-Stockline-Token": self.token}
        headers.update(overrides)
        return self.request("POST", path, payload, headers)

    def test_csv_import_retains_before_after_and_replay_is_zero_change(self):
        payload = dict(filename="correction.csv", csv_text=(SAMPLE / "corrections.csv").read_text())
        status, result = self.post("/api/import", payload)
        self.assertEqual(status, 200)
        self.assertEqual(result["run"]["accepted_count"], 1)
        self.assertEqual(result["impact"]["total"], 4)
        self.assertTrue(all(row["closing_delta"] == "10.000" for row in result["impact"]["rows"]))
        status, changes = self.request("GET", "/api/changes?run_id=" + result["run"]["run_id"])
        self.assertEqual(status, 200)
        self.assertEqual(changes["rows"], result["impact"]["rows"])
        status, repeated = self.post("/api/import", payload)
        self.assertEqual(status, 200)
        self.assertEqual(repeated["run"]["duplicate_count"], 1)
        self.assertEqual(repeated["impact"]["total"], 0)
        self.assertTrue(repeated["impact"]["has_snapshot"])

    def test_valid_rows_publish_with_visible_quarantine(self):
        content = (SAMPLE / "review_correction.csv").read_text()
        content += "bad,1,2026-01-01,RECEIPT,UNKNOWN,WH-A,,3.000,false\n"
        status, result = self.post("/api/import", dict(filename="mixed.csv", csv_text=content))
        self.assertEqual(status, 200)
        self.assertEqual(result["run"]["status"], "succeeded_with_rejects")
        self.assertEqual(result["run"]["rejected_count"], 1)
        status, report = self.request("GET", "/api/report")
        self.assertEqual(status, 200)
        self.assertEqual(report["rejects"][0]["source_file"], "mixed.csv")
        self.assertEqual(report["rejects"][0]["row_number"], 3)

    def test_ordinary_workspaces_do_not_claim_seeded_demo_examples(self):
        status, report = self.request("GET", "/api/report")
        self.assertEqual(status, 200)
        self.assertIsNone(report["demo_examples"])

    def test_bad_schema_fails_without_replacing_previous_balances(self):
        before = self.inventory.report()["balances"]
        status, result = self.post("/api/import", dict(filename="bad.csv", csv_text="unexpected\nvalue\n"))
        self.assertEqual(status, 400)
        self.assertIn("schema", result["error"])
        self.assertEqual(self.inventory.report()["balances"], before)
        self.assertEqual(self.inventory.report()["runs"][0]["status"], "failed")

    def test_origin_token_and_host_guards_block_mutation(self):
        payload = dict(filename="test.csv", csv_text=(SAMPLE / "review_correction.csv").read_text())
        count = len(self.inventory.report()["runs"])
        self.assertEqual(self.post("/api/import", payload, Origin="https://unrelated.example")[0], 403)
        self.assertEqual(self.post("/api/import", payload, **{"X-Stockline-Token": "wrong"})[0], 403)
        self.assertEqual(self.request("POST", "/api/import", payload)[0], 403)
        self.assertEqual(self.request("GET", "/api/session", headers={"Host": "unrelated.example"})[0], 403)
        self.assertEqual(len(self.inventory.report()["runs"]), count)

    def test_catalog_import_is_atomic_and_supports_equal_filenames(self):
        payload = dict(items_filename="catalog.csv", items_csv="item_id,unit\nNEW,KG\n",
                       locations_filename="catalog.csv", locations_csv="location_id\nNEW-WH\n")
        status, result = self.post("/api/catalogs", payload)
        self.assertEqual(status, 200)
        self.assertEqual(result, {"items": 1, "locations": 1})
        status, catalogs = self.request("GET", "/api/catalogs")
        self.assertIn({"item_id": "NEW", "unit": "KG"}, catalogs["items"])
        payload["items_csv"] = "item_id,unit\nANOTHER,EA\nITEM-A,KG\n"
        payload["locations_csv"] = "location_id\nANOTHER-WH\n"
        self.assertEqual(self.post("/api/catalogs", payload)[0], 400)
        self.assertNotIn({"item_id": "ANOTHER", "unit": "EA"}, self.inventory.catalogs()["items"])
        self.assertNotIn({"location_id": "ANOTHER-WH"}, self.inventory.catalogs()["locations"])

    def test_rejects_bad_filename_payload_size_and_content_type(self):
        for filename in ("../evil.csv", "folder\\evil.csv", "not-csv.txt", "bad\nfile.csv"):
            with self.subTest(filename=filename):
                self.assertEqual(self.post("/api/import", dict(filename=filename, csv_text=""))[0], 400)
        self.assertEqual(self.post("/api/import", dict(filename="ok.csv", csv_text=""), **{"Content-Type": "text/plain"})[0], 415)
        self.assertEqual(self.post("/api/import", {}, **{"Content-Length": str(MAX_REQUEST_BYTES + 1)})[0], 413)
        with self.assertRaises(ValueError):
            _csv_input(dict(filename="ok.csv", csv_text="x" * (MAX_CSV_BYTES + 1)), "filename", "csv_text")

    def test_sample_routes_and_changes_pagination_validation(self):
        status, sample = self.request("GET", "/api/sample/review_correction.csv")
        self.assertEqual(status, 200)
        self.assertIn("receipt-a,3,", sample)
        self.assertEqual(self.request("GET", "/api/sample/unknown.csv")[0], 404)
        self.assertEqual(self.request("GET", "/api/changes?limit=0")[0], 400)
        self.assertEqual(self.request("GET", "/api/changes?offset=-1")[0], 400)
        self.assertEqual(self.request("DELETE", "/api/import")[0], 405)

    def test_default_demo_downloads_have_fifty_distinct_movements_and_matching_catalogs(self):
        status, source = self.request("GET", "/api/demo/movements.csv")
        self.assertEqual(status, 200)
        movements = list(csv.DictReader(io.StringIO(source)))
        self.assertEqual(len(movements), 50)
        self.assertEqual(len({row["event_id"] for row in movements}), 50)
        status, source = self.request("GET", "/api/demo/items.csv")
        self.assertEqual(status, 200)
        items = {row["item_id"] for row in csv.DictReader(io.StringIO(source))}
        status, source = self.request("GET", "/api/demo/locations.csv")
        self.assertEqual(status, 200)
        locations = {row["location_id"] for row in csv.DictReader(io.StringIO(source))}
        self.assertEqual((len(items), len(locations)), (5, 3))
        self.assertTrue(all(row["item_id"] in items and row["location_id"] in locations for row in movements))
        self.assertEqual(self.request("GET", "/api/demo/unknown.csv")[0], 404)


class ShowcaseTest(unittest.TestCase):
    def test_missing_evidence_never_claims_verification(self):
        with tempfile.TemporaryDirectory() as temporary:
            result = build_showcase(temporary)
        self.assertFalse(result["evidence"]["tests"]["passed"])
        self.assertIsNone(result["evidence"]["benchmark"])

    def test_recorded_evidence_is_parsed_without_hardcoded_numbers(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            evidence = root / "evidence"
            evidence.mkdir()
            (evidence / "unit-tests.txt").write_text("Ran 17 tests in 0.2s\n\nOK\n")
            (evidence / "performance.json").write_text(json.dumps(dict(physical_rows=1234,
                ingestion_and_reconciliation_seconds=9.876, first_run={"accepted_count": 1200}, metrics={"daily_rows": 90})))
            result = build_showcase(root)
        self.assertTrue(result["evidence"]["tests"]["passed"])
        self.assertEqual(result["evidence"]["tests"]["count"], 17)
        self.assertEqual(result["evidence"]["benchmark"]["seconds"], 9.876)
        self.assertEqual(result["evidence"]["benchmark"]["accepted"], 1200)
