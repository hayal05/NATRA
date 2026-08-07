"""Gunicorn config for the Render (production) deployment.

Why this file exists
---------------------
db.py's Turso client needs a genuine OS thread (with its own private
asyncio event loop) at the moment it's created — see the comment at the
top of db.py / app.py. app.py handles this correctly for local dev
(`python app.py`) by importing db.py before calling
`gevent.monkey.patch_all()` itself.

That ordering trick does NOT carry over to gunicorn's gevent worker
classes (GeventWorker / GeventWebSocketWorker). Those workers call
`gevent.monkey.patch_all()` from their own `init_process()` — which runs
BEFORE gunicorn imports the WSGI app (`app:app`). So by the time app.py's
top-level `import db` line runs under gunicorn, patching has already
happened, threading.Thread is already greenlet-backed, and the Turso
client's background thread breaks with "no running event loop".

`post_fork()` runs earlier than `init_process()` — right after os.fork(),
before the worker patches anything. Importing db here creates the client
against real OS threads first, exactly like the local dev path, and
avoids the double-patched state entirely.
"""


def post_fork(server, worker):
    import db  # noqa: F401  (import side effect: creates the Turso client)

    server.log.info("Turso client created in post_fork (pre-monkeypatch)")
