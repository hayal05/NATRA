"""App factory, blueprint registration, Jinja filters.

IMPORTANT: gevent.monkey.patch_all() must run before anything else is
imported — including os, dotenv, and db. This used to be reversed (db
imported first, to give the Turso client "real" OS threads before
patching), on the theory that patching-after-creation would break it with
"no running event loop". In production (Render, gunicorn +
GeventWebSocketWorker) that ordering instead produced a *different*,
confirmed crash: "Error: cannot release un-acquired lock", immediately
after patch_all() ran — because ssl/aiohttp/threading primitives had
already been constructed unpatched (via db.py's client, which pulls in
aiohttp) before patching flipped them over. gevent's own guidance is to
patch first, before importing anything that might touch ssl/socket/
threading, so that's what happens here.
"""
import gevent.monkey

gevent.monkey.patch_all()

import os
from dotenv import load_dotenv

load_dotenv()

import db



from flask import Flask, g

from db import init_db
from auth import load_logged_in_user
from extensions import socketio
from utils import format_postmark, active_status

from routes.auth import bp as auth_bp
from routes.jobs import bp as jobs_bp
from routes.portfolio import bp as portfolio_bp
from routes.users import bp as users_bp


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "change-me-before-deploying")

    init_db(app)

    app.before_request(load_logged_in_user)

    app.register_blueprint(auth_bp)
    app.register_blueprint(jobs_bp)
    app.register_blueprint(portfolio_bp)
    app.register_blueprint(users_bp)

    # Template helpers (mirror the formatting the original React UI did client-side)
    app.jinja_env.filters["postmark"] = format_postmark
    app.jinja_env.globals["active_status"] = active_status

    @app.get("/health")
    def health():
        return {"ok": True}

    socketio.init_app(app)
    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    # debug=False is deliberate: the reloader double-starts SocketIO's
    # background thread in dev, which produces duplicate broadcasts.
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
