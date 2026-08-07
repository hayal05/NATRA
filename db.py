"""Turso (libSQL) database connection + schema setup — via Turso's plain
HTTP API ("Hrana over HTTP"), not the `libsql_client` SDK.

Why not `libsql_client`: its sync client bridges to an internal asyncio
event loop running in a background thread. That bridge turned out to be
fundamentally incompatible with gevent's monkey patching in production —
not a matter of getting the import order right, we tried both and both
failed for real, in the actual Render deploy:

  - patch_all() BEFORE creating the client -> RuntimeError: no running
    event loop (deep inside libsql_client's asyncio bridge / aiohttp)
  - patch_all() AFTER creating the client  -> Error: cannot release
    un-acquired lock (ssl/threading primitives built unpatched, then
    patched out from under them)

There's no ordering that satisfies both a real background thread with its
own asyncio loop *and* gevent's cooperative scheduling of that same
thread's synchronization primitives. So instead of fighting that, this
module skips the SDK's async layer entirely and does plain synchronous
HTTP POSTs (via `requests`) against Turso's `/v2/pipeline` endpoint. No
background thread, no private event loop — just a normal blocking HTTP
call per query, which is exactly what `requests`/`urllib3` already do via
`socket`/`ssl`, the modules gevent patches cleanly and everyone relies on
patching. This is slightly less efficient per-query than a persistent
libSQL connection, which is a fine trade for a small job board; see
Turso's embedded-replica docs if this ever needs to scale past that.

For local dev with TURSO_DATABASE_URL=file:local.db (no Turso account
needed), this module uses Python's built-in `sqlite3` instead — also
plain, synchronous, no event loop, so gevent (or debug reloading, or
anything else) can't trip over it either.

Every route module imports `get_db()` from here and runs SQL against it
directly, using plain `?`-placeholder queries.
"""
import base64
import os
import sqlite3

import requests

TURSO_DATABASE_URL = os.environ.get("TURSO_DATABASE_URL")
TURSO_AUTH_TOKEN = os.environ.get("TURSO_AUTH_TOKEN")

if not TURSO_DATABASE_URL:
    raise RuntimeError(
        "TURSO_DATABASE_URL is not set. Copy .env.example to .env and fill "
        "in your Turso credentials (or use TURSO_DATABASE_URL=file:local.db "
        "for local dev with no Turso account)."
    )

_IS_LOCAL_FILE = TURSO_DATABASE_URL.startswith("file:")


class Cursor:
    """sqlite3-cursor-style wrapper (.fetchone() / .fetchall()) around a
    list of already-materialized rows. Rows are plain dicts, so
    row['column'] access works the same as it did with the old backend."""

    def __init__(self, rows):
        self._rows = rows

    def fetchone(self):
        return self._rows[0] if self._rows else None

    def fetchall(self):
        return self._rows


# ---------------------------------------------------------------------
# Local file backend — plain sqlite3, dev only
# ---------------------------------------------------------------------
class _SqliteConnection:
    def __init__(self, path):
        # check_same_thread=False: gevent/gunicorn may hand requests to
        # different real threads across the process's lifetime, and this
        # single connection is shared and only ever used one query at a
        # time per request, so it's safe here.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row

    def execute(self, sql, params=None):
        cur = self._conn.execute(sql, list(params) if params else [])
        rows = [dict(row) for row in cur.fetchall()]
        self._conn.commit()
        return Cursor(rows)

    def commit(self):
        pass  # each execute() above already commits


# ---------------------------------------------------------------------
# Turso HTTP ("Hrana over HTTP") backend — production
# ---------------------------------------------------------------------
def _to_hrana_value(v):
    if v is None:
        return {"type": "null"}
    if isinstance(v, bool):
        # SQLite has no real boolean type; store as 0/1 like sqlite3 does.
        return {"type": "integer", "value": str(int(v))}
    if isinstance(v, int):
        return {"type": "integer", "value": str(v)}
    if isinstance(v, float):
        return {"type": "float", "value": v}
    if isinstance(v, (bytes, bytearray)):
        return {"type": "blob", "base64": base64.b64encode(v).decode("ascii")}
    return {"type": "text", "value": str(v)}


def _from_hrana_value(v):
    t = v.get("type")
    if t == "null":
        return None
    if t == "integer":
        return int(v["value"])
    if t == "float":
        return float(v["value"])
    if t == "text":
        return v["value"]
    if t == "blob":
        return base64.b64decode(v["base64"])
    return v.get("value")


class _HttpConnection:
    def __init__(self, base_url, auth_token):
        self._base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers["Content-Type"] = "application/json"
        if auth_token:
            self._session.headers["Authorization"] = f"Bearer {auth_token}"

    def execute(self, sql, params=None):
        args = [_to_hrana_value(p) for p in (params or [])]
        payload = {
            "requests": [
                {"type": "execute", "stmt": {"sql": sql, "args": args}},
                {"type": "close"},
            ]
        }
        resp = self._session.post(f"{self._base_url}/v2/pipeline", json=payload, timeout=30)
        resp.raise_for_status()
        data = resp.json()

        result = data["results"][0]
        if result["type"] == "error":
            raise RuntimeError(f"Turso query failed: {result['error']['message']}")

        exec_result = result["response"]["result"]
        cols = [c["name"] for c in exec_result.get("cols", [])]
        rows = [
            dict(zip(cols, (_from_hrana_value(v) for v in row)))
            for row in exec_result.get("rows", [])
        ]
        return Cursor(rows)

    def commit(self):
        pass  # each execute() above is already its own committed request


# ---------------------------------------------------------------------
if _IS_LOCAL_FILE:
    _sqlite_path = TURSO_DATABASE_URL[len("file:"):] or "local.db"
    _shared_connection = _SqliteConnection(_sqlite_path)
else:
    # The HTTP API only speaks https:// — libsql:// (the WebSocket scheme)
    # doesn't apply here at all since we're not opening a socket connection,
    # just POSTing plain HTTP requests.
    _connect_url = TURSO_DATABASE_URL
    if _connect_url.startswith("libsql://"):
        _connect_url = "https://" + _connect_url[len("libsql://"):]
    _shared_connection = _HttpConnection(_connect_url, TURSO_AUTH_TOKEN)


def get_db():
    return _shared_connection


def close_db(e=None):
    # _shared_connection is a lightweight, shared, stateless-per-call
    # wrapper (a requests.Session or a single sqlite3 connection); nothing
    # request-scoped to release here.
    pass


def init_db(app):
    app.teardown_appcontext(close_db)

    _shared_connection.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            avatar_url TEXT DEFAULT ''
        )
    """)

    _shared_connection.execute("""
        CREATE TABLE IF NOT EXISTS portfolios (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL REFERENCES users(id),
            title TEXT NOT NULL,
            link TEXT NOT NULL,
            description TEXT DEFAULT ''
        )
    """)

    _shared_connection.execute("""
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

    _shared_connection.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id TEXT PRIMARY KEY,
            job_id TEXT NOT NULL REFERENCES jobs(id),
            professional_id TEXT NOT NULL REFERENCES users(id),
            status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'rejected'))
        )
    """)
