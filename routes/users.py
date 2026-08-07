from flask import Blueprint, render_template, request, redirect, url_for, flash, g

from db import get_db
from auth import login_required

bp = Blueprint("users", __name__)


@bp.route("/me/settings", methods=("GET", "POST"))
@login_required
def settings():
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        avatar_url = request.form.get("avatar_url", "").strip()
        if not name:
            flash("Name can't be empty.", "error")
        else:
            db = get_db()
            db.execute(
                "UPDATE users SET name = ?, avatar_url = ? WHERE id = ?",
                (name, avatar_url, g.user["id"]),
            )
            db.commit()
            flash("Profile updated.", "success")
            return redirect(url_for("users.settings"))
    return render_template("settings.html")


@bp.route("/me/applications")
@login_required
def my_applications():
    db = get_db()
    rows = db.execute(
        """SELECT applications.status AS app_status, applications.id AS app_id,
                  jobs.id AS job_id, jobs.title, jobs.price, jobs.status AS job_status
           FROM applications
           JOIN jobs ON jobs.id = applications.job_id
           WHERE applications.professional_id = ?
           ORDER BY jobs.created_at DESC""",
        (g.user["id"],),
    ).fetchall()
    return render_template("tasks_claimed.html", rows=rows)


@bp.route("/me/balance")
@login_required
def balance():
    db = get_db()
    total = db.execute(
        """SELECT COALESCE(SUM(jobs.price), 0) AS total
           FROM applications
           JOIN jobs ON jobs.id = applications.job_id
           WHERE applications.professional_id = ? AND applications.status = 'accepted'""",
        (g.user["id"],),
    ).fetchone()["total"]

    earnings = db.execute(
        """SELECT jobs.title, jobs.price
           FROM applications
           JOIN jobs ON jobs.id = applications.job_id
           WHERE applications.professional_id = ? AND applications.status = 'accepted'
           ORDER BY jobs.created_at DESC""",
        (g.user["id"],),
    ).fetchall()

    return render_template("balance.html", total=total, earnings=earnings)
