"""Portable launcher boundaries: validation, path resolution and browser timing."""

import contextlib
import io
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

import run_demo

ROOT = Path(__file__).resolve().parents[1]


class FakeServer:
    def __init__(self, events):
        self.events = events

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.events.append("closed")

    def serve_forever(self):
        self.events.append("served")
        raise KeyboardInterrupt


class StartupTest(unittest.TestCase):
    def exercise(self, arguments):
        events = []
        output = io.StringIO()

        def seed(args):
            events.append("seeded")
            return 0

        def bind(*args, **kwargs):
            events.append("bound")
            return FakeServer(events)

        def browser(*args, **kwargs):
            events.append("browser")
            return True

        with mock.patch.object(run_demo, "cli_main", side_effect=seed) as cli, \
             mock.patch.object(run_demo, "create_server", side_effect=bind) as server, \
             mock.patch.object(run_demo.webbrowser, "open", side_effect=browser), \
             contextlib.redirect_stdout(output):
            status = run_demo.main(arguments)
        self.assertEqual(status, 0)
        return events, output.getvalue(), cli, server

    def test_browser_opens_only_after_server_is_bound(self):
        events, text, _, server = self.exercise(["--port", "8766"])
        self.assertEqual(events, ["seeded", "bound", "browser", "served", "closed"])
        self.assertIn("http://127.0.0.1:8766", text)
        self.assertIn("local data is retained", text)
        self.assertEqual(server.call_args.kwargs["port"], 8766)

    def test_no_browser_and_relative_folder_work_from_another_directory(self):
        original = Path.cwd()
        with tempfile.TemporaryDirectory() as temporary:
            try:
                os.chdir(temporary)
                events, _, cli, server = self.exercise(["--no-browser", "--data-dir", "var/separate-review"])
            finally:
                os.chdir(original)
        folder = ROOT / "var" / "separate-review"
        self.assertEqual(cli.call_args.args[0], ["demo", "--out", str(folder)])
        self.assertEqual(server.call_args.args[0], folder / "inventory.db")
        self.assertNotIn("browser", events)

    def test_absolute_folder_with_spaces_is_honored(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary) / "review data"
            _, _, cli, _ = self.exercise(["--no-browser", "--data-dir", str(folder)])
            self.assertEqual(cli.call_args.args[0][-1], str(folder.resolve()))

    def test_invalid_port_is_rejected_before_seeding(self):
        for port in ("0", "-1", "65536"):
            with self.subTest(port=port), mock.patch.object(run_demo, "cli_main") as cli, \
                 contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as error:
                run_demo.main(["--port", port])
            self.assertEqual(error.exception.code, 2)
            cli.assert_not_called()

    def test_busy_port_does_not_open_an_unrelated_service(self):
        with mock.patch.object(run_demo, "cli_main", return_value=0), \
             mock.patch.object(run_demo, "create_server", side_effect=OSError("address already in use")), \
             mock.patch.object(run_demo.webbrowser, "open") as browser, \
             contextlib.redirect_stderr(io.StringIO()) as errors:
            self.assertEqual(run_demo.main(["--port", "8765"]), 1)
        browser.assert_not_called()
        self.assertIn("--port 8766", errors.getvalue())

    def test_unavailable_browser_keeps_server_usable(self):
        events = []
        with mock.patch.object(run_demo, "cli_main", return_value=0), \
             mock.patch.object(run_demo, "create_server", return_value=FakeServer(events)), \
             mock.patch.object(run_demo.webbrowser, "open", return_value=False), \
             contextlib.redirect_stdout(io.StringIO()) as output:
            self.assertEqual(run_demo.main([]), 0)
        self.assertIn("manually", output.getvalue())
        self.assertEqual(events, ["served", "closed"])

    def test_old_python_receives_clear_message_before_application_import(self):
        script = "import runpy,sys; sys.version_info=(3,9,0,'final',0); runpy.run_path('run_demo.py',run_name='__main__')"
        result = subprocess.run([sys.executable, "-c", script], cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn("Python 3.10 or newer", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
