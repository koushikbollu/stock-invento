"""Password management uses hidden prompts and never resets an existing hash."""

from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from inventory.auth import AuthManager
from inventory.cli import main
from inventory.pipeline import Inventory


class PasswordCliTest(unittest.TestCase):
    def setUp(self):
        self.temporary=tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.db=Path(self.temporary.name)/'inventory.db'
        self.inventory=Inventory(self.db)

    def change(self, answers):
        output,error=io.StringIO(),io.StringIO()
        with mock.patch('getpass.getpass',side_effect=answers),redirect_stdout(output),redirect_stderr(error):
            status=main(['set-password','--db',str(self.db)])
        return status,output.getvalue(),error.getvalue()

    def test_hidden_prompt_changes_password_without_printing_it_or_resetting_on_startup(self):
        AuthManager(self.inventory)
        status,output,error=self.change(['new-local-password','new-local-password'])
        self.assertEqual(status,0,error)
        self.assertTrue(json.loads(output)['password_updated'])
        self.assertNotIn('new-local-password',output+error)
        restarted=AuthManager(self.inventory)
        secret,_=restarted.begin_login()
        self.assertIsNone(restarted.authenticate('admin','admin123','local',secret))
        self.assertIsNotNone(restarted.authenticate('admin','new-local-password','local',secret))
        with self.inventory.connect() as connection:
            stored=bytes(connection.execute('SELECT password_hash FROM web_users').fetchone()[0])
        self.assertNotEqual(stored,b'new-local-password')
        folder=Path(self.temporary.name)/'export'
        exported=self.inventory.export(folder)
        self.assertNotIn('web_users.csv',exported['files'])
        exported_text=''.join((folder/name).read_text() for name in exported['files'])
        self.assertNotIn('new-local-password',exported_text)
        self.assertNotIn(stored.hex(),exported_text)

    def test_mismatch_or_short_password_preserves_existing_credentials(self):
        AuthManager(self.inventory)
        with self.inventory.connect() as connection:
            before=tuple(connection.execute('SELECT * FROM web_users').fetchone())
        for answers in (['one-password','different-password'],['short','short']):
            with self.subTest(answers_kind='mismatch' if answers[0]!=answers[1] else 'short'):
                status,output,error=self.change(answers)
                self.assertEqual(status,1)
                self.assertIn('error',json.loads(error))
                with self.inventory.connect() as connection:
                    self.assertEqual(tuple(connection.execute('SELECT * FROM web_users').fetchone()),before)

    def test_nonexistent_database_does_not_prompt_or_create_a_file(self):
        missing=Path(self.temporary.name)/'missing.db'
        with mock.patch('getpass.getpass') as prompt,redirect_stderr(io.StringIO()):
            self.assertEqual(main(['set-password','--db',str(missing)]),1)
        prompt.assert_not_called()
        self.assertFalse(missing.exists())


if __name__=='__main__':
    unittest.main()
