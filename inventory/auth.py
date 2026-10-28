"""Local password verification, login throttling, and expiring web sessions.

Credentials persist as salted PBKDF2 hashes in the workspace database. Session
secrets exist only in memory and become invalid when the server restarts.
"""

from collections import deque
import hashlib
import math
import secrets
import threading
import time


PASSWORD_ITERATIONS = 600_000
IDLE_SECONDS = 30 * 60
ABSOLUTE_SECONDS = 8 * 60 * 60
LOGIN_SECONDS = 10 * 60
FAILURE_WINDOW = 60
FAILURE_LIMIT = 5
MAX_SESSIONS = 128
MAX_LOGIN_SESSIONS = 1024
DEFAULT_USERNAME = 'admin'
_SCHEMA = '''CREATE TABLE IF NOT EXISTS web_users (
 username TEXT PRIMARY KEY NOT NULL,
 salt BLOB NOT NULL, password_hash BLOB NOT NULL, iterations INTEGER NOT NULL
)'''


class LoginThrottled(ValueError):
    def __init__(self, retry_after):
        self.retry_after = retry_after
        super().__init__('Too many sign-in attempts. Please wait and try again.')


def _password_hash(password, salt, iterations=PASSWORD_ITERATIONS):
    return hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), salt, iterations)


def _ensure_user(inventory):
    with inventory.connect() as connection:
        connection.execute(_SCHEMA)
        existing = connection.execute('SELECT 1 FROM web_users WHERE username=?', (DEFAULT_USERNAME,)).fetchone()
    if existing:
        return
    salt = secrets.token_bytes(32)
    digest = _password_hash('admin123', salt)
    with inventory.connect() as connection:
        connection.execute('INSERT OR IGNORE INTO web_users VALUES (?,?,?,?)',
                           (DEFAULT_USERNAME, salt, digest, PASSWORD_ITERATIONS))


def set_password(inventory, password):
    """Replace the local admin hash; restart the web server to revoke sessions."""
    if not isinstance(password, str) or not 8 <= len(password) <= 1024:
        raise ValueError('Password must contain between 8 and 1024 characters')
    salt = secrets.token_bytes(32)
    digest = _password_hash(password, salt)
    with inventory.connect() as connection:
        connection.execute(_SCHEMA)
        connection.execute('''INSERT INTO web_users VALUES (?,?,?,?)
            ON CONFLICT(username) DO UPDATE SET salt=excluded.salt,
                password_hash=excluded.password_hash,iterations=excluded.iterations''',
                           (DEFAULT_USERNAME, salt, digest, PASSWORD_ITERATIONS))


class AuthManager:
    def __init__(self, inventory, clock=None):
        _ensure_user(inventory)
        self.inventory = inventory
        self.clock = clock or time.monotonic
        self.lock = threading.RLock()
        self.sessions = {}
        self.login_sessions = {}
        self.failures = {}

    @staticmethod
    def _key(secret):
        if not isinstance(secret, str) or not 32 <= len(secret) <= 128:
            return None
        return hashlib.sha256(secret.encode('utf-8')).hexdigest()

    def _cleanup(self, now):
        for key, value in list(self.sessions.items()):
            if now-value['last_seen'] >= IDLE_SECONDS or now-value['created'] >= ABSOLUTE_SECONDS:
                del self.sessions[key]
        for key, value in list(self.login_sessions.items()):
            if now-value['created'] >= LOGIN_SECONDS:
                del self.login_sessions[key]
        for client, values in list(self.failures.items()):
            while values and now-values[0] >= FAILURE_WINDOW:
                values.popleft()
            if not values:
                del self.failures[client]

    def begin_login(self):
        with self.lock:
            now = self.clock()
            self._cleanup(now)
            if len(self.login_sessions) >= MAX_LOGIN_SESSIONS:
                oldest = min(self.login_sessions, key=lambda key: self.login_sessions[key]['created'])
                del self.login_sessions[oldest]
            secret, csrf = secrets.token_urlsafe(32), secrets.token_urlsafe(32)
            self.login_sessions[self._key(secret)] = dict(csrf_token=csrf, created=now)
            return secret, csrf

    def valid_login_token(self, secret, token):
        with self.lock:
            self._cleanup(self.clock())
            value = self.login_sessions.get(self._key(secret))
            return bool(value and isinstance(token, str) and secrets.compare_digest(value['csrf_token'].encode(), token.encode()))

    def authenticate(self, username, password, client, login_secret, old_session=None):
        """Return a new opaque cookie value, or None for generic bad credentials.

        The handler validates the login CSRF token immediately before this call.
        Verification holds the lock so parallel attempts cannot evade throttling.
        """
        with self.lock:
            now = self.clock()
            self._cleanup(now)
            if self._key(login_secret) not in self.login_sessions:
                return None
            failures = self.failures.setdefault(client, deque())
            if len(failures) >= FAILURE_LIMIT:
                raise LoginThrottled(max(1, math.ceil(FAILURE_WINDOW-(now-failures[0]))))
            valid_shape = isinstance(username,str) and 1 <= len(username) <= 64 and isinstance(password,str) and 1 <= len(password) <= 1024
            with self.inventory.connect() as connection:
                user = connection.execute('SELECT salt,password_hash,iterations FROM web_users WHERE username=?',
                                          (DEFAULT_USERNAME,)).fetchone()
            # An unknown username pays the same password-hash cost.
            candidate = _password_hash(password if valid_shape else '', bytes(user['salt']), user['iterations'])
            correct = (valid_shape and secrets.compare_digest(username.encode(),DEFAULT_USERNAME.encode())
                       and secrets.compare_digest(candidate,bytes(user['password_hash'])))
            if not correct:
                failures.append(now)
                return None
            self.failures.pop(client, None)
            self.login_sessions.pop(self._key(login_secret), None)
            self.sessions.pop(self._key(old_session), None)
            if len(self.sessions) >= MAX_SESSIONS:
                oldest = min(self.sessions, key=lambda key:self.sessions[key]['last_seen'])
                del self.sessions[oldest]
            secret = secrets.token_urlsafe(32)
            self.sessions[self._key(secret)] = dict(username=DEFAULT_USERNAME,csrf_token=secrets.token_urlsafe(32),created=now,last_seen=now)
            return secret

    def session(self, secret):
        with self.lock:
            now=self.clock()
            self._cleanup(now)
            value=self.sessions.get(self._key(secret))
            if value is None:
                return None
            value['last_seen']=now
            return dict(username=value['username'],csrf_token=value['csrf_token'],
                        expires_in=max(0,min(IDLE_SECONDS,int(ABSOLUTE_SECONDS-(now-value['created'])))))

    def logout(self, secret):
        with self.lock:
            self.sessions.pop(self._key(secret),None)
