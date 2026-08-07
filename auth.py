"""
Auth helpers for NATRA®.
Session-based auth (no Flask-Login dependency) — user_id stored in the
signed session cookie, user row fetched per-request via g.user.
"""
from functools import wraps
from flask import session, redirect, url_for, g, request
from werkzeug.security import generate_password_hash, check_password_hash
from database import get_db


def hash_password(password: str) -> str:
    return generate_password_hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    return check_password_hash(password_hash, password)


def get_current_user():
    """Load the logged-in user for this request, if any. Cached on g."""
    if "user" not in g:
        user_id = session.get("user_id")
        if user_id is None:
            g.user = None
        else:
            db = get_db()
            g.user = db.execute(
                "SELECT id, name, email FROM users WHERE id = ?", (user_id,)
            ).fetchone()
    return g.user


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if get_current_user() is None:
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped
