"""Seed real, clearly identified examples for every interactive report view."""

import csv
import hashlib
import io
import json
from pathlib import Path
import tempfile
import uuid

from .pipeline import PipelineError


DEMO_MARKER = "demo_examples_v1"
DEMO_PROGRESS = "demo_examples_v1_progress"


def _save_progress(inventory, progress):
    with inventory.connect() as connection:
        connection.execute("""INSERT INTO settings(key,value) VALUES (?,?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value""",
            (DEMO_PROGRESS, json.dumps(progress, sort_keys=True)))


def _matching_run(inventory, intent, scenario, source):
    """Find only this durable intent's committed, independently verified audit.

    The unguessable source basename identifies ownership across a process crash.
    A starting audit boundary plus exact raw payload/count checks prevent reuse
    of ordinary user imports that happen to have the same template filename.
    """
    expected = list(csv.DictReader(io.StringIO(source.decode("utf-8-sig")), strict=True))
    with inventory.connect() as connection:
        candidates = connection.execute("""SELECT rowid AS audit_rowid,* FROM runs
            WHERE source_file=? AND rowid>? ORDER BY rowid""",
            (intent["source_file"], intent["after_audit_rowid"])).fetchall()
        for candidate in candidates:
            run = dict(candidate)
            if intent.get("run_id") and run["run_id"] != intent["run_id"]:
                continue
            raw = connection.execute("SELECT raw_json,outcome FROM raw_records WHERE run_id=? ORDER BY row_number",
                                     (run["run_id"],)).fetchall()
            if scenario == "failure":
                matches = (run["status"] == "failed" and (run["error"] or "").startswith("unexpected schema:")
                           and run["input_count"] == 0 and not raw)
            else:
                payloads_match = len(raw) == len(expected) and all(json.loads(row["raw_json"]) == payload
                                                                for row, payload in zip(raw, expected))
                common = (payloads_match and run["input_count"] == len(expected)
                          and run["rolled_back_count"] == 0)
                if scenario == "validation":
                    matches = (common and run["status"] == "succeeded_with_rejects"
                               and run["accepted_count"] == 0 and run["duplicate_count"] == 0
                               and run["rejected_count"] == 3 and all(row["outcome"] == "rejected" for row in raw))
                elif scenario == "recovery":
                    matches = (common and run["status"] == "succeeded" and run["accepted_count"] == 0
                               and run["duplicate_count"] == 50 and run["rejected_count"] == 0
                               and all(row["outcome"] == "duplicate" for row in raw))
                else:
                    matches = (common and run["status"] == "succeeded" and run["rejected_count"] == 0
                               and run["accepted_count"] + run["duplicate_count"] == 1
                               and all(row["outcome"] in {"accepted", "duplicate"} for row in raw))
            if matches:
                return run["run_id"]
    return None


def _scenario(inventory, progress, name, template):
    source = template.read_bytes()
    digest = hashlib.sha256(source).hexdigest()
    intent = progress["scenarios"].get(name)
    if intent is None:
        token = uuid.uuid4().hex[:12]
        with inventory.connect() as connection:
            boundary = connection.execute("SELECT COALESCE(MAX(rowid),0) FROM runs").fetchone()[0]
        intent = dict(token=token, source_file=f"{template.stem}.{token}.csv",
                      source_sha256=digest, after_audit_rowid=boundary)
        progress["scenarios"][name] = intent
        # Commit the unique intent before ingestion can commit its audit.
        _save_progress(inventory, progress)
    elif intent["source_sha256"] != digest:
        raise RuntimeError("an unfinished demo scenario's source changed; restore its original template before retrying")

    run_id = _matching_run(inventory, intent, name, source)
    if intent.get("run_id") and run_id is None:
        raise RuntimeError("retained demo scenario evidence does not match its checkpoint")
    if run_id is None:
        with tempfile.TemporaryDirectory(prefix="stock-invento-demo-") as temporary:
            input_path = Path(temporary) / intent["source_file"]
            input_path.write_bytes(source)
            try:
                inventory.ingest(input_path, through="2026-01-04")
            except PipelineError:
                # Only the deliberate schema failure is a successful teaching
                # step. Unexpected operational or validation failures escape.
                if name != "failure" or _matching_run(inventory, intent, name, source) is None:
                    raise
        run_id = _matching_run(inventory, intent, name, source)
        if run_id is None:
            raise RuntimeError(f"demo {name} did not produce its expected audited outcome")
    if intent.get("run_id") != run_id:
        intent["run_id"] = run_id
        _save_progress(inventory, progress)
    return run_id


def seed_demo_examples(inventory, initial_run, correction_run, data_dir):
    """Run the teaching scenarios once, preserving their actual operational IDs.

    Each ingestion has its ordinary transaction/audit behavior. Durable intents
    and validated audit checkpoints make retries safe even between ingestion
    commit and checkpoint save. The public marker is written only after recovery.
    """
    with inventory.connect() as connection:
        existing = connection.execute("SELECT value FROM settings WHERE key=?", (DEMO_MARKER,)).fetchone()
        saved_progress = connection.execute("SELECT value FROM settings WHERE key=?", (DEMO_PROGRESS,)).fetchone()
    if existing:
        return json.loads(existing[0])

    data_dir = Path(data_dir)
    progress = json.loads(saved_progress[0]) if saved_progress else dict(
        version=1, initial_run_id=initial_run["run_id"], correction_run_id=correction_run["run_id"], scenarios={})
    if progress.get("version") != 1 or not isinstance(progress.get("scenarios"), dict):
        raise RuntimeError("unsupported demo progress metadata")
    if saved_progress is None:
        _save_progress(inventory, progress)
    runs = {"initial": progress["initial_run_id"], "correction": progress["correction_run_id"]}
    for name, filename in (("cancellation", "demo_cancel_transfer.csv"),
                           ("restoration", "demo_restore_transfer.csv"),
                           ("validation", "demo_quality_examples.csv"),
                           ("failure", "demo_expected_schema_failure.csv"),
                           ("recovery", "movements.csv")):
        runs[name] = _scenario(inventory, progress, name, data_dir / filename)
    metadata = dict(version=1, initial_movement_count=50, expected_rejected_rows=3,
                    transfer_event_id="demo-c-transfer-1", runs=runs)
    with inventory.connect() as connection:
        connection.execute("INSERT INTO settings(key,value) VALUES (?,?)",
                           (DEMO_MARKER, json.dumps(metadata, sort_keys=True)))
    return metadata
