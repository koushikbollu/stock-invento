"""Authentication at the actual local HTTP boundary, using real session cookies."""

import http.client
from http.cookies import SimpleCookie
import hashlib
import json
from pathlib import Path
import tempfile
import threading
import unittest

from inventory.pipeline import Inventory
from inventory.auth import (ABSOLUTE_SECONDS, FAILURE_LIMIT, FAILURE_WINDOW, IDLE_SECONDS,
                            LOGIN_SECONDS, PASSWORD_ITERATIONS, AuthManager, LoginThrottled, set_password)
from inventory.web import create_server


SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample"


class AuthHttpAcceptanceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="inventory-auth-acceptance-")
        self.addCleanup(temporary.cleanup)
        self.db = Path(temporary.name) / "inventory.db"
        self.inventory = Inventory(self.db)
        self.inventory.load_catalogs(SAMPLE / "items.csv", SAMPLE / "locations.csv")
        self.inventory.ingest(SAMPLE / "movements.csv", through="2026-01-04")
        self.cookies = {}
        self.start_server()
        self.addCleanup(self.stop_server)

    def start_server(self):
        self.server = create_server(self.db, port=0)
        self.server.RequestHandlerClass.log_message = lambda *_args: None
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.port = self.server.server_port
        self.origin = f"http://127.0.0.1:{self.port}"

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def cookie_header(self):
        return "; ".join(f"{name}={value}" for name, value in self.cookies.items())

    def request(self, method, path, payload=None, headers=None, cookie=None):
        values = dict(headers or {})
        selected = self.cookie_header() if cookie is None else cookie
        if selected:
            values.setdefault("Cookie", selected)
        body = None
        if payload is not None:
            body = json.dumps(payload).encode("utf-8")
            values.setdefault("Content-Type", "application/json")
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            connection.request(method, path, body=body, headers=values)
            response = connection.getresponse()
            content = response.read()
            response_headers = response.getheaders()
            for name, value in response_headers if cookie is None else ():
                if name.lower() == "set-cookie":
                    for key, morsel in SimpleCookie(value).items():
                        if not morsel.value or morsel["max-age"] == "0":
                            self.cookies.pop(key, None)
                        else:
                            self.cookies[key] = morsel.value
            try:
                result = json.loads(content)
            except ValueError:
                result = content.decode("utf-8")
            return response.status, result, response_headers
        finally:
            connection.close()

    def login(self, username="admin", password="admin123"):
        status, preauth, _ = self.request("GET", "/api/login-session")
        self.assertEqual(status, 200)
        return self.request("POST", "/api/login", {"username": username, "password": password},
                            {"Origin": self.origin, "X-Stockline-Token": preauth["csrf_token"]})

    def session(self):
        status, session, _ = self.request("GET", "/api/session")
        self.assertEqual(status, 200)
        self.assertEqual(session["username"], "admin")
        self.assertGreater(session["expires_in"], 0)
        return session

    def test_auth_a01_anonymous_data_routes_and_mutations_require_login(self):
        """AUTH-A01: every ledger/data boundary is protected, before mutation parsing."""
        routes = ("/api/report", "/api/catalogs", "/api/showcase", "/api/changes", "/api/session",
                  "/api/sample/movements.csv", "/api/demo/movements.csv")
        for path in routes:
            with self.subTest(path=path):
                status, result, _ = self.request("GET", path, cookie="")
                self.assertEqual(status, 401)
                self.assertTrue(result["error"])
        before = self.inventory.report()["runs"]
        for path in ("/api/import", "/api/catalogs", "/api/logout"):
            with self.subTest(path=path):
                self.assertEqual(self.request("POST", path, [], {"Origin": self.origin}, cookie="")[0], 401)
        self.assertEqual(self.inventory.report()["runs"], before)
        for path in ("/", "/index.html"):
            with self.subTest(path=path):
                status, _, headers = self.request("GET", path, cookie="")
                self.assertEqual(status, 302)
                self.assertEqual(dict(headers)["Location"], "/login")
        status, page, _ = self.request("GET", "/login", cookie="")
        self.assertEqual(status, 200)
        self.assertIn("password", page.lower())

    def test_auth_a02_wrong_credentials_deny_and_correct_credentials_unlock_session(self):
        """AUTH-A02: wrong credentials reveal no password and cannot open report data."""
        status, result, _ = self.login(password="wrong-password")
        self.assertEqual(status, 401)
        self.assertNotIn("admin123", json.dumps(result))
        self.assertEqual(self.request("GET", "/api/report")[0], 401)
        status, result, headers = self.login()
        self.assertEqual(status, 200)
        self.assertEqual(result["username"], "admin")
        self.assertTrue(any(name.lower() == "set-cookie" and "httponly" in value.lower() for name, value in headers))
        session = self.session()
        self.assertTrue(session["csrf_token"])
        self.assertEqual(self.request("GET", "/api/report")[0], 200)

    def test_auth_a03_login_needs_its_own_cookie_token_and_local_origin(self):
        """AUTH-A03: a login request needs a matching preauth cookie and CSRF token."""
        status, preauth, headers = self.request("GET", "/api/login-session")
        self.assertEqual(status, 200)
        self.assertTrue(any(name.lower() == "set-cookie" and "httponly" in value.lower() for name, value in headers))
        payload = {"username": "admin", "password": "admin123"}
        self.assertEqual(self.request("POST", "/api/login", payload, {"Origin": self.origin})[0], 403)
        self.assertEqual(self.request("POST", "/api/login", payload, {"Origin": self.origin, "X-Stockline-Token": "forged"})[0], 403)
        self.assertEqual(self.request("POST", "/api/login", payload, {"Origin": "https://unrelated.example", "X-Stockline-Token": preauth["csrf_token"]})[0], 403)
        self.assertEqual(self.request("POST", "/api/login", payload, {"Origin": self.origin, "X-Stockline-Token": preauth["csrf_token"]}, cookie="")[0], 403)
        self.assertEqual(self.request("GET", "/api/report")[0], 401)

    def test_auth_a04_preauth_and_forged_cookies_cannot_authorize_mutation(self):
        """AUTH-A04: preauth credentials do not substitute for an authenticated session."""
        _, preauth, _ = self.request("GET", "/api/login-session")
        old_cookie = self.cookie_header()
        self.assertEqual(self.request("GET", "/api/report", cookie=old_cookie)[0], 401)
        self.assertEqual(self.login()[0], 200)
        session = self.session()
        forged = "; ".join(f"{name}=forged-session" for name in self.cookies)
        self.assertEqual(self.request("GET", "/api/report", cookie=forged)[0], 401)
        payload = {"filename": "sample.csv", "csv_text": (SAMPLE / "movements.csv").read_text(encoding="utf-8")}
        self.assertEqual(self.request("POST", "/api/import", payload,
                         {"Origin": self.origin, "X-Stockline-Token": preauth["csrf_token"]})[0], 403)
        self.assertEqual(self.request("POST", "/api/import", payload,
                         {"Origin": self.origin, "X-Stockline-Token": session["csrf_token"]}, cookie=old_cookie)[0], 401)
        self.assertEqual(self.request("GET", "/api/report")[0], 200)

    def test_auth_a05_authenticated_mutations_keep_origin_and_csrf_guards(self):
        """AUTH-A05: authentication does not bypass existing mutation origin/CSRF checks."""
        self.assertEqual(self.login()[0], 200)
        token = self.session()["csrf_token"]
        payload = {"filename": "sample.csv", "csv_text": (SAMPLE / "movements.csv").read_text(encoding="utf-8")}
        before = len(self.inventory.report()["runs"])
        for headers in ({"Origin": self.origin}, {"X-Stockline-Token": token},
                        {"Origin": "https://unrelated.example", "X-Stockline-Token": token}):
            with self.subTest(headers=headers):
                self.assertEqual(self.request("POST", "/api/import", payload, headers)[0], 403)
        self.assertEqual(len(self.inventory.report()["runs"]), before)
        status, result, _ = self.request("POST", "/api/import", payload,
                                        {"Origin": self.origin, "X-Stockline-Token": token})
        self.assertEqual(status, 200)
        self.assertEqual((result["run"]["accepted_count"], result["run"]["duplicate_count"]), (0, 7))

    def test_auth_a06_logout_invalidates_cookie_and_requires_authentication_to_reopen(self):
        """AUTH-A06: logout revokes server-side state, including a copied old cookie."""
        self.assertEqual(self.login()[0], 200)
        token = self.session()["csrf_token"]
        old_cookie = self.cookie_header()
        self.assertEqual(self.request("POST", "/api/logout", {}, {"Origin": self.origin})[0], 403)
        self.assertEqual(self.request("GET", "/api/report")[0], 200)
        status, _, headers = self.request("POST", "/api/logout", {}, {"Origin": self.origin, "X-Stockline-Token": token})
        self.assertEqual(status, 200)
        self.assertTrue(any(name.lower() == "set-cookie" and ("max-age=0" in value.lower() or "expires=" in value.lower()) for name, value in headers))
        self.assertEqual(self.request("GET", "/api/report")[0], 401)
        self.assertEqual(self.request("GET", "/api/report", cookie=old_cookie)[0], 401)

    def test_auth_a07_new_login_rotates_session_and_rejects_previous_cookie(self):
        """AUTH-A07: successful relogin rotates session identity and CSRF state."""
        self.assertEqual(self.login()[0], 200)
        first_cookie = self.cookie_header()
        first_token = self.session()["csrf_token"]
        self.assertEqual(self.login()[0], 200)
        self.assertNotEqual(self.cookie_header(), first_cookie)
        self.assertNotEqual(self.session()["csrf_token"], first_token)
        self.assertEqual(self.request("GET", "/api/report", cookie=first_cookie)[0], 401)

    def test_auth_a08_server_restart_invalidates_memory_sessions_but_credentials_persist(self):
        """AUTH-A08: a restarted process rejects old sessions while retaining the account."""
        self.assertEqual(self.login()[0], 200)
        old_cookie = self.cookie_header()
        self.stop_server()
        self.start_server()
        self.assertEqual(self.request("GET", "/api/report", cookie=old_cookie)[0], 401)
        self.assertEqual(self.login()[0], 200)
        self.assertEqual(self.request("GET", "/api/report")[0], 200)

    def test_auth_a09_repeated_bad_passwords_throttle_with_retry_after(self):
        """AUTH-A09: five failed attempts prevent another password check in the window."""
        for attempt in range(5):
            with self.subTest(attempt=attempt + 1):
                self.assertEqual(self.login(password="bad-password")[0], 401)
        status, result, headers = self.login(password="bad-password")
        self.assertEqual(status, 429)
        self.assertTrue(result["error"])
        self.assertGreater(int(dict(headers)["Retry-After"]), 0)

    def test_auth_a10_idle_session_expiry_protects_http_data_routes(self):
        """AUTH-A10: an idle expiry is enforced by the real HTTP authorization boundary."""
        clock = [0.0]
        self.server.auth.clock = lambda: clock[0]
        self.assertEqual(self.login()[0], 200)
        self.assertEqual(self.request("GET", "/api/report")[0], 200)
        clock[0] = IDLE_SECONDS
        self.assertEqual(self.request("GET", "/api/report")[0], 401)
        self.assertEqual(self.request("GET", "/api/session")[0], 401)


