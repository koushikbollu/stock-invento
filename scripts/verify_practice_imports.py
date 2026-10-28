"""Verify included practice CSVs in a temporary seeded workspace (standard library only)."""
import argparse
import contextlib
import csv
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import tempfile
import logging

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from inventory.cli import main as cli_main
from inventory.pipeline import Inventory


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def business(rows):
    return [{key: value for key, value in row.items() if key != 'last_run_id'} for row in rows]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='var/practice-file-verification.json')
    args = parser.parse_args()
    output = Path(args.out).resolve()
    # Never leave an older success artifact beside a failed rerun.
    output.unlink(missing_ok=True)
    fixture = ROOT / 'data/import-practice'
    oracle_file = ROOT / 'data/expected/import_practice_balances.csv'
    with oracle_file.open(newline='', encoding='utf-8') as stream:
        answers = list(csv.DictReader(stream))
    results = []
    expectations = [(name, accepted, rejected) for name, accepted, rejected in (
        ('01_receipts.csv', 2, 0), ('02_issues_transfers_adjustments.csv', 3, 0),
        ('03_backdated_correction.csv', 1, 0), ('04_mixed_valid_and_invalid.csv', 1, 3),
        ('05_negative_stock.csv', 1, 0), ('06_fix_negative_stock.csv', 1, 0))]
    logging.getLogger('inventory').setLevel(logging.CRITICAL)
    with tempfile.TemporaryDirectory(prefix='stock-invento-practice-') as temporary:
        with contextlib.redirect_stdout(io.StringIO()):
            status = cli_main(['demo', '--out', temporary])
        require(status == 0, 'fresh seeded demo failed')
        inventory = Inventory(Path(temporary) / 'inventory.db')
        original = business(inventory.report()['balances'])
        missing = inventory.ingest(fixture / '01_receipts.csv')
        require((missing['accepted_count'], missing['rejected_count']) == (0, 2), 'missing catalogs must quarantine both rows')
        inventory.load_catalogs(fixture / '00_items.csv', fixture / '00_locations.csv')
        references = inventory.catalogs()
        inventory.load_catalogs(fixture / '00_items.csv', fixture / '00_locations.csv')
        require(inventory.catalogs() == references, 'reloading catalogs changed reference data')
        for filename, accepted, rejected in expectations:
            run = inventory.ingest(fixture / filename)
            require((run['accepted_count'], run['rejected_count'], run['duplicate_count']) == (accepted, rejected, 0), filename + ': wrong first-import counts')
            report = inventory.report()
            practice = [row for row in report['balances'] if row['item_id'] == 'PRACTICE-ITEM']
            expected = [row for row in answers if row['after_file'] == filename]
            actual = {(row['balance_date'], row['location_id']): row['closing'] for row in practice}
            target = {(row['balance_date'], row['location_id']): row['closing'] for row in expected}
            require(actual == target, filename + ': hand-calculated balance mismatch')
            require(all(row['passed'] for row in report['reconciliation']), filename + ': reconciliation failed')
            preserved = business([row for row in report['balances'] if row['item_id'] != 'PRACTICE-ITEM'])
            require(preserved == original, filename + ': seeded balances changed')
            before = business(report['balances'])
            replay = inventory.ingest(fixture / filename)
            require((replay['accepted_count'], replay['duplicate_count'], replay['rejected_count'], replay['changed_balance_rows']) == (0, accepted, rejected, 0), filename + ': wrong replay outcome')
            require(business(inventory.report()['balances']) == before, filename + ': replay changed balances')
            results.append(dict(file=filename, passed=True, accepted=accepted, rejected=rejected,
                                balance_rows_checked=len(expected), reconciliation_checks=len(report['reconciliation']),
                                replay_accepted=0, replay_duplicates=accepted, replay_rejected=rejected,
                                replay_changed_balance_rows=0, original_demo_balances_unchanged=True))
    paths = sorted(fixture.glob('*.csv')) + [oracle_file]
    result = dict(passed=True, executed_at=datetime.now(timezone.utc).isoformat(),
                  python=platform.python_version(), system=platform.system(),
                  scope='Actual included CSV sequence, independent answer sheet and replay in a temporary seeded workspace; no user database touched',
                  catalog_files=2, movement_files=len(results), balance_rows_checked=sum(row['balance_rows_checked'] for row in results),
                  missing_catalog_rows_quarantined=2, repeated_catalog_load_identical=True,
                  stages=results, input_sha256={path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in paths})
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(dict(passed=True, movement_files=len(results), balance_rows_checked=result['balance_rows_checked'], output=str(output)), indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
