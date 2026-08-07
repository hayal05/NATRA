"""
Database layer for NATRA®.
Uses plain sqlite3 (no ORM) to keep dependencies minimal for Render's free tier.
"""
import sqlite3
import os
from flask import g

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "remotehub.db"))


def get_db():
    """Get a request-scoped DB connection, creating one if needed."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
        g.db.execute("PRAGMA foreign_keys = ON")
    return g.db


def close_db(e=None):
    db = g.pop("db", None)
    if db is not None:
        db.close()


SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS projects (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    description TEXT,
    color TEXT NOT NULL DEFAULT '#1B4332',
    owner_id INTEGER NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (owner_id) REFERENCES users(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT NOT NULL DEFAULT 'todo',  -- 'todo' | 'in_progress' | 'done'
    project_id INTEGER NOT NULL,
    assignee_id INTEGER,
    due_date TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY (assignee_id) REFERENCES users(id) ON DELETE SET NULL
);
"""


def init_db(app):
    """Create tables if they don't exist. Call once at app startup."""
    with app.app_context():
        db = get_db()
        db.executescript(SCHEMA)
        db.commit()
    app.teardown_appcontext(close_db)


# ---- Dashboard queries (Projects & Tasks) ----
# Plain sqlite3, same as the rest of this layer — no ORM.

def get_dashboard_stats(db, user_id):
    """Aggregate counts for the four stat cards on the dashboard."""
    active_projects = db.execute(
        "SELECT COUNT(*) FROM projects WHERE owner_id = ?", (user_id,)
    ).fetchone()[0]

    open_tasks = db.execute(
        """SELECT COUNT(*) FROM tasks t
           JOIN projects p ON p.id = t.project_id
           WHERE p.owner_id = ? AND t.status != 'done'""",
        (user_id,),
    ).fetchone()[0]

    due_this_week = db.execute(
        """SELECT COUNT(*) FROM tasks t
           JOIN projects p ON p.id = t.project_id
           WHERE p.owner_id = ? AND t.status != 'done'
             AND t.due_date IS NOT NULL
             AND date(t.due_date) BETWEEN date('now') AND date('now', '+7 days')""",
        (user_id,),
    ).fetchone()[0]

    # No team/invite system yet — count distinct people already attached to
    # this user's tasks (owner + any assignees) as a stand-in.
    team_members = db.execute(
        """SELECT COUNT(DISTINCT person) FROM (
               SELECT owner_id AS person FROM projects WHERE owner_id = ?
               UNION
               SELECT t.assignee_id AS person FROM tasks t
               JOIN projects p ON p.id = t.project_id
               WHERE p.owner_id = ? AND t.assignee_id IS NOT NULL
           )""",
        (user_id, user_id),
    ).fetchone()[0]

    return {
        "active_projects": active_projects,
        "open_tasks": open_tasks,
        "due_this_week": due_this_week,
        "team_members": team_members,
    }


def get_recent_tasks(db, user_id, limit=5):
    """Most recently created tasks across all of the user's projects."""
    return db.execute(
        """SELECT t.id, t.title, t.status, t.due_date,
                  p.name AS project_name, p.color AS project_color
           FROM tasks t
           JOIN projects p ON p.id = t.project_id
           WHERE p.owner_id = ?
           ORDER BY t.created_at DESC
           LIMIT ?""",
        (user_id, limit),
    ).fetchall()


def get_projects(db, user_id):
    """Projects with a rollup of how many tasks are done vs total."""
    return db.execute(
        """SELECT p.id, p.name, p.description, p.color,
                  COUNT(t.id) AS task_count,
                  COALESCE(SUM(CASE WHEN t.status = 'done' THEN 1 ELSE 0 END), 0) AS done_count
           FROM projects p
           LEFT JOIN tasks t ON t.project_id = p.id
           WHERE p.owner_id = ?
           GROUP BY p.id
           ORDER BY p.created_at DESC""",
        (user_id,),
    ).fetchall()


# ---- Project CRUD (Stage 6) ----

PROJECT_COLORS = ("#1B4332", "#3E5C76", "#8A5A44", "#5B4B8A", "#A6402E", "#3E7CA6")


def get_project(db, user_id, project_id):
    """Fetch a single project, scoped to this user's ownership. None if not found/not owned."""
    return db.execute(
        "SELECT id, name, description, color FROM projects WHERE id = ? AND owner_id = ?",
        (project_id, user_id),
    ).fetchone()


def create_project(db, user_id, name, description, color):
    """Create a project owned by the user. Returns the new project id."""
    cur = db.execute(
        "INSERT INTO projects (name, description, color, owner_id) VALUES (?, ?, ?, ?)",
        (name, description or None, color, user_id),
    )
    db.commit()
    return cur.lastrowid


def update_project(db, user_id, project_id, name, description, color):
    """Update a project the user owns. Returns True on success, False if not found/owned."""
    if get_project(db, user_id, project_id) is None:
        return False
    db.execute(
        "UPDATE projects SET name = ?, description = ?, color = ? WHERE id = ?",
        (name, description or None, color, project_id),
    )
    db.commit()
    return True


def delete_project(db, user_id, project_id):
    """Delete a project the user owns (cascades to its tasks). Returns True if deleted."""
    if get_project(db, user_id, project_id) is None:
        return False
    db.execute("DELETE FROM projects WHERE id = ?", (project_id,))
    db.commit()
    return True


