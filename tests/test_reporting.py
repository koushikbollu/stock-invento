"""The evidence runner must never leave stale PASS artifacts after failure."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock
import xml.etree.ElementTree as ET

from scripts import run_tests


class ReportRunnerAcceptanceTest(unittest.TestCase):
    def test_failed_rerun_invalidates_old_pass_artifacts(self):
        class FailingFixture(unittest.TestCase):
            def test_controlled_failure(self):
                self.fail('intentional reporting-tool self-check')
        with tempfile.TemporaryDirectory() as temporary:
            out = Path(temporary)
            for name in ('unit-tests.txt','python-tests.json','junit.xml'):
                (out/name).write_text('old PASS data')
            suite = unittest.TestSuite([FailingFixture('test_controlled_failure')])
            with mock.patch.object(run_tests.unittest.defaultTestLoader,'discover',return_value=suite), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                status = run_tests.main(['--out',str(out)])
            self.assertEqual(status,1)
            self.assertTrue((out/'failed-unit-tests.txt').is_file())
            self.assertIn('intentional reporting-tool self-check',(out/'failed-unit-tests.txt').read_text())
            self.assertTrue(all(not (out/name).exists() for name in ('unit-tests.txt','python-tests.json','junit.xml')))

    def test_success_writes_matching_json_junit_and_clears_old_failure_log(self):
        class PassingFixture(unittest.TestCase):
            def test_controlled_success(self):
                with self.subTest(value=1):
                    self.assertEqual(1+1,2)
        with tempfile.TemporaryDirectory() as temporary:
            out=Path(temporary)
            (out/'failed-unit-tests.txt').write_text('previous diagnostic')
            suite=unittest.TestSuite([PassingFixture('test_controlled_success')])
            with mock.patch.object(run_tests.unittest.defaultTestLoader,'discover',return_value=suite), \
                 redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                status=run_tests.main(['--out',str(out)])
            self.assertEqual(status,0)
            self.assertFalse((out/'failed-unit-tests.txt').exists())
            report=json.loads((out/'python-tests.json').read_text())
            self.assertEqual((report['tests_run'],report['subtest_checks'],report['failures'],report['errors']),(1,1,0,0))
            self.assertTrue(report['passed'])
            self.assertEqual(report['tests'][0]['status'],'passed')
            xml=ET.parse(out/'junit.xml').getroot()
            self.assertEqual(xml.attrib['tests'],'1')
            self.assertEqual(len(xml.findall('testcase')),1)
            self.assertIn('Ran 1 test',(out/'unit-tests.txt').read_text())


if __name__=='__main__':
    unittest.main()
