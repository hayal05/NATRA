"""
NATRA® - Flask Application
Entry point for local development. Production uses gunicorn -> app:app
"""
import os
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, session, flash

from database import (
    init_db,
    get_db,
    get_dashboard_stats,
    get_recent_tasks,
    get_projects,
    seed_demo_data,
    get_all_tasks,
    get_task,
    get_projects_for_select,
    create_task,
    update_task,
    delete_task,
    cycle_task_status,
    TASK_STATUSES,
    get_project,
    create_project,
    update_project,
    delete_project,
    PROJECT_COLORS,
)
from auth import hash_password, verify_password, get_current_user, login_required


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = os.environ.get("SECRET_KEY", "dev-secret-key-change-in-production")

    init_db(app)

    @app.context_processor
    def inject_user():
        # Makes `current_user` available in every template automatically
        return {"current_user": get_current_user()}

    @app.template_filter("friendly_date")
    def friendly_date(value):
        """Turn an ISO date string into 'Due today' / 'Overdue by 2d' / 'Due Aug 9'."""
        if not value:
            return None
        d = date.fromisoformat(value)
        delta = (d - date.today()).days
        if delta == 0:
            return "Due today"
        if delta == 1:
            return "Due tomorrow"
        if delta < 0:
            return f"Overdue by {-delta}d"
        if delta <= 7:
            return f"Due in {delta}d"
        return "Due " + d.strftime("%b ") + str(d.day)

    # ---- Public routes ----

    @app.route("/")
    def landing():
        return render_template("landing.html")

    @app.route("/signup", methods=["GET", "POST"])
    def signup():
        if get_current_user():
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            error = None
            if not name:
                error = "Enter your name."
            elif not email or "@" not in email:
                error = "Enter a valid email."
            elif len(password) < 8:
                error = "Password must be at least 8 characters."

            if error is None:
                db = get_db()
                existing = db.execute("SELECT id FROM users WHERE email = ?", (email,)).fetchone()
                if existing:
                    error = "An account with that email already exists."

            if error is None:
                db = get_db()
                cur = db.execute(
                    "INSERT INTO users (name, email, password_hash) VALUES (?, ?, ?)",
                    (name, email, hash_password(password)),
                )
                user_id = cur.lastrowid
                seed_demo_data(db, user_id)  # starter projects/tasks so the dashboard isn't empty
                db.commit()
                session.clear()
                session["user_id"] = user_id
                return redirect(url_for("dashboard"))

            flash(error, "error")

        return render_template("signup.html")

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if get_current_user():
            return redirect(url_for("dashboard"))

        if request.method == "POST":
            email = request.form.get("email", "").strip().lower()
            password = request.form.get("password", "")

            db = get_db()
            user = db.execute(
                "SELECT id, name, password_hash FROM users WHERE email = ?", (email,)
            ).fetchone()

            error = None
            if user is None or not verify_password(user["password_hash"], password):
                error = "Incorrect email or password."

            if error is None:
                session.clear()
                session["user_id"] = user["id"]
                next_url = request.args.get("next")
                return redirect(next_url or url_for("dashboard"))

            flash(error, "error")

        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        return redirect(url_for("landing"))

    # ---- Protected routes ----

    @app.route("/dashboard")
    @login_required
    def dashboard():
        db = get_db()
        user = get_current_user()
        return render_template(
            "dashboard.html",
            stats=get_dashboard_stats(db, user["id"]),
            recent_tasks=get_recent_tasks(db, user["id"]),
            projects=get_projects(db, user["id"]),
        )

    # ---- Projects CRUD (Stage 6) ----

    @app.route("/projects")
    @login_required
    def projects():
        db = get_db()
        user = get_current_user()
        return render_template(
            "projects.html",
            projects=get_projects(db, user["id"]),
            colors=PROJECT_COLORS,
        )

    @app.route("/projects/create", methods=["POST"])
    @login_required
    def create_project_route():
        db = get_db()
        user = get_current_user()

        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        color = request.form.get("color", PROJECT_COLORS[0])
        if color not in PROJECT_COLORS:
            color = PROJECT_COLORS[0]

        if not name:
            flash("Give the project a name.", "error")
        else:
            create_project(db, user["id"], name, description, color)
            flash("Project created.", "success")

        return redirect(url_for("projects"))

    @app.route("/projects/<int:project_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_project(project_id):
        db = get_db()
        user = get_current_user()
        project = get_project(db, user["id"], project_id)
        if project is None:
            flash("Project not found.", "error")
            return redirect(url_for("projects"))

        if request.method == "POST":
            name = request.form.get("name", "").strip()
            description = request.form.get("description", "").strip()
            color = request.form.get("color", PROJECT_COLORS[0])
            if color not in PROJECT_COLORS:
                color = PROJECT_COLORS[0]

            if not name:
                flash("Give the project a name.", "error")
            else:
                update_project(db, user["id"], project_id, name, description, color)
                flash("Project updated.", "success")
                return redirect(url_for("projects"))

            # Re-render edit form with attempted values on error
            project = dict(project)
            project.update({"name": name, "description": description, "color": color})

        return render_template("project_edit.html", project=project, colors=PROJECT_COLORS)

    @app.route("/projects/<int:project_id>/delete", methods=["POST"])
    @login_required
    def delete_project_route(project_id):
        db = get_db()
        user = get_current_user()
        if delete_project(db, user["id"], project_id):
            flash("Project deleted (and its tasks along with it).", "success")
        else:
            flash("Project not found.", "error")
        return redirect(url_for("projects"))

    # ---- Tasks CRUD (Stage 4) ----

    @app.route("/tasks")
    @login_required
    def tasks():
        db = get_db()
        user = get_current_user()
        status_filter = request.args.get("status")
        if status_filter not in TASK_STATUSES:
            status_filter = None
        return render_template(
            "tasks.html",
            tasks=get_all_tasks(db, user["id"], status_filter),
            projects=get_projects_for_select(db, user["id"]),
            status_filter=status_filter,
        )

    @app.route("/tasks/create", methods=["POST"])
    @login_required
    def create_task_route():
        db = get_db()
        user = get_current_user()

        title = request.form.get("title", "").strip()
        description = request.form.get("description", "").strip()
        due_date = request.form.get("due_date", "").strip()
        try:
            project_id = int(request.form.get("project_id", ""))
        except ValueError:
            project_id = None

        if not title:
            flash("Give the task a title.", "error")
        elif project_id is None:
            flash("Choose a project for this task.", "error")
        else:
            new_id = create_task(db, user["id"], project_id, title, description, due_date)
            if new_id is None:
                flash("That project couldn't be found.", "error")
            else:
                flash("Task created.", "success")

        return redirect(url_for("tasks"))

    @app.route("/tasks/<int:task_id>/edit", methods=["GET", "POST"])
    @login_required
    def edit_task(task_id):
        db = get_db()
        user = get_current_user()
        task = get_task(db, user["id"], task_id)
        if task is None:
            flash("Task not found.", "error")
            return redirect(url_for("tasks"))

        if request.method == "POST":
            title = request.form.get("title", "").strip()
            description = request.form.get("description", "").strip()
            due_date = request.form.get("due_date", "").strip()
            status = request.form.get("status", "todo")
            try:
                project_id = int(request.form.get("project_id", ""))
            except ValueError:
                project_id = None

            if not title:
                flash("Give the task a title.", "error")
            elif project_id is None or status not in TASK_STATUSES:
                flash("Something about that submission looked off.", "error")
            else:
                ok = update_task(db, user["id"], task_id, project_id, title, description, due_date, status)
                if ok:
                    flash("Task updated.", "success")
                    return redirect(url_for("tasks"))
                flash("That project couldn't be found.", "error")

            # Re-render edit form with attempted values on error
            task = dict(task)
            task.update(
                {
                    "title": title,
                    "description": description,
                    "due_date": due_date,
                    "status": status,
                    "project_id": project_id or task["project_id"],
                }
            )

        return render_template(
            "task_edit.html",
            task=task,
            projects=get_projects_for_select(db, user["id"]),
            statuses=TASK_STATUSES,
        )

    @app.route("/tasks/<int:task_id>/delete", methods=["POST"])
    @login_required
    def delete_task_route(task_id):
        db = get_db()
        user = get_current_user()
        if delete_task(db, user["id"], task_id):
            flash("Task deleted.", "success")
        else:
            flash("Task not found.", "error")
        return redirect(url_for("tasks"))

    @app.route("/tasks/<int:task_id>/toggle", methods=["POST"])
    @login_required
    def toggle_task_status(task_id):
        db = get_db()
        user = get_current_user()
        new_status = cycle_task_status(db, user["id"], task_id)
        if new_status is None:
            flash("Task not found.", "error")
        return redirect(request.referrer or url_for("tasks"))

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
