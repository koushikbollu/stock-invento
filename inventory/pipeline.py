"""Transactional CSV ingestion, immutable revisions, materialization and checks."""

import csv
import json
import logging
import os
import sqlite3
import tempfile
import time
import uuid
from collections import defaultdict
from contextlib import nullcontext
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .model import FIELDS, SQLITE_LIMIT, format_quantity, identifier, iso_date, parse_event
from .impact import capture_balances, changes_report, record_changes

LOG = logging.getLogger("inventory")
MEASURES = ("receipts", "issues", "transfers_in", "transfers_out", "adjustments")
SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
 item_id TEXT PRIMARY KEY, unit TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS locations (location_id TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs (
 run_id TEXT PRIMARY KEY, source_file TEXT NOT NULL, started_at TEXT NOT NULL,
 finished_at TEXT, status TEXT NOT NULL, input_count INTEGER NOT NULL DEFAULT 0,
 accepted_count INTEGER NOT NULL DEFAULT 0, duplicate_count INTEGER NOT NULL DEFAULT 0,
 rejected_count INTEGER NOT NULL DEFAULT 0, rolled_back_count INTEGER NOT NULL DEFAULT 0,
 output_count INTEGER NOT NULL DEFAULT 0, duration_ms INTEGER NOT NULL DEFAULT 0,
 error TEXT, published_through TEXT
);
CREATE TABLE IF NOT EXISTS raw_records (
 run_id TEXT NOT NULL REFERENCES runs(run_id), row_number INTEGER NOT NULL,
 source_file TEXT NOT NULL, raw_json TEXT NOT NULL, outcome TEXT NOT NULL,
 reason TEXT, PRIMARY KEY(run_id, row_number)
);
CREATE TABLE IF NOT EXISTS movement_versions (
 event_id TEXT NOT NULL, revision INTEGER NOT NULL CHECK(revision > 0),
 effective_date TEXT NOT NULL, movement_type TEXT NOT NULL,
 item_id TEXT NOT NULL REFERENCES items(item_id),
 location_id TEXT NOT NULL REFERENCES locations(location_id),
 to_location_id TEXT REFERENCES locations(location_id), quantity_milli INTEGER NOT NULL,
 is_void INTEGER NOT NULL CHECK(is_void IN (0,1)), payload_json TEXT NOT NULL,
 run_id TEXT NOT NULL REFERENCES runs(run_id), source_file TEXT NOT NULL,
 row_number INTEGER NOT NULL, PRIMARY KEY(event_id,revision)
);
CREATE VIEW IF NOT EXISTS current_movements AS
 SELECT v.* FROM movement_versions v WHERE v.revision =
 (SELECT MAX(newer.revision) FROM movement_versions newer WHERE newer.event_id=v.event_id);
CREATE TABLE IF NOT EXISTS postings (
 posting_id TEXT PRIMARY KEY, event_id TEXT NOT NULL, revision INTEGER NOT NULL,
 effective_date TEXT NOT NULL, item_id TEXT NOT NULL REFERENCES items(item_id),
 location_id TEXT NOT NULL REFERENCES locations(location_id),
 receipts_milli INTEGER NOT NULL, issues_milli INTEGER NOT NULL,
 transfers_in_milli INTEGER NOT NULL, transfers_out_milli INTEGER NOT NULL,
 adjustments_milli INTEGER NOT NULL,
 FOREIGN KEY(event_id,revision) REFERENCES movement_versions(event_id,revision)
);
CREATE INDEX IF NOT EXISTS postings_grain ON postings(item_id,location_id,effective_date);
CREATE TABLE IF NOT EXISTS daily_balances (
 balance_date TEXT NOT NULL, item_id TEXT NOT NULL REFERENCES items(item_id),
 location_id TEXT NOT NULL REFERENCES locations(location_id), opening_milli INTEGER NOT NULL,
 receipts_milli INTEGER NOT NULL, issues_milli INTEGER NOT NULL,
 transfers_in_milli INTEGER NOT NULL, transfers_out_milli INTEGER NOT NULL,
 adjustments_milli INTEGER NOT NULL, closing_milli INTEGER NOT NULL,
 last_run_id TEXT NOT NULL REFERENCES runs(run_id),
 PRIMARY KEY(balance_date,item_id,location_id)
);
CREATE INDEX IF NOT EXISTS balances_account_date ON daily_balances(item_id,location_id,balance_date);
CREATE TABLE IF NOT EXISTS balance_changes (
 run_id TEXT NOT NULL REFERENCES runs(run_id), balance_date TEXT NOT NULL,
 item_id TEXT NOT NULL REFERENCES items(item_id), location_id TEXT NOT NULL REFERENCES locations(location_id),
 before_json TEXT, after_json TEXT, closing_delta_milli TEXT NOT NULL,
 PRIMARY KEY(run_id,balance_date,item_id,location_id)
);
"""


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


class PipelineError(RuntimeError):
    """A failed run has been rolled back and its failure recorded."""


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


class Inventory:
    def __init__(self, db_path):
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.executescript(SCHEMA)
            if "impact_recorded" not in {c[1] for c in conn.execute("PRAGMA table_info(runs)")}:
                conn.execute("ALTER TABLE runs ADD COLUMN impact_recorded INTEGER NOT NULL DEFAULT 0")

    def connect(self):
        conn = sqlite3.connect(self.db_path, timeout=30, factory=ClosingConnection)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def load_catalogs(self, items_csv, locations_csv):
        """Add reference keys atomically; an existing item's unit cannot be changed."""
        def read(path, fields):
            with Path(path).open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.DictReader(stream, strict=True)
                if reader.fieldnames is None or len(reader.fieldnames) != len(fields) or set(reader.fieldnames) != set(fields):
                    raise ValueError(f"{Path(path).name}: expected columns {','.join(fields)}")
                result = []
                seen = set()
                for row in reader:
                    if set(row) != set(fields) or any(v is None for v in row.values()):
                        raise ValueError(f"{Path(path).name}: malformed catalog row")
                    values = tuple(identifier(row[k].strip(), k) for k in fields)
                    if values[0] in seen:
                        raise ValueError(f"{Path(path).name}: duplicate reference key")
                    seen.add(values[0])
                    result.append(values)
                return result
        items = read(items_csv, ("item_id", "unit"))
        locations = read(locations_csv, ("location_id",))
        with self.connect() as conn:
            conn.execute("BEGIN IMMEDIATE")
            for item_id, unit in items:
                old = conn.execute("SELECT unit FROM items WHERE item_id=?", (item_id,)).fetchone()
                if old and old[0] != unit:
                    raise ValueError("an existing item's unit cannot change")
                conn.execute("INSERT OR IGNORE INTO items VALUES (?,?)", (item_id, unit))
            conn.executemany("INSERT OR IGNORE INTO locations VALUES (?)", locations)
        return {"items": len(items), "locations": len(locations)}

    def ingest(self, input_path, through=None, fail_before_publish=False):
        """Valid rows commit together with derived targets; bad rows are quarantined.

        fail_before_publish is a test failpoint to prove rollback/retry, not a CLI option.
        Each invocation gets a new operational run ID; business keys remain deterministic.
        """
        started = time.perf_counter()
        run_id = str(uuid.uuid4())
        source_file = Path(input_path).name
        summary = dict(run_id=run_id, source_file=source_file, started_at=utc_now(),
                       status="running", input_count=0, accepted_count=0,
                       duplicate_count=0, rejected_count=0, rolled_back_count=0,
                       output_count=0, duration_ms=0, error=None, impact_recorded=0)
        attempts = []
        with self.connect() as audit:
            audit.execute("INSERT INTO runs(run_id,source_file,started_at,status) VALUES (?,?,?,?)",
                          (run_id, source_file, summary["started_at"], "running"))
        conn = self.connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            before_balances = capture_balances(conn)
            if through is not None:
                iso_date(through)
            items = {r[0] for r in conn.execute("SELECT item_id FROM items")}
            locations = {r[0] for r in conn.execute("SELECT location_id FROM locations")}
            with Path(input_path).open(newline="", encoding="utf-8-sig") as stream:
                reader = csv.DictReader(stream, strict=True)
                if reader.fieldnames is None or len(reader.fieldnames) != len(FIELDS) or set(reader.fieldnames) != set(FIELDS):
                    raise ValueError("unexpected schema: expected exactly " + ",".join(FIELDS))
                for row in reader:
                    summary["input_count"] += 1
                    # CSV physical ending line, including a header and any multiline fields.
                    line = reader.line_num
                    raw_json = json.dumps(row, ensure_ascii=True, default=str)
                    outcome, reason = "accepted", None
                    try:
                        event = parse_event(row, items, locations)
                        payload = json.dumps(event, sort_keys=True, separators=(",", ":"))
                        previous = conn.execute(
                            "SELECT payload_json FROM movement_versions WHERE event_id=? AND revision=?",
                            (event["event_id"], event["revision"])).fetchone()
                        if previous:
                            if previous[0] != payload:
                                raise ValueError("conflicting payload for existing event_id/revision; submit a higher revision")
                            outcome = "duplicate"
                        else:
                            conn.execute("""INSERT INTO movement_versions VALUES
                                (?,?,?,?,?,?,?,?,?,?,?,?,?)""", (
                                event["event_id"], event["revision"], event["effective_date"],
                                event["movement_type"], event["item_id"], event["location_id"],
                                event["to_location_id"] or None, event["quantity_milli"], event["is_void"],
                                payload, run_id, source_file, line))
                    except (ValueError, TypeError) as error:
                        outcome, reason = "rejected", str(error)
                    summary[outcome + "_count"] += 1
                    record = (run_id, line, source_file, raw_json, outcome, reason)
                    attempts.append(record)
                    conn.execute("INSERT INTO raw_records VALUES (?,?,?,?,?,?)", record)
            horizon = self._rebuild(conn, run_id, through)
            if fail_before_publish:
                raise RuntimeError("injected failure before target publication")
            summary["output_count"] = conn.execute("SELECT COUNT(*) FROM daily_balances").fetchone()[0]
            checks = self._reconcile(conn)
            if not all(c["passed"] for c in checks):
                raise RuntimeError("reconciliation failed; target publication rolled back")
            summary["changed_balance_rows"] = record_changes(conn, run_id, before_balances)
            summary["impact_recorded"] = 1
            summary["status"] = "succeeded_with_rejects" if summary["rejected_count"] else "succeeded"
            summary["published_through"] = horizon
            summary["finished_at"] = utc_now()
            summary["duration_ms"] = round((time.perf_counter() - started) * 1000)
            self._finish(conn, summary)
            conn.commit()
        except Exception as error:
            conn.rollback()
            summary["impact_recorded"] = 0
            summary["changed_balance_rows"] = 0
            summary["rolled_back_count"] = summary["accepted_count"]
            summary["accepted_count"] = 0
            summary["status"] = "failed"
            # Do not copy local paths or arbitrary data into a public error report.
            summary["error"] = (str(error) if not isinstance(error, OSError)
                                else f"{type(error).__name__}: could not read or write local data")
            summary["finished_at"] = utc_now()
            summary["duration_ms"] = round((time.perf_counter() - started) * 1000)
            with self.connect() as audit:
                audit.execute("BEGIN IMMEDIATE")
                for record in attempts:
                    updated = record[:4] + (("rolled_back", "run failed before publication") if record[4] == "accepted" else record[4:])
                    audit.execute("INSERT INTO raw_records VALUES (?,?,?,?,?,?)", updated)
                self._finish(audit, summary)
            LOG.error(json.dumps(summary, sort_keys=True))
            raise PipelineError(f"run {run_id} failed: {summary['error']}") from error
        finally:
            conn.close()
        LOG.info(json.dumps(summary, sort_keys=True))
        return summary

    @staticmethod
    def _finish(conn, summary):
        keys = ("finished_at", "status", "input_count", "accepted_count", "duplicate_count",
                "rejected_count", "rolled_back_count", "output_count", "duration_ms", "error", "published_through", "impact_recorded")
        conn.execute("UPDATE runs SET " + ",".join(k + "=?" for k in keys) + " WHERE run_id=?",
                     tuple(summary.get(k) for k in keys) + (summary["run_id"],))

    def _rebuild(self, conn, run_id, through):
        previous = conn.execute("SELECT value FROM settings WHERE key='published_through'").fetchone()
        events = conn.execute("SELECT * FROM current_movements WHERE is_void=0 ORDER BY event_id").fetchall()
        dates = [e["effective_date"] for e in events]
        horizon = max(dates + ([through] if through else []) + ([previous[0]] if previous else []), default=None)
        conn.execute("DELETE FROM daily_balances")
        conn.execute("DELETE FROM postings")
        totals = defaultdict(lambda: [0, 0, 0, 0, 0])
        first_dates = {}
        postings = []
        for e in events:
            q = e["quantity_milli"]
            kind = e["movement_type"]
            legs = [(e["location_id"], [q, 0, 0, 0, 0])] if kind == "RECEIPT" else (
                [(e["location_id"], [0, q, 0, 0, 0])] if kind == "ISSUE" else (
                [(e["location_id"], [0, 0, 0, 0, q])] if kind == "ADJUSTMENT" else [
                    (e["location_id"], [0, 0, 0, q, 0]),
                    (e["to_location_id"], [0, 0, q, 0, 0])]))
            for leg, (location, amounts) in enumerate(legs):
                postings.append((f"{e['event_id']}@{e['revision']}:{leg}", e["event_id"], e["revision"],
                                 e["effective_date"], e["item_id"], location, *amounts))
                key = (e["item_id"], location)
                first_dates[key] = min(first_dates.get(key, e["effective_date"]), e["effective_date"])
                bucket = totals[(e["effective_date"], *key)]
                for index, amount in enumerate(amounts):
                    bucket[index] += amount
                    if abs(bucket[index]) > SQLITE_LIMIT:
                        raise ValueError("aggregate quantity exceeds SQLite integer capacity")
        conn.executemany("INSERT INTO postings VALUES (?,?,?,?,?,?,?,?,?,?,?)", postings)
        rows = []
        for (item, location), first in sorted(first_dates.items()):
            opening = 0
            day = date.fromisoformat(first)
            end = date.fromisoformat(horizon)
            while day <= end:
                amounts = totals.get((day.isoformat(), item, location), (0, 0, 0, 0, 0))
                receipt, issue, incoming, outgoing, adjustment = amounts
                closing = opening + receipt - issue + incoming - outgoing + adjustment
                if abs(closing) > SQLITE_LIMIT:
                    raise ValueError("balance exceeds SQLite integer capacity")
                rows.append((day.isoformat(), item, location, opening, *amounts, closing, run_id))
                opening = closing
                if day == end:
                    break
                day += timedelta(days=1)
        conn.executemany("INSERT INTO daily_balances VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)
        if horizon:
            conn.execute("INSERT INTO settings VALUES ('published_through',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (horizon,))
        return horizon

    @staticmethod
    def _reconcile(conn):
        checks = []
        def check(name, expected, actual, details, quantity=False):
            formatter = format_quantity if quantity else str
            checks.append(dict(check_name=name, expected=formatter(expected), actual=formatter(actual),
                               variance=formatter(actual - expected), passed=(expected == actual), details=details))
        # Python summation avoids SQLite SUM coercing overflowed integers to imprecise reals.
        source = conn.execute("SELECT movement_type,quantity_milli FROM current_movements WHERE is_void=0").fetchall()
        expected = dict.fromkeys(MEASURES, 0)
        columns = {"RECEIPT": "receipts", "ISSUE": "issues", "ADJUSTMENT": "adjustments"}
        transfer_count = 0
        for row in source:
            if row[0] == "TRANSFER":
                expected["transfers_in"] += row[1]
                expected["transfers_out"] += row[1]
                transfer_count += 1
            else:
                expected[columns[row[0]]] += row[1]
        actual = dict.fromkeys(MEASURES, 0)
        for row in conn.execute("SELECT receipts_milli,issues_milli,transfers_in_milli,transfers_out_milli,adjustments_milli FROM postings"):
            for name, amount in zip(MEASURES, row):
                actual[name] += amount
        for name in MEASURES:
            check("source_to_postings_" + name, expected[name], actual[name], "Highest non-void revision vs generated postings", True)
        posting_count = conn.execute("SELECT COUNT(*) FROM postings").fetchone()[0]
        check("posting_row_count", len(source) + transfer_count, posting_count, "Two legs per transfer; one for other movements")
        bad = conn.execute("""SELECT COUNT(*) FROM postings p LEFT JOIN current_movements e
            ON p.event_id=e.event_id AND p.revision=e.revision
            WHERE e.event_id IS NULL OR e.is_void=1 OR p.effective_date!=e.effective_date
            OR p.item_id!=e.item_id OR NOT (
              (e.movement_type='RECEIPT' AND p.location_id=e.location_id AND p.receipts_milli=e.quantity_milli
                AND p.issues_milli=0 AND p.transfers_in_milli=0 AND p.transfers_out_milli=0 AND p.adjustments_milli=0)
              OR (e.movement_type='ISSUE' AND p.location_id=e.location_id AND p.issues_milli=e.quantity_milli
                AND p.receipts_milli=0 AND p.transfers_in_milli=0 AND p.transfers_out_milli=0 AND p.adjustments_milli=0)
              OR (e.movement_type='ADJUSTMENT' AND p.location_id=e.location_id AND p.adjustments_milli=e.quantity_milli
                AND p.receipts_milli=0 AND p.issues_milli=0 AND p.transfers_in_milli=0 AND p.transfers_out_milli=0)
              OR (e.movement_type='TRANSFER' AND p.receipts_milli=0 AND p.issues_milli=0 AND p.adjustments_milli=0 AND (
                (p.location_id=e.location_id AND p.transfers_out_milli=e.quantity_milli AND p.transfers_in_milli=0)
                OR (p.location_id=e.to_location_id AND p.transfers_in_milli=e.quantity_milli AND p.transfers_out_milli=0))))""").fetchone()[0]
        check("posting_mapping_violations", 0, bad, "Each posting matches its current source event, date, item, location and movement type")
        check("transfer_conservation", actual["transfers_in"], actual["transfers_out"], "Transfers conserve total stock", True)
        # SQLite promotes overflowing intermediate integer arithmetic to REAL,
        # even when offsetting movements leave a valid exact int64 closing.
        # Python integers preserve the same exact arithmetic as publication.
        bad = sum(row[6] != row[0]+row[1]-row[2]+row[3]-row[4]+row[5]
                  for row in conn.execute("""SELECT opening_milli,receipts_milli,issues_milli,
                      transfers_in_milli,transfers_out_milli,adjustments_milli,closing_milli
                      FROM daily_balances"""))
        check("daily_balance_equation_violations", 0, bad, "Every row satisfies opening + net movement = closing")
        bad = conn.execute("""SELECT COUNT(*) FROM daily_balances d JOIN daily_balances p
            ON d.item_id=p.item_id AND d.location_id=p.location_id AND p.balance_date=date(d.balance_date,'-1 day')
            WHERE d.opening_milli != p.closing_milli""").fetchone()[0]
        check("opening_continuity_violations", 0, bad, "Opening equals previous day's closing")
        posting_totals = defaultdict(lambda: [0] * len(MEASURES))
        for row in conn.execute("SELECT effective_date,item_id,location_id,receipts_milli,issues_milli,transfers_in_milli,transfers_out_milli,adjustments_milli FROM postings"):
            for index, amount in enumerate(tuple(row)[3:]):
                posting_totals[tuple(row)[:3]][index] += amount
        wrong_grains = 0
        item_closing = defaultdict(int)
        for row in conn.execute("SELECT * FROM daily_balances"):
            grain = (row["balance_date"], row["item_id"], row["location_id"])
            amounts = [row[name + "_milli"] for name in MEASURES]
            if amounts != posting_totals.pop(grain, [0] * len(MEASURES)):
                wrong_grains += 1
        check("daily_movement_grain_violations", 0, wrong_grains + len(posting_totals),
              "Daily movement columns equal posting totals at date/item/location grain")
        bad = conn.execute("""SELECT COUNT(*) FROM daily_balances d WHERE opening_milli != 0
            AND NOT EXISTS (SELECT 1 FROM daily_balances p WHERE p.item_id=d.item_id
              AND p.location_id=d.location_id AND p.balance_date < d.balance_date)""").fetchone()[0]
        check("first_day_opening_violations", 0, bad, "First modeled day starts at zero")
        ending_rows = conn.execute("""SELECT d.item_id,d.closing_milli FROM daily_balances d
            WHERE d.balance_date=(SELECT MAX(p.balance_date) FROM daily_balances p
              WHERE p.item_id=d.item_id AND p.location_id=d.location_id)""").fetchall()
        ending = sum(r[1] for r in ending_rows)
        for item, closing in ending_rows:
            item_closing[item] += closing
        source_net = defaultdict(int)
        for row in conn.execute("SELECT item_id,movement_type,quantity_milli FROM current_movements WHERE is_void=0"):
            source_net[row[0]] += (row[2] if row[1] in {"RECEIPT", "ADJUSTMENT"} else -row[2] if row[1] == "ISSUE" else 0)
        check("item_closing_stock_violations", 0,
              sum(source_net[k] != item_closing[k] for k in source_net.keys() | item_closing.keys()),
              "Each item's total closing equals its external net movement; units are never combined")
        check("global_closing_stock", expected["receipts"] - expected["issues"] + expected["adjustments"], ending,
              "Arithmetic checksum across quantities; per-item checks carry physical meaning", True)
        # Row accounting for every completed run (not the currently running one).
        bad = conn.execute("""SELECT COUNT(*) FROM runs WHERE status!='running' AND
            input_count != accepted_count+duplicate_count+rejected_count+rolled_back_count""").fetchone()[0]
        check("run_row_accounting_violations", 0, bad, "Every consumed row has exactly one recorded outcome")
        return checks

    def report(self, _connection=None):
        """One consistent read snapshot. Safe to call from separate HTTP threads."""
        with (nullcontext(_connection) if _connection is not None else self.connect()) as conn:
            if not conn.in_transaction:
                conn.execute("BEGIN")
            balances = []
            for row in conn.execute("SELECT * FROM daily_balances ORDER BY balance_date,item_id,location_id"):
                value = {k: row[k] for k in ("balance_date", "item_id", "location_id", "last_run_id")}
                for name in ("opening", *MEASURES, "closing"):
                    value[name] = format_quantity(row[name + "_milli"])
                value["is_negative"] = row["closing_milli"] < 0
                balances.append(value)
            runs = [dict(r) for r in conn.execute("SELECT * FROM runs ORDER BY started_at DESC,rowid DESC")]
            rejects = [dict(r) for r in conn.execute("SELECT * FROM raw_records WHERE outcome='rejected' ORDER BY rowid DESC LIMIT 500")]
            history = []
            for row in conn.execute("SELECT v.*,v.revision=(SELECT MAX(x.revision) FROM movement_versions x WHERE x.event_id=v.event_id) AS is_current FROM movement_versions v ORDER BY rowid DESC LIMIT 500"):
                value = {k: row[k] for k in ("event_id", "revision", "effective_date", "movement_type", "item_id", "location_id", "to_location_id", "is_void", "run_id", "source_file", "row_number", "is_current")}
                value["quantity"] = format_quantity(row["quantity_milli"])
                history.append(value)
            metrics = dict(current_events=conn.execute("SELECT COUNT(*) FROM current_movements WHERE is_void=0").fetchone()[0],
                           history_versions=conn.execute("SELECT COUNT(*) FROM movement_versions").fetchone()[0],
                           daily_rows=len(balances), negative_balance_days=sum(b["is_negative"] for b in balances),
                           rejected_rows=conn.execute("SELECT COUNT(*) FROM raw_records WHERE outcome='rejected'").fetchone()[0],
                           voided_events=conn.execute("SELECT COUNT(*) FROM current_movements WHERE is_void=1").fetchone()[0])
            horizon = conn.execute("SELECT value FROM settings WHERE key='published_through'").fetchone()
            demo = conn.execute("SELECT value FROM settings WHERE key='demo_examples_v1'").fetchone()
            return dict(metrics=metrics, balances=balances, runs=runs, rejects=rejects,
                        movements=history, reconciliation=self._reconcile(conn),
                        published_through=horizon[0] if horizon else None,
                        display_limits={"rejects": 500, "movements": 500}, generated_at=utc_now(),
                        demo_examples=json.loads(demo[0]) if demo else None)

    def changes(self, run_id=None, limit=100, offset=0):
        with self.connect() as conn:
            conn.execute("BEGIN")
            return changes_report(conn, run_id=run_id, limit=limit, offset=offset)

    def catalogs(self):
        with self.connect() as conn:
            conn.execute("BEGIN")
            return dict(items=[dict(r) for r in conn.execute("SELECT * FROM items ORDER BY item_id")],
                        locations=[dict(r) for r in conn.execute("SELECT * FROM locations ORDER BY location_id")])

    def export(self, output_dir):
        """Write shareable CSV/JSON; report.json is replaced last as the export manifest."""
        output = Path(output_dir)
        output.mkdir(parents=True, exist_ok=True)
        with self.connect() as conn:
            conn.execute("BEGIN")
            report = self.report(_connection=conn)
            datasets = {"daily_balances": report["balances"], "runs": report["runs"], "reconciliation": report["reconciliation"]}
            datasets["raw_records"] = [dict(r) for r in conn.execute("SELECT * FROM raw_records ORDER BY rowid")]
            datasets["movement_versions"] = [dict(r) for r in conn.execute("SELECT * FROM movement_versions ORDER BY event_id,revision")]
            datasets["postings"] = [dict(r) for r in conn.execute("SELECT * FROM postings ORDER BY posting_id")]
            datasets["balance_changes"] = [dict(r) for r in conn.execute("SELECT * FROM balance_changes ORDER BY run_id,balance_date,item_id,location_id")]
            fields = {name: [c[1] for c in conn.execute("PRAGMA table_info(" + name + ")")]
                      for name in ("runs", "raw_records", "movement_versions", "postings", "balance_changes")}
            fields["daily_balances"] = ["balance_date", "item_id", "location_id", "last_run_id", "opening", *MEASURES, "closing", "is_negative"]
            fields["reconciliation"] = ["check_name", "expected", "actual", "variance", "passed", "details"]
        # All rows are exported, including rejects beyond the dashboard's display cap.
        for name, records in datasets.items():
            with tempfile.NamedTemporaryFile("w", dir=output, newline="", encoding="utf-8", delete=False) as stream:
                temp = Path(stream.name)
                writer = csv.DictWriter(stream, fieldnames=fields[name])
                writer.writeheader()
                writer.writerows(records)
            os.replace(temp, output / (name + ".csv"))
        with tempfile.NamedTemporaryFile("w", dir=output, encoding="utf-8", delete=False) as stream:
            temp = Path(stream.name)
            json.dump(report, stream, indent=2)
            stream.write("\n")
        os.replace(temp, output / "report.json")
        return {"output_dir": str(output), "files": [n + ".csv" for n in datasets] + ["report.json"]}
