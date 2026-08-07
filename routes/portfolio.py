import uuid

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort

from db import get_db
from auth import login_required

bp = Blueprint("portfolio", __name__)


@bp.route("/portfolio/<user_id>")
def view_portfolio(user_id):
    db = get_db()
    owner = db.execute("SELECT id, name FROM users WHERE id = ?", (user_id,)).fetchone()
    if owner is None:
        abort(404)
    items = db.execute(
        "SELECT * FROM portfolios WHERE user_id = ? ORDER BY rowid DESC", (user_id,)
    ).fetchall()
    is_owner = g.user and g.user["id"] == user_id
    return render_template("portfolio.html", owner=owner, items=items, is_owner=is_owner)


@bp.route("/portfolio/add", methods=("POST",))
@login_required
def add_item():
    title = request.form.get("title", "").strip()
    link = request.form.get("link", "").strip()
    description = request.form.get("description", "").strip()

    if not title or not link:
        flash("Title and link are required.", "error")
        return redirect(url_for("portfolio.view_portfolio", user_id=g.user["id"]))

    db = get_db()
    db.execute(
        "INSERT INTO portfolios (id, user_id, title, link, description) VALUES (?, ?, ?, ?, ?)",
        (str(uuid.uuid4()), g.user["id"], title, link, description),
    )
    db.commit()
    return redirect(url_for("portfolio.view_portfolio", user_id=g.user["id"]))
