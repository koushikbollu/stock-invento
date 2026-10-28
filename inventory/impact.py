"""Retained, exact before/after evidence for successful inventory publications."""

import json

from .model import format_quantity

QUANTITIES = ("opening", "receipts", "issues", "transfers_in", "transfers_out", "adjustments", "closing")


def capture_balances(conn):
    return {
        (row["balance_date"], row["item_id"], row["location_id"]):
        {name: format_quantity(row[name + "_milli"]) for name in QUANTITIES}
        for row in conn.execute("SELECT * FROM daily_balances")
    }


def record_changes(conn, run_id, before):
    """Store only business changes. Lineage-only changes on rerun are excluded."""
    after = capture_balances(conn)
    batch = []
    count = 0
    for grain in sorted(before.keys() | after.keys()):
        old, new = before.get(grain), after.get(grain)
        if old == new:
            continue
        old_closing = int(old["closing"].replace(".", "")) if old else 0
        new_closing = int(new["closing"].replace(".", "")) if new else 0
        # Two valid int64 balances can have a delta wider than int64. Preserve it as
        # decimal integer text rather than losing precision or failing publication.
        batch.append((run_id, *grain, json.dumps(old, sort_keys=True) if old else None,
                      json.dumps(new, sort_keys=True) if new else None, str(new_closing - old_closing)))
        count += 1
        if len(batch) == 2000:
            conn.executemany("INSERT INTO balance_changes VALUES (?,?,?,?,?,?,?)", batch)
            batch.clear()
    conn.executemany("INSERT INTO balance_changes VALUES (?,?,?,?,?,?,?)", batch)
    return count


def changes_report(conn, run_id=None, limit=100, offset=0):
    if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 500:
        raise ValueError("limit must be an integer between 1 and 500")
    if isinstance(offset, bool) or not isinstance(offset, int) or offset < 0:
        raise ValueError("offset must be a non-negative integer")
    if run_id is None:
        run = conn.execute("SELECT * FROM runs ORDER BY started_at DESC,rowid DESC LIMIT 1").fetchone()
    else:
        run = conn.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if run is None:
            raise ValueError("run_id was not found")
    if run is None:
        return dict(run_id=None, run=None, has_snapshot=False, total=0, limit=limit, offset=offset,
                    summary=dict(changed_rows=0, affected_series=0, from_date=None, through_date=None), rows=[])
    run_id = run["run_id"]
    counts = conn.execute("SELECT COUNT(*),MIN(balance_date),MAX(balance_date) FROM balance_changes WHERE run_id=?", (run_id,)).fetchone()
    series = conn.execute("SELECT COUNT(*) FROM (SELECT DISTINCT item_id,location_id FROM balance_changes WHERE run_id=?)", (run_id,)).fetchone()[0]
    rows = []
    for row in conn.execute("SELECT * FROM balance_changes WHERE run_id=? ORDER BY balance_date,item_id,location_id LIMIT ? OFFSET ?", (run_id, limit, offset)):
        old = json.loads(row["before_json"]) if row["before_json"] else None
        new = json.loads(row["after_json"]) if row["after_json"] else None
        rows.append(dict(balance_date=row["balance_date"], item_id=row["item_id"], location_id=row["location_id"],
                         before_closing=old["closing"] if old else None, after_closing=new["closing"] if new else None,
                         before_opening=old["opening"] if old else None, after_opening=new["opening"] if new else None,
                         closing_delta=format_quantity(row["closing_delta_milli"]),
                         change_type="added" if old is None else "removed" if new is None else "updated",
                         changed_fields=[name for name in QUANTITIES if (old or {}).get(name) != (new or {}).get(name)],
                         before=old, after=new))
    return dict(run_id=run_id, run=dict(run), has_snapshot=bool(run["impact_recorded"]), total=counts[0], limit=limit, offset=offset,
                summary=dict(changed_rows=counts[0], affected_series=series, from_date=counts[1], through_date=counts[2]), rows=rows)
