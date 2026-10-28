"""Local inventory UI, guarded CSV imports, and retained correction comparisons."""
from __future__ import annotations

import ipaddress
import json
import secrets
import tempfile
import threading
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from .pipeline import Inventory, PipelineError
from .showcase import build_showcase
from .auth import ABSOLUTE_SECONDS, LOGIN_SECONDS, AuthManager, LoginThrottled

_ROOT = Path(__file__).resolve().parents[1]
_STATIC = Path(__file__).with_name("static")
MAX_CSV_BYTES = 10 * 1024 * 1024
MAX_REQUEST_BYTES = 32 * 1024 * 1024
_ASSETS = {"/": ("index.html", "text/html; charset=utf-8"),
           "/index.html": ("index.html", "text/html; charset=utf-8"),
           "/style.css": ("style.css", "text/css; charset=utf-8"),
           "/app.js": ("app.js", "text/javascript; charset=utf-8")}
_SAMPLES = {name + ".csv" for name in ("movements", "corrections", "review_correction", "items", "locations")}
_DEMOS = {name + ".csv" for name in ("movements", "items", "locations", "demo_quality_examples",
                                   "demo_cancel_transfer", "demo_restore_transfer", "demo_expected_schema_failure")}
_PUBLIC = {"/login": ("login.html", "text/html; charset=utf-8"),
           "/login.css": ("login.css", "text/css; charset=utf-8"),
           "/login.js": ("login.js", "text/javascript; charset=utf-8"),
           "/style.css": ("style.css", "text/css; charset=utf-8")}


def _validate_loopback(host):
    if host == "localhost":
        return
    try:
        address = ipaddress.ip_address(host)
    except ValueError as error:
        raise ValueError("Dashboard host must be localhost or a loopback IP address") from error
    if not address.is_loopback or address.version != 4:
        raise ValueError("Use localhost or an IPv4 loopback address such as 127.0.0.1")


def _csv_input(payload, filename_key, text_key):
    name, content = payload.get(filename_key), payload.get(text_key)
    if not isinstance(name, str) or not name.lower().endswith(".csv") or not 1 <= len(name) <= 128:
        raise ValueError(f"{filename_key}: choose a CSV filename of at most 128 characters")
    if name in {".", ".."} or any(c in name for c in "/\\") or any(ord(c) < 32 for c in name):
        raise ValueError(f"{filename_key}: must be a filename without directories or control characters")
    if not isinstance(content, str):
        raise ValueError(f"{text_key}: must contain CSV text")
    if len(content.encode("utf-8")) > MAX_CSV_BYTES:
        raise ValueError("CSV files may be at most 10 MiB each; use the CLI for larger batches")
    return name, content


