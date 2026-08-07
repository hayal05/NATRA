import uuid

from flask import Blueprint, render_template, request, redirect, url_for, flash, g, abort

from db import get_db
from auth import login_required
from extensions import broadcast
from utils import now_iso, add_days_iso

bp = Blueprint("jobs", __name__)


@bp.route("/")
def list_jobs():
    db = get_db()
    q = request.args.get("q", "").strip()
    if q:
        like = f"%{q}%"
        rows = db.execute(
            """SELECT * FROM jobs
               WHERE title LIKE ? OR description LIKE ?
               ORDER BY created_at DESC""",
            (like, like),
        ).fetchall()
    else:
        rows = db.execute("SELECT * FROM jobs ORDER BY created_at DESC").fetchall()

    return render_template("jobs.html", jobs=rows, q=q, total=db.execute(
        "SELECT COUNT(*) AS n FROM jobs"
    ).fetchone()["n"])


@bp.route("/jobs/new", methods=("GET", "POST"))
@login_required
def new_job():
    if request.method == "POST":
        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        price_raw = request.form.get("price", "").strip()

        error = None
        try:
            price = float(price_raw)
            if price < 0:
                error = "Price can't be negative."
        except ValueError:
            error = "Enter a valid price."
        if not title:
            error = "Title is required."

        if error:
            flash(error, "error")
        else:
            db = get_db()
            job_id = str(uuid.uuid4())
            db.execute(
                """INSERT INTO jobs (id, employer_id, title, description, price, status, created_at, expires_at)
                   VALUES (?, ?, ?, ?, ?, 'open', ?, ?)""",
                (job_id, g.user["id"], title, description, price, now_iso(), add_days_iso(30)),
            )
            db.commit()
            job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
            broadcast("job:new", dict(job))
            return redirect(url_for("jobs.job_detail", job_id=job_id))

    return render_template("post_job.html")


@bp.route("/jobs/<job_id>")
def job_detail(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        abort(404)

    applicants = []
    is_owner = g.user and g.user["id"] == job["employer_id"]
    if is_owner:
        applicants = db.execute(
            """SELECT applications.*, users.name AS applicant_name
               FROM applications
               JOIN users ON users.id = applications.professional_id
               WHERE job_id = ?""",
            (job_id,),
        ).fetchall()

    my_application = None
    if g.user and not is_owner:
        my_application = db.execute(
            "SELECT * FROM applications WHERE job_id = ? AND professional_id = ?",
            (job_id, g.user["id"]),
        ).fetchone()

    return render_template(
        "job_detail.html",
        job=job,
        applicants=applicants,
        is_owner=is_owner,
        my_application=my_application,
    )


@bp.route("/jobs/<job_id>/apply", methods=("POST",))
@login_required
def apply(job_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        abort(404)
    if job["employer_id"] == g.user["id"]:
        flash("You can't apply to your own job.", "error")
        return redirect(url_for("jobs.job_detail", job_id=job_id))
    if job["status"] != "open":
        flash("This job is no longer open.", "error")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    existing = db.execute(
        "SELECT id FROM applications WHERE job_id = ? AND professional_id = ?",
        (job_id, g.user["id"]),
    ).fetchone()
    if existing:
        flash("You already applied to this job.", "error")
        return redirect(url_for("jobs.job_detail", job_id=job_id))

    app_id = str(uuid.uuid4())
    db.execute(
        "INSERT INTO applications (id, job_id, professional_id, status) VALUES (?, ?, ?, 'pending')",
        (app_id, job_id, g.user["id"]),
    )
    db.commit()
    broadcast("application:new", {"id": app_id, "job_id": job_id, "professional_id": g.user["id"]})
    flash("Application sent.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job_id))


@bp.route("/jobs/<job_id>/applications/<app_id>/accept", methods=("POST",))
@login_required
def accept_application(job_id, app_id):
    db = get_db()
    job = db.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
    if job is None:
        abort(404)
    if job["employer_id"] != g.user["id"]:
        abort(403)

    db.execute("UPDATE applications SET status = 'accepted' WHERE id = ? AND job_id = ?", (app_id, job_id))
    db.execute("UPDATE applications SET status = 'rejected' WHERE job_id = ? AND id != ?", (job_id, app_id))
    db.execute("UPDATE jobs SET status = 'closed' WHERE id = ?", (job_id,))
    db.commit()

    broadcast("application:accepted", {"id": app_id, "job_id": job_id})
    broadcast("job:closed", {"id": job_id})
    flash("Applicant accepted — job closed to further applications.", "success")
    return redirect(url_for("jobs.job_detail", job_id=job_id))
