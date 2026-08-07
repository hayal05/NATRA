# NATRA® — Stage 6

## Run locally
```bash
pip install -r requirements.txt
python app.py
```
Visit http://localhost:5000 — the SQLite DB (`remotehub.db`) is created automatically on first run.
Delete `remotehub.db` if you want a completely fresh database (new schema, no old demo data).

## What's in this stage
- Everything from Stages 1–5 (landing page, design system, auth, protected dashboard,
  full Tasks CRUD, deploy config)
- **Projects CRUD** — `/projects` lists all of a user's projects with a create form
  (name, description, color) and a rollup of tasks done/total per project;
  `/projects/<id>/edit` and `/projects/<id>/delete` round it out. Same ownership-guard
  pattern as Tasks: `get_project` scopes every read/write to `owner_id`, so one user can't
  touch another's projects even by guessing an ID.
- Deleting a project cascades to its tasks (`ON DELETE CASCADE` in the schema) — the
  delete confirm prompt says so.
- **`Procfile`** — `web: gunicorn app:app`, the process Render (or Heroku) runs in production
- **`render.yaml`** — one-click Render Blueprint: web service, build/start commands, and an
  auto-generated `SECRET_KEY`
- **`.env.example`** — documents the env vars the app reads (`SECRET_KEY`, optional
  `DATABASE_PATH`)
- **`.gitignore`** — keeps `__pycache__/`, local venvs, `*.db`, and `.env` out of version control

## Deploying to Render
1. Push this repo to GitHub.
2. In Render: **New → Blueprint**, point it at the repo — `render.yaml` configures the
   service automatically. (Or **New → Web Service** manually: build command
   `pip install -r requirements.txt`, start command `gunicorn app:app`.)
3. Set `SECRET_KEY` if you didn't use the Blueprint (Render can generate one for you).
4. Deploy. First load will run `init_db` and create a fresh `remotehub.db`.

**On persistence:** Render's free web services don't support attached disks, so
`remotehub.db` lives on ephemeral storage — every restart or redeploy wipes it back to
empty. That's fine for demoing, but for anything you want to keep, either add a paid
instance with a persistent disk (mount it and point `DATABASE_PATH` at the mounted path)
or move to Render's managed Postgres later. Double-check current plan names/limits on
Render's pricing page before you commit — they've changed more than once recently.

## Why plain sqlite3 instead of an ORM
Keeps dependencies to just Flask + gunicorn — no compiled packages to worry about
on Render's free tier.

## A note on the seed data
Tasks are always assigned to the account's own owner for now — there's no team/invite
system yet, so `assignee_id` never points at anyone else. The "Team Members" stat is a
placeholder that will become meaningful once invites exist.

## Stage 6 recap — Projects CRUD
- `projects.html`: inline "new project" form (name, color, optional description) and a
  list of existing projects with a done/total task rollup
- `project_edit.html`: full edit form (name, description, color)
- Delete with a confirm prompt that warns tasks go with it; all project routes are
  scoped to the logged-in user's own data (`get_project` guards against editing/deleting
  someone else's project even if they guess an ID)
- Color is chosen from a fixed palette (`PROJECT_COLORS` in `database.py`) rather than a
  free-form picker, to keep the dot/swatch colors consistent with the rest of the UI

## Stage 4 recap — Tasks CRUD
- `tasks.html`: inline "add a task" form, status filter tabs (All / To do / In progress / Done),
  and a task list with click-to-advance status dots
- `task_edit.html`: full edit form (title, description, project, due date, status)
- Delete with a confirm prompt; all task routes are scoped to the logged-in user's own
  projects (`get_task` / `_project_belongs_to_user` guard against editing/deleting
  someone else's data even if they guess an ID)

## Next stages
- Team invites (real `assignee_id` values, makes the "Team Members" stat meaningful)