def create_server(db_path, host="127.0.0.1", port=8765):
    """Create a bound local server. Port zero is supported for isolated tests."""
    _validate_loopback(host)
    if isinstance(port, bool) or not isinstance(port, int) or not 0 <= port <= 65535:
        raise ValueError("Dashboard port must be between 0 and 65535")
    database = Path(db_path).expanduser().resolve()
    if not database.is_file():
        raise FileNotFoundError("Database does not exist; initialize and ingest data first")
    inventory = Inventory(database)
    auth = AuthManager(inventory)
    import_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        server_version = "InventoryDashboard/1.1"

        def setup(self):
            super().setup()
            self.connection.settimeout(30)

        def _hosts(self):
            return {f"127.0.0.1:{self.server.server_port}", f"localhost:{self.server.server_port}", f"{host}:{self.server.server_port}"}

        def _respond(self, status, body, content_type, filename=None, headers=()):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Content-Security-Policy", "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'")
            if filename:
                self.send_header("Content-Disposition", f'attachment; filename="{filename}"')
            for key, value in headers:
                self.send_header(key, value)
            self.end_headers()
            if self.command != "HEAD":
                self.wfile.write(body)

        def _json(self, status, data, headers=()):
            self._respond(status, json.dumps(data, ensure_ascii=False, allow_nan=False).encode("utf-8"), "application/json; charset=utf-8", headers=headers)

        def _cookie(self, name):
            try:
                cookies = SimpleCookie()
                cookies.load(self.headers.get("Cookie", ""))
                return cookies[name].value if name in cookies else None
            except (CookieError, ValueError):
                return None

        def _cookie_header(self, name, value, seconds):
            return ("Set-Cookie", f"{name}={value}; Path=/; HttpOnly; SameSite=Strict; Max-Age={seconds}")

        def _redirect(self, destination):
            self._respond(302, b"", "text/plain; charset=utf-8", headers=(("Location", destination),))

        def _session(self):
            return auth.session(self._cookie(self.server.auth_cookie_name))

        def _csrf_valid(self, expected):
            return secrets.compare_digest(self.headers.get("X-Stockline-Token", "").encode("utf-8"), expected.encode("utf-8"))

        def _valid_host(self):
            if self.headers.get("Host", "").lower() not in self._hosts():
                self._json(403, {"error": "Local dashboard host required"})
                return False
            return True

        def do_GET(self):
            if not self._valid_host():
                return
            request = urlsplit(self.path)
            try:
                session = self._session()
                if request.path == "/api/login-session":
                    secret, token = auth.begin_login()
                    self._json(200, {"csrf_token": token}, headers=(self._cookie_header(self.server.login_cookie_name, secret, LOGIN_SECONDS),))
                    return
                if request.path in _PUBLIC:
                    if request.path == "/login" and session:
                        self._redirect("/")
                    else:
                        filename, content_type = _PUBLIC[request.path]
                        self._respond(200, (_STATIC / filename).read_bytes(), content_type)
                    return
                if not session:
                    if request.path.startswith("/api/"):
                        self._json(401, {"error": "Sign in to continue"})
                    else:
                        self._redirect("/login")
                    return
                if request.path == "/api/session":
                    self._json(200, session)
                elif request.path == "/api/report":
                    self._json(200, inventory.report())
                elif request.path == "/api/catalogs":
                    self._json(200, inventory.catalogs())
                elif request.path == "/api/showcase":
                    self._json(200, build_showcase())
                elif request.path == "/api/changes":
                    query = parse_qs(request.query, keep_blank_values=True)
                    self._json(200, inventory.changes(run_id=query.get("run_id", [None])[0] or None,
                                                     limit=int(query.get("limit", ["100"])[0]),
                                                     offset=int(query.get("offset", ["0"])[0])))
                elif request.path.startswith("/api/sample/"):
                    filename = request.path.removeprefix("/api/sample/")
                    if filename not in _SAMPLES:
                        self._json(404, {"error": "Sample file not found"})
                    else:
                        self._respond(200, (_ROOT / "data" / "sample" / filename).read_bytes(), "text/csv; charset=utf-8", filename)
                elif request.path.startswith("/api/demo/"):
                    filename = request.path.removeprefix("/api/demo/")
                    if filename not in _DEMOS:
                        self._json(404, {"error": "Demo file not found"})
                    else:
                        self._respond(200, (_ROOT / "data" / "demo" / filename).read_bytes(), "text/csv; charset=utf-8", filename)
                elif request.path in _ASSETS:
                    filename, content_type = _ASSETS[request.path]
                    self._respond(200, (_STATIC / filename).read_bytes(), content_type)
                else:
                    self._json(404, {"error": "Not found"})
            except ValueError as error:
                self._json(400, {"error": str(error)})
            except Exception as error:
                self.log_error("read failed: %s", type(error).__name__)
                self._json(500, {"error": "Could not read local data; check the server log"})

        def do_HEAD(self):
            self.do_GET()

        def do_POST(self):
            if not self._valid_host():
                return
            if self.headers.get("Origin", "") not in {"http://" + value for value in self._hosts()}:
                self._json(403, {"error": "Requests require this dashboard's own origin"})
                return
            path = urlsplit(self.path).path
            session = None
            if path == "/api/login":
                login_secret = self._cookie(self.server.login_cookie_name)
                if not auth.valid_login_token(login_secret, self.headers.get("X-Stockline-Token", "")):
                    self._json(403, {"error": "Sign-in session expired; refresh the sign-in page"})
                    return
            else:
                session = self._session()
                if not session:
                    self._json(401, {"error": "Sign in to continue"})
                    return
            if session and not self._csrf_valid(session["csrf_token"]):
                self._json(403, {"error": "Session token missing or expired; refresh the dashboard"})
                return
            if path not in {"/api/import", "/api/catalogs", "/api/login", "/api/logout"}:
                self._json(404, {"error": "Not found"})
                return
            if self.headers.get("Content-Type", "").split(";", 1)[0].lower() != "application/json":
                self._json(415, {"error": "Expected application/json"})
                return
            try:
                length = int(self.headers.get("Content-Length", "-1"))
            except ValueError:
                length = -1
            if length < 0:
                self._json(411, {"error": "Content-Length is required"})
                return
            limit = 8192 if path in {"/api/login", "/api/logout"} else MAX_REQUEST_BYTES
            if length > limit:
                self._json(413, {"error": "Request is too large; use the CLI for larger batches"})
                return
            try:
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                if not isinstance(payload, dict):
                    raise ValueError("Expected a JSON object")
                if path == "/api/login":
                    secret = auth.authenticate(payload.get("username"), payload.get("password"),
                                               self.client_address[0], login_secret,
                                               self._cookie(self.server.auth_cookie_name))
                    if secret is None:
                        self._json(401, {"error": "Invalid username or password"})
                    else:
                        self._json(200, {"username": "admin"}, headers=(
                            self._cookie_header(self.server.auth_cookie_name, secret, ABSOLUTE_SECONDS),
                            self._cookie_header(self.server.login_cookie_name, "", 0)))
                    return
                if path == "/api/logout":
                    auth.logout(self._cookie(self.server.auth_cookie_name))
                    self._json(200, {"signed_out": True}, headers=(self._cookie_header(self.server.auth_cookie_name, "", 0),))
                    return
                if path == "/api/import":
                    filename, content = _csv_input(payload, "filename", "csv_text")
                    through = payload.get("through")
                    through = None if through in (None, "") else through
                    if through is not None and not isinstance(through, str):
                        raise ValueError("through must be an ISO business date")
                else:
                    items_name, items = _csv_input(payload, "items_filename", "items_csv")
                    locations_name, locations = _csv_input(payload, "locations_filename", "locations_csv")
                if not import_lock.acquire(blocking=False):
                    self._json(409, {"error": "Another import is running; wait for it to finish and retry"})
                    return
                try:
                    with tempfile.TemporaryDirectory(prefix="stockline-import-") as temporary:
                        directory = Path(temporary)
                        if path == "/api/import":
                            source = directory / filename
                            source.write_text(content, encoding="utf-8", newline="")
                            run = inventory.ingest(source, through=through)
                            self._json(200, {"run": run, "impact": inventory.changes(run["run_id"])})
                        else:
                            (directory / "items").mkdir()
                            (directory / "locations").mkdir()
                            item_path, location_path = directory / "items" / items_name, directory / "locations" / locations_name
                            item_path.write_text(items, encoding="utf-8", newline="")
                            location_path.write_text(locations, encoding="utf-8", newline="")
                            self._json(200, inventory.load_catalogs(item_path, location_path))
                finally:
                    import_lock.release()
            except LoginThrottled as error:
                self._json(429, {"error": str(error)}, headers=(("Retry-After", str(error.retry_after)),))
            except (ValueError, UnicodeError, PipelineError) as error:
                self._json(400, {"error": str(error)})
            except Exception as error:
                self.log_error("import failed: %s", type(error).__name__)
                self._json(500, {"error": "Local import failed; inspect the run audit and server log"})

        def _not_allowed(self):
            self._json(405, {"error": "This method is not supported"})

        do_PUT = do_PATCH = do_DELETE = _not_allowed

    server = ThreadingHTTPServer((host, port), Handler)
    server.auth = auth
    server.auth_cookie_name = f"StockInventoSession_{server.server_port}"
    server.login_cookie_name = f"StockInventoLogin_{server.server_port}"
    server.daemon_threads = True
    return server


def serve(db_path, host="127.0.0.1", port=8765):
    if isinstance(port, bool) or not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("Dashboard port must be between 1 and 65535")
    with create_server(db_path, host=host, port=port) as server:
        print(f"Inventory dashboard: http://{host}:{server.server_port} (local imports enabled; Ctrl+C to stop)", flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass

