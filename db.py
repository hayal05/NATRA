"""Turso (libSQL) database connection + schema setup.

Every route module imports `get_db()` from here and runs SQL against it
directly, using plain `?`-placeholder queries — same style as the original
Node/Turso backend, just called from Python via the libsql-client SDK.
"""
import os
import libsql_client

TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

if not TURSO_DATABASE_URL:
    raise RuntimeError(
        "TURSO_DATABASE_URL is not set. Copy .env.example to .env and fill "
        "in your Turso credentials (or use TURSO_DATABASE_URL=file:local.db "
        "for local dev with no Turso account)."
    )

# For a purely local file DB during development, set TURSO_DATABASE_URL=file:local.db
# and omit TURSO_AUTH_TOKEN — no Turso account needed until you want to sync/deploy.
# libsql-client opens a WebSocket when the URL uses the libsql:// scheme.
# Some hosts (Render included) can fail that WebSocket handshake against
# Turso's edge ("WSServerHandshakeError: 400"). Using the https:// scheme
# instead makes the client talk to the same database over plain HTTP,
# which sidesteps that failure mode entirely — no functional difference
# for the simple (non-interactive-transaction) queries this app makes.
_connect_url = TURSO_DATABASE_URL
if _connect_url.startswith("libsql://"):
    _connect_url = "https://" + _connect_url[len("libsql://"):]

_client_kwargs = {"url": _connect_url}
if TURSO_AUTH_TOKEN and not TURSO_DATABASE_URL.startswith("file:"):
    _client_kwargs["auth_token"] = TURSO_AUTH_TOKEN

# One client (and its background event loop) for the life of the process —
# reused across requests rather than reconnecting every time.
_client = libsql_client.create_client_sync(**_client_kwargs)


class Cursor:
    """Thin sqlite3-cursor-style wrapper around a libsql_client ResultSet so
    route code can keep calling .fetchone() / .fetchall(), and rows keep
    supporting row['column'] access."""

    def __init__(self, result_set):
        self._rows = list(result_set.rows)

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


class Connection:
    """Wraps the shared libsql client so `get_db()` keeps the same
    `db.execute(sql, params)` / `db.commit()` interface routes already use."""

    def __init__(self, client):
        self._client = client

    def execute(self, sql, params=None):
        return Cursor(self._client.execute(sql, list(params) if params else []))

    def commit(self):
        # libsql-client commits each statement as it runs; nothing to flush.
        pass


def get_db():
    return Connection(_client)


def close_db(e=None):
    # Connection objects are lightweight wrappers with nothing to release;
    # the underlying libsql client is shared and closed at process exit.
    pass


def init_db(app):
    app.teardown_appcontext(close_db)

    _client.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            avatar_url TEXT DEFAULT ''
        )
    """)

    _client.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            link TEXT NOT NULL,
            description TEXT DEFAULT ''
        )
    """)

    _client.execute("""
        CREATE TABLE IF NOT EXISTS jobs (
            id TEXT PRIMARY KEY,
            employer_id TEXT NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            description TEXT DEFAULT '',
            price REAL NOT NULL,
            status TEXT NOT NULL DEFAULT 'open' CHECK (status IN ('open', 'closed')),
            created_at TEXT NOT NULL,
            expires_at TEXT NOT NULL
        )
    """)

    _client.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            professional_id TEXT NOT NULL REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected'))
        )
    """)
