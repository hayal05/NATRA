import uuid

from flask import Blueprint, render_template, request, redirect, url_for, session, flash, g
from werkzeug.security import generate_password_hash, check_password_hash

from db import get_db

bp = Blueprint("auth", __name__)


@bp.route("/register", methods=("GET", "POST"))
def register():
    if g.user:
        return redirect(url_for("jobs.list_jobs"))

    if request.method == "POST":
        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        error = None
        if not name:
            error = "Name is required."
        elif not email:
            error = "Email is required."
        elif not password or len(password) < 8:
            error = "Password must be at least 8 characters."

        if error is None:
            db = get_db()
            existing = db.execute(
                "SELECT id FROM users WHERE email = ?", (email,)
            ).fetchone()
            if existing:
                error = "An account with that email already exists."
            else:
                user_id = str(uuid.uuid4())
                db.execute(
                    "INSERT INTO users (id, name, email, password_hash) VALUES (?, ?, ?, ?)",
                    (user_id, name, email, generate_password_hash(password)),
                )
                db.commit()
                session.clear()
                session["user_id"] = user_id
                return redirect(url_for("jobs.list_jobs"))

        flash(error, "error")

    return render_template("register.html")


@bp.route("/login", methods=("GET", "POST"))
def login():
    if g.user:
        return redirect(url_for("jobs.list_jobs"))

    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

        db = get_db()
        user = db.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()

        error = None
        if user is None or not check_password_hash(user["password_hash"], password):
            error = "Incorrect email or password."

        if error is None:
            session.clear()
            session["user_id"] = user["id"]
            next_path = request.args.get("next")
            return redirect(next_path or url_for("jobs.list_jobs"))

        flash(error, "error")

    return render_template("login.html")


@bp.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("jobs.list_jobs"))
