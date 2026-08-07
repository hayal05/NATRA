"""Session-based auth (replaces the original JWT-in-localStorage approach).

Flask's session cookie is signed with SECRET_KEY and httpOnly by default,
which is a better fit for a server-rendered app than a bearer token a
client-side script has to remember to attach.
"""
from functools import wraps
from flask import session, redirect, url_for, request, g
from db import get_db


def load_logged_in_user():
    """Run before every request: attach the current user (or None) to g."""
    user_id = session.get("user_id")
    if user_id is None:
        g.user = None
    else:
        db = get_db()
        g.user = db.execute(
            "SELECT id, name, email, avatar_url FROM users WHERE id = ?",
            (user_id,),
        ).fetchone()


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            return redirect(url_for("auth.login", next=request.path))
        return view(*args, **kwargs)
    return wrapped