# ---- Task CRUD (Stage 4) ----

TASK_STATUSES = ("todo", "in_progress", "done")


def get_projects_for_select(db, user_id):
    """Slim (id, name) list for populating the project dropdown in forms."""
    return db.execute(
        "SELECT id, name, color FROM projects WHERE owner_id = ? ORDER BY name",
        (user_id,),
    ).fetchall()


def get_all_tasks(db, user_id, status_filter=None):
    """All of a user's tasks (via their projects), optionally filtered by status."""
    query = """SELECT t.id, t.title, t.description, t.status, t.due_date,
                      t.project_id, p.name AS project_name, p.color AS project_color
               FROM tasks t
               JOIN projects p ON p.id = t.project_id
               WHERE p.owner_id = ?"""
    params = [user_id]
    if status_filter in TASK_STATUSES:
        query += " AND t.status = ?"
        params.append(status_filter)
    query += " ORDER BY (t.due_date IS NULL), t.due_date ASC, t.created_at DESC"
    return db.execute(query, params).fetchall()


def get_task(db, user_id, task_id):
    """Fetch a single task, scoped to this user's ownership. None if not found/not owned."""
    return db.execute(
        """SELECT t.id, t.title, t.description, t.status, t.due_date, t.project_id
           FROM tasks t
           JOIN projects p ON p.id = t.project_id
           WHERE t.id = ? AND p.owner_id = ?""",
        (task_id, user_id),
    ).fetchone()


def _project_belongs_to_user(db, user_id, project_id):
    row = db.execute(
        "SELECT id FROM projects WHERE id = ? AND owner_id = ?", (project_id, user_id)
    ).fetchone()
    return row is not None


def create_task(db, user_id, project_id, title, description, due_date, status="todo"):
    """Create a task under one of the user's own projects. Returns new task id, or None if
    the project doesn't belong to the user."""
    if not _project_belongs_to_user(db, user_id, project_id):
        return None
    cur = db.execute(
        """INSERT INTO tasks (title, description, status, project_id, assignee_id, due_date)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (title, description or None, status, project_id, user_id, due_date or None),
    )
    db.commit()
    return cur.lastrowid


def update_task(db, user_id, task_id, project_id, title, description, due_date, status):
    """Update a task the user owns. Returns True on success, False if not found/owned
    or the target project isn't the user's own."""
    if get_task(db, user_id, task_id) is None:
        return False
    if not _project_belongs_to_user(db, user_id, project_id):
        return False
    db.execute(
        """UPDATE tasks SET title = ?, description = ?, project_id = ?,
               due_date = ?, status = ?
           WHERE id = ?""",
        (title, description or None, project_id, due_date or None, status, task_id),
    )
    db.commit()
    return True


def delete_task(db, user_id, task_id):
    """Delete a task the user owns. Returns True if a row was deleted."""
    if get_task(db, user_id, task_id) is None:
        return False
    db.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    db.commit()
    return True


def cycle_task_status(db, user_id, task_id):
    """Advance a task's status: todo -> in_progress -> done -> todo. Returns the new
    status, or None if the task isn't found/owned."""
    task = get_task(db, user_id, task_id)
    if task is None:
        return None
    current = task["status"]
    next_status = TASK_STATUSES[(TASK_STATUSES.index(current) + 1) % len(TASK_STATUSES)]
    db.execute("UPDATE tasks SET status = ? WHERE id = ?", (next_status, task_id))
    db.commit()
    return next_status


def seed_demo_data(db, user_id):
    """
    Give a brand-new account a starter workspace so the dashboard isn't
    empty before Projects & Tasks CRUD exists (Stage 4). Assignee is always
    the new user themselves for now — real teammates arrive with invites later.
    """
    from datetime import date, timedelta

    today = date.today()

    projects = [
        ("Website Redesign", "Refresh marketing site & landing pages", "#1B4332"),
        ("Mobile App v2", "Native app rewrite in progress", "#3E5C76"),
        ("Q3 Content Calendar", "Blog and newsletter planning", "#8A5A44"),
    ]
    project_ids = []
    for name, description, color in projects:
        cur = db.execute(
            "INSERT INTO projects (name, description, color, owner_id) VALUES (?, ?, ?, ?)",
            (name, description, color, user_id),
        )
        project_ids.append(cur.lastrowid)

    tasks = [
        (project_ids[0], "Wireframe new homepage", "todo", today + timedelta(days=2)),
        (project_ids[0], "Review typography system", "in_progress", today + timedelta(days=5)),
        (project_ids[1], "Set up CI pipeline", "done", today - timedelta(days=1)),
        (project_ids[1], "Draft onboarding flow", "todo", today + timedelta(days=9)),
        (project_ids[2], "Outline August newsletter", "in_progress", today + timedelta(days=3)),
        (project_ids[2], "Publish customer case study", "todo", None),
    ]
    for project_id, title, status, due in tasks:
        db.execute(
            """INSERT INTO tasks (title, status, project_id, assignee_id, due_date)
               VALUES (?, ?, ?, ?, ?)""",
            (title, status, project_id, user_id, due.isoformat() if due else None),
        )