class AuthManagerAcceptanceTest(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="inventory-auth-manager-")
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)
        self.inventory = Inventory(self.directory / "inventory.db")
        self.now = 0.0
        self.manager = AuthManager(self.inventory, clock=lambda: self.now)

    def authenticate(self, manager=None, password="admin123", client="unit-client"):
        manager = manager or self.manager
        login_secret, csrf = manager.begin_login()
        self.assertTrue(manager.valid_login_token(login_secret, csrf))
        secret = manager.authenticate("admin", password, client, login_secret)
        return secret

    def credential(self, inventory=None):
        with (inventory or self.inventory).connect() as connection:
            return dict(connection.execute("SELECT * FROM web_users WHERE username='admin'").fetchone())

    def test_auth_u01_bootstrap_hash_is_salted_persistent_and_excluded_from_exports(self):
        """AUTH-U01: stored credentials use the specified password KDF and stay out of reports."""
        stored = self.credential()
        self.assertEqual(stored["iterations"], PASSWORD_ITERATIONS)
        self.assertEqual(PASSWORD_ITERATIONS, 600000)
        self.assertEqual(len(stored["salt"]), 32)
        self.assertEqual(len(stored["password_hash"]), 32)
        self.assertEqual(stored["password_hash"], hashlib.pbkdf2_hmac("sha256", b"admin123", stored["salt"], 600000))
        self.assertNotEqual(stored["password_hash"], b"admin123")
        reopened = AuthManager(self.inventory, clock=lambda: self.now)
        self.assertEqual(self.credential(), stored)
        self.assertIsNotNone(self.authenticate(reopened))
        second_inventory = Inventory(self.directory / "second.db")
        AuthManager(second_inventory)
        second = self.credential(second_inventory)
        self.assertNotEqual(second["salt"], stored["salt"])
        self.assertNotEqual(second["password_hash"], stored["password_hash"])
        exported = self.inventory.export(self.directory / "export")
        self.assertNotIn("web_users.csv", exported["files"])
        report = json.loads((self.directory / "export" / "report.json").read_text(encoding="utf-8"))
        self.assertNotIn("web_users", report)
        self.assertNotIn(stored["password_hash"].hex(), json.dumps(report))

    def test_auth_u02_password_replacement_validates_length_and_survives_restart(self):
        """AUTH-U02: invalid changes preserve the hash; a valid change replaces salt/hash."""
        original = self.credential()
        for value in (None, 42, "short", "x" * 1025):
            with self.subTest(value_type=type(value).__name__), self.assertRaises(ValueError):
                set_password(self.inventory, value)
            self.assertEqual(self.credential(), original)
        old_session = self.authenticate()
        replacement = "local-review-password"
        set_password(self.inventory, replacement)
        changed = self.credential()
        self.assertNotEqual(changed["salt"], original["salt"])
        self.assertNotEqual(changed["password_hash"], original["password_hash"])
        self.assertEqual(changed["password_hash"], hashlib.pbkdf2_hmac("sha256", replacement.encode(), changed["salt"], 600000))
        self.assertIsNone(self.authenticate(password="admin123"))
        self.assertIsNotNone(self.authenticate(password=replacement))
        restarted = AuthManager(self.inventory, clock=lambda: self.now)
        self.assertIsNone(restarted.session(old_session))
        self.assertIsNotNone(self.authenticate(restarted, password=replacement))
        self.assertEqual(self.credential(), changed)

    def test_auth_u03_idle_absolute_and_preauth_expiry_have_exact_boundaries(self):
        """AUTH-U03: idle, absolute and preauth lifetimes expire without real sleeps."""
        secret = self.authenticate()
        self.now = IDLE_SECONDS - 1
        self.assertIsNotNone(self.manager.session(secret))
        self.now = 2 * IDLE_SECONDS - 1
        self.assertIsNone(self.manager.session(secret))
        absolute = self.authenticate()
        created = self.now
        for elapsed in range(IDLE_SECONDS - 1, ABSOLUTE_SECONDS, IDLE_SECONDS - 1):
            self.now = created + elapsed
            self.assertIsNotNone(self.manager.session(absolute))
        self.now = created + ABSOLUTE_SECONDS
        self.assertIsNone(self.manager.session(absolute))
        login_secret, csrf = self.manager.begin_login()
        issued = self.now
        self.now = issued + LOGIN_SECONDS - 1
        self.assertTrue(self.manager.valid_login_token(login_secret, csrf))
        self.now = issued + LOGIN_SECONDS
        self.assertFalse(self.manager.valid_login_token(login_secret, csrf))

    def test_auth_u04_throttle_is_per_client_and_recovers_at_window_boundary(self):
        """AUTH-U04: throttling has an exact retry window and does not block another client."""
        login_secret, csrf = self.manager.begin_login()
        self.assertTrue(self.manager.valid_login_token(login_secret, csrf))
        for _ in range(FAILURE_LIMIT):
            self.assertIsNone(self.manager.authenticate("admin", "wrong", "blocked-client", login_secret))
        with self.assertRaises(LoginThrottled) as blocked:
            self.manager.authenticate("admin", "admin123", "blocked-client", login_secret)
        self.assertEqual(blocked.exception.retry_after, FAILURE_WINDOW)
        self.assertIsNotNone(self.authenticate(client="another-client"))
        self.now = FAILURE_WINDOW - 1
        with self.assertRaises(LoginThrottled) as almost:
            self.manager.authenticate("admin", "admin123", "blocked-client", login_secret)
        self.assertEqual(almost.exception.retry_after, 1)
        self.now = FAILURE_WINDOW
        self.assertIsNotNone(self.manager.authenticate("admin", "admin123", "blocked-client", login_secret))


if __name__ == "__main__":
    unittest.main()
