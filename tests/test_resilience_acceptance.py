"""Acceptance checks for process death, stable business IDs, and durable audit.

The child process is killed only after it has built uncommitted replacement
balances. This tests SQLite rollback and retry at a real process boundary.
"""

import csv
from datetime import datetime
from pathlib import Path
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

from inventory.pipeline import Inventory


ROOT = Path(__file__).resolve().parents[1]
FIELDS = ('event_id', 'revision', 'effective_date', 'movement_type', 'item_id',
          'location_id', 'to_location_id', 'quantity', 'is_void')
CHILD = r'''
from pathlib import Path
import sys
import time
from inventory.pipeline import Inventory
engine = Inventory(sys.argv[1])
original = engine._rebuild
def paused(connection, run_id, through):
    result = original(connection, run_id, through)
    Path(sys.argv[3]).write_text('replacement targets built but not committed')
    time.sleep(30)
    return result
engine._rebuild = paused
engine.ingest(sys.argv[2], through='2026-01-10')
'''


def business_rows(inventory):
    report = inventory.report()
    return [{key: value for key, value in row.items() if key != 'last_run_id'}
            for row in report['balances']]


class ResilienceAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='stock-invento-resilience-')
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)
        self.items = self.folder / 'items.csv'
        self.locations = self.folder / 'locations.csv'
        self.items.write_text('item_id,unit\nITEM-A,EA\nITEM-B,KG\n')
        self.locations.write_text('location_id\nWH-A\nWH-B\n')
        self.inventory = self.engine('state.db')

    def engine(self, name):
        engine = Inventory(self.folder / name)
        engine.load_catalogs(self.items, self.locations)
        return engine

    def source(self, name, rows):
        path = self.folder / name
        with path.open('w', newline='', encoding='utf-8') as stream:
            writer = csv.writer(stream)
            writer.writerow(FIELDS)
            writer.writerows(rows)
        return path

    def test_same_millisecond_runs_share_one_latest_audit_order(self):
        source = self.source('same-time.csv', [('receipt',1,'2026-01-01','RECEIPT','ITEM-A','WH-A','','1','false')])
        # UUID lexical order deliberately disagrees with insertion order.
        ids = ['ffffffff-ffff-4fff-8fff-ffffffffffff', '00000000-0000-4000-8000-000000000000']
        with mock.patch('inventory.pipeline.utc_now', return_value='2026-01-01T00:00:00.000+00:00'), \
             mock.patch('inventory.pipeline.uuid.uuid4', side_effect=ids):
            first = self.inventory.ingest(source)
            latest = self.inventory.ingest(source)
        self.assertEqual([row['run_id'] for row in self.inventory.report()['runs']], [latest['run_id'],first['run_id']])
        self.assertEqual(self.inventory.changes()['run_id'],latest['run_id'])

    def test_daily_equation_remains_exact_when_intermediate_sum_exceeds_int64(self):
        # A focused storage fixture exercises the aggregate boundary without
        # generating millions of individually bounded source movements.
        empty = self.source('empty.csv', [])
        run = self.inventory.ingest(empty)
        for sign in (1, -1):
            with self.subTest(sign=sign):
                edge = sign * (2**63 - 501)
                with self.inventory.connect() as connection:
                    connection.execute('DELETE FROM daily_balances')
                    amounts = (1000,1000) if sign > 0 else (0,1000)
                    adjustments = 0
                    incoming = 0 if sign > 0 else 1000
                    connection.execute('INSERT INTO daily_balances VALUES (?,?,?,?,?,?,?,?,?,?,?)',
                        ('2026-01-01','ITEM-A','WH-A',edge,*amounts,incoming,0,adjustments,edge,run['run_id']))
                checks = {check['check_name']:check for check in self.inventory.report()['reconciliation']}
                self.assertTrue(checks['daily_balance_equation_violations']['passed'])
                with self.inventory.connect() as connection:
                    connection.execute('UPDATE daily_balances SET closing_milli=?', (edge-sign,))
                checks = {check['check_name']:check for check in self.inventory.report()['reconciliation']}
                self.assertEqual(checks['daily_balance_equation_violations']['actual'],'1')
                self.assertFalse(checks['daily_balance_equation_violations']['passed'])

    def test_hard_process_death_rolls_back_uncommitted_targets_and_retry_recovers(self):
        initial = self.source('initial.csv', [('receipt',1,'2026-01-02','RECEIPT','ITEM-A','WH-A','','10.125','false')])
        self.inventory.ingest(initial, through='2026-01-05')
        before = business_rows(self.inventory)
        with self.inventory.connect() as connection:
            before_ids = [tuple(row) for row in connection.execute('SELECT posting_id,event_id,revision FROM postings')]
        replacement = self.source('replacement.csv', [
            ('receipt',2,'2026-01-01','RECEIPT','ITEM-A','WH-A','','20.125','false'),
            ('transfer',1,'2026-01-03','TRANSFER','ITEM-A','WH-A','WH-B','5.125','false'),
        ])
        ready = self.folder / 'uncommitted-ready.txt'
        with (self.folder / 'child-output.txt').open('w') as log:
            child = subprocess.Popen([sys.executable,'-c',CHILD,str(self.inventory.db_path),str(replacement),str(ready)],
                                     cwd=ROOT, stdout=log, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 10
                while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                    time.sleep(0.02)
                self.assertTrue(ready.exists(), 'child must reach the uncommitted publication boundary')
                # A WAL reader sees the complete old publication while a writer
                # has already replaced its private transaction's targets.
                self.assertEqual(business_rows(self.inventory), before)
                child.kill()
                child.wait(timeout=5)
            finally:
                if child.poll() is None:
                    child.kill()
                    child.wait(timeout=5)
        restarted = Inventory(self.inventory.db_path)
        self.assertEqual(business_rows(restarted), before)
        report = restarted.report()
        self.assertEqual(report['published_through'], '2026-01-05')
        self.assertEqual(report['metrics']['history_versions'], 1)
        unfinished = [run for run in report['runs'] if run['status'] == 'running']
        self.assertEqual(len(unfinished), 1)
        self.assertIsNone(unfinished[0]['finished_at'])
        self.assertEqual(unfinished[0]['source_file'], 'replacement.csv')
        # The incomplete attempt is deliberately visible and never fabricated
        # as successful. Uncommitted raw/history/impact rows do not survive.
        with restarted.connect() as connection:
            self.assertEqual(connection.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual([tuple(row) for row in connection.execute('SELECT posting_id,event_id,revision FROM postings')], before_ids)
            for table in ('raw_records','balance_changes','movement_versions'):
                self.assertEqual(connection.execute(f'SELECT COUNT(*) FROM {table} WHERE run_id=?',
                                                    (unfinished[0]['run_id'],)).fetchone()[0], 0)
        recovered = restarted.ingest(replacement, through='2026-01-10')
        self.assertEqual(recovered['accepted_count'], 2)
        self.assertTrue(all(check['passed'] for check in restarted.report()['reconciliation']))
        closings = {(row['item_id'],row['location_id']): row['closing'] for row in restarted.report()['balances']
                    if row['balance_date'] == '2026-01-10'}
        self.assertEqual(closings, {('ITEM-A','WH-A'):'15.000',('ITEM-A','WH-B'):'5.125'})
        self.assertEqual(restarted.report()['metrics']['history_versions'], 3)
        replay = restarted.ingest(replacement, through='2026-01-10')
        self.assertEqual((replay['accepted_count'],replay['duplicate_count']), (0,2))
        self.assertEqual(restarted.changes(replay['run_id'])['total'], 0)

    def test_posting_ids_are_deterministic_and_audit_ids_are_unique_iso_timestamps(self):
        source = self.source('stable.csv', [
            ('receipt:one',1,'2026-01-01','RECEIPT','ITEM-A','WH-A','','10.001','false'),
            ('transfer.two',1,'2026-01-02','TRANSFER','ITEM-A','WH-A','WH-B','1.001','false'),
            ('adjustment-three',1,'2026-01-03','ADJUSTMENT','ITEM-B','WH-B','','-0.001','false'),
        ])
        other = self.engine('other.db')
        first = self.inventory.ingest(source, through='2026-01-04')
        second = other.ingest(source, through='2026-01-04')
        self.assertNotEqual(first['run_id'],second['run_id'])
        self.assertEqual(business_rows(self.inventory), business_rows(other))
        identifiers = []
        for engine in (self.inventory, other):
            with engine.connect() as connection:
                self.assertEqual(connection.execute('PRAGMA foreign_keys').fetchone()[0], 1)
                self.assertEqual(connection.execute('PRAGMA foreign_key_check').fetchall(), [])
                identifiers.append([row[0] for row in connection.execute('SELECT posting_id FROM postings ORDER BY posting_id')])
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM raw_records WHERE source_file=?', ('stable.csv',)).fetchone()[0],3)
                self.assertEqual(connection.execute('SELECT COUNT(*) FROM movement_versions WHERE source_file=?', ('stable.csv',)).fetchone()[0],3)
        self.assertEqual(identifiers[0], identifiers[1])
        self.assertEqual(set(identifiers[0]), {'receipt:one@1:0','transfer.two@1:0','transfer.two@1:1','adjustment-three@1:0'})
        for run in (first,second):
            start, finish = (datetime.fromisoformat(run[key]) for key in ('started_at','finished_at'))
            self.assertIsNotNone(start.tzinfo)
            self.assertIsNotNone(finish.tzinfo)
            self.assertLessEqual(start,finish)
            self.assertEqual(run['source_file'],'stable.csv')
            self.assertEqual(run['input_count'],run['accepted_count']+run['duplicate_count']+run['rejected_count']+run['rolled_back_count'])
        # Reusing a database preserves business keys and records a distinct
        # operational attempt with no duplicate target or change rows.
        replay = self.inventory.ingest(source, through='2026-01-04')
        self.assertNotIn(replay['run_id'], {first['run_id'],second['run_id']})
        self.assertEqual(replay['duplicate_count'],3)
        self.assertEqual(self.inventory.changes(replay['run_id'])['total'],0)


if __name__ == '__main__':
    unittest.main()
