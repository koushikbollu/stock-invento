"""Run all Python tests and save per-test JSON/JUnit evidence on a clean pass.

Run from any directory: python3 scripts/run_tests.py --out var/test-results
No third-party test runner is required. Failed runs never write a PASS report.
"""

import argparse
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import platform
import sys
import time
import unittest
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


class RecordedResult(unittest.TextTestResult):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.records = []
        self.subtest_checks = 0
        self.active = None
        self.started = None

    def startTest(self, test):
        super().startTest(test)
        self.active = dict(test_id=test.id(), status='running', subtest_checks=0)
        self.records.append(self.active)
        self.started = time.perf_counter()

    def stopTest(self, test):
        self.active['seconds'] = round(time.perf_counter() - self.started, 6)
        super().stopTest(test)

    def addSuccess(self, test):
        self.active['status'] = 'passed'
        super().addSuccess(test)

    def addFailure(self, test, err):
        self.active['status'] = 'failed'
        super().addFailure(test, err)

    def addError(self, test, err):
        self.active['status'] = 'error'
        super().addError(test, err)

    def addSkip(self, test, reason):
        self.active.update(status='skipped', reason=reason)
        super().addSkip(test, reason)

    def addExpectedFailure(self, test, err):
        self.active['status'] = 'expected_failure'
        super().addExpectedFailure(test, err)

    def addUnexpectedSuccess(self, test):
        self.active['status'] = 'unexpected_success'
        super().addUnexpectedSuccess(test)

    def addSubTest(self, test, subtest, err):
        self.subtest_checks += 1
        self.active['subtest_checks'] += 1
        if err is not None:
            self.active['status'] = 'failed'
        super().addSubTest(test, subtest, err)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--out', default='var/test-results')
    args = parser.parse_args(argv)
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    # These generated artifacts describe this invocation. A failed rerun must
    # not leave an older PASS beside its new failure log.
    for filename in ('unit-tests.txt', 'python-tests.json', 'junit.xml'):
        (output/filename).unlink(missing_ok=True)
    suite = unittest.defaultTestLoader.discover(str(ROOT/'tests'), top_level_dir=str(ROOT))
    log = io.StringIO()
    started = time.perf_counter()
    timestamp = datetime.now(timezone.utc).isoformat()
    result = unittest.TextTestRunner(stream=log, verbosity=2, resultclass=RecordedResult, buffer=True).run(suite)
    duration = round(time.perf_counter()-started, 6)
    clean = result.wasSuccessful() and all(row['status'] == 'passed' for row in result.records)
    if not clean:
        (output/'failed-unit-tests.txt').write_text(log.getvalue(), encoding='utf-8')
        print(log.getvalue(), file=sys.stderr)
        print('Tests did not all pass. No PASS JSON/JUnit report was written.', file=sys.stderr)
        return 1
    (output/'failed-unit-tests.txt').unlink(missing_ok=True)
    snapshot = {}
    for directory in ('inventory','tests'):
        for path in sorted((ROOT/directory).rglob('*')):
            if path.is_file() and '__pycache__' not in path.parts and path.suffix in {'.py','.js','.cjs','.html','.css'}:
                snapshot[path.relative_to(ROOT).as_posix()] = hashlib.sha256(path.read_bytes()).hexdigest()
    report = dict(passed=True, executed_at=timestamp, python=platform.python_version(), system=platform.system(),
                  architecture=platform.machine(), tests_run=result.testsRun, failures=len(result.failures),
                  errors=len(result.errors), skipped=len(result.skipped), subtest_checks=result.subtest_checks,
                  seconds=duration, tests=result.records, source_sha256=snapshot,
                  scope='Executed Python test methods and unittest subtests. Browser, performance and package checks have separate evidence.')
    (output/'unit-tests.txt').write_text(log.getvalue(), encoding='utf-8')
    (output/'python-tests.json').write_text(json.dumps(report,indent=2,sort_keys=True)+'\n',encoding='utf-8')
    xml = ET.Element('testsuite', name='Stock Invento Python acceptance and regression', tests=str(result.testsRun),
                     failures='0', errors='0', skipped='0', time=str(duration), timestamp=timestamp)
    for row in result.records:
        classname, name = row['test_id'].rsplit('.',1)
        case = ET.SubElement(xml,'testcase',classname=classname,name=name,time=str(row['seconds']))
        properties = ET.SubElement(case,'properties')
        ET.SubElement(properties,'property',name='subtest_checks',value=str(row['subtest_checks']))
    ET.indent(xml)
    ET.ElementTree(xml).write(output/'junit.xml', encoding='utf-8', xml_declaration=True)
    print(json.dumps(dict(passed=True,tests_run=result.testsRun,subtest_checks=result.subtest_checks,seconds=duration,
                          files=['unit-tests.txt','python-tests.json','junit.xml']),indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
