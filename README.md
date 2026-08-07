# NATRA — Remote Job Platform (Flask rewrite)

Same scaffold as before — one user type, portfolios, job listings, posting,
applying, accepting applicants, live updates — rebuilt as a single Flask app:
server-rendered HTML (Jinja) + CSS, no separate frontend build, real-time
updates over WebSockets via Flask-SocketIO.

## Structure
```
app.py              App factory, blueprint registration, Jinja filters
db.py               Turso (libSQL) connection + schema (users, portfolios, jobs, applications)
auth.py             Session-based login_required decorator + current-user loader
extensions.py       Shared SocketIO instance + broadcast() helper
utils.py            Date formatting / job-status helpers used in templates
routes/
  auth.py           /register, /login, /logout
  jobs.py           /, /jobs/new, /jobs/<id>, apply, accept applicant
  portfolio.py      /portfolio/<user_id>, add work sample
  users.py          /me/settings, /me/applications, /me/balance
templates/          Jinja templates (one per page) + base.html layout
static/css/         Stylesheet (the NATRA postal/dispatch look)
static/js/live.js   Socket.IO client — refreshes page content on live events
```

## Set up the database

**Option A — local file DB, no Turso account needed (fastest for dev):**
```
cd remote-job-platform-flask
cp .env.example .env
# edit .env: comment out TURSO_DATABASE_URL=libsql://... and TURSO_AUTH_TOKEN,
# uncomment TURSO_DATABASE_URL=file:local.db instead
```

**Option B — real Turso database:**
```
# install the Turso CLI: https://docs.turso.tech/cli/installation
turso auth login
turso db create remote-job-platform
turso db show remote-job-platform --url          # → TURSO_DATABASE_URL
turso db tokens create remote-job-platform        # → TURSO_AUTH_TOKEN

cd remote-job-platform-flask
cp .env.example .env
# paste both values into .env
```

Tables (`users`, `portfolios`, `jobs`, `applications`) are created automatically
on first run — see `db.py`.

## Run it locally

```
cd remote-job-platform-flask
python3 -m venv venv && source venv/bin/activate   # optional but recommended
pip install -r requirements.txt
# also set SECRET_KEY in .env to something random:
python -c "import secrets; print(secrets.token_hex(32))"

python app.py        # http://localhost:5000
```

## What's here
- **Auth**: register/login with hashed passwords (`werkzeug.security`),
  session cookie instead of JWT/localStorage — the natural fit for a
  server-rendered app. No role selection; every account can browse, post
  jobs, and apply.
- **Portfolio**: any user adds work samples (title + link + description),
  viewable by anyone at `/portfolio/<user_id>`.
- **Jobs**: any signed-in user can post a job; browsing is public.
- **Applications**: any signed-in user can apply to a job that isn't their
  own; the job's poster sees applicants and accepts one, closing the job.
- **Live updates**: Flask-SocketIO runs a WebSocket endpoint on the same
  Flask process/port as the HTTP routes. New jobs, job closures, and new/accepted
  applications are broadcast to every connected client. `static/js/live.js`
  listens for the relevant event on each page and re-fetches + swaps in the
  page's content — no manual refresh, no separate frontend build step.

## Not included (by design — this is a scaffold)
- Input validation beyond the basics, pagination, richer search/filtering
- File uploads, payments/escrow, messaging between users
- Per-user targeted WebSocket rooms (everything broadcasts to all connected
  clients — fine for a small board, add auth-aware rooms before scaling)

## Deploying to Render

Single Render **Web Service** (no separate static site needed — Flask
serves the HTML/CSS/JS itself).

- **Build Command:** `pip install -r requirements.txt`
- **Start Command:** `gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 app:app`
  *(Flask-SocketIO needs an async worker; `gevent` + `gevent-websocket` are
  already in `requirements.txt`. We use gevent rather than eventlet because
  eventlet's monkey-patching doesn't play well with Python 3.12's `logging`
  internals under gunicorn — surfaces as "RLock(s) were not greened" /
  "Working outside of request context" crashes.)*
- **Environment Variables:**

| Key | Value |
|---|---|
| `SECRET_KEY` | a random 64-char hex string (generate with the snippet above) — required, don't reuse the dev default |
| `TURSO_DATABASE_URL` | your Turso db URL (`libsql://your-db-your-org.turso.io`) |
| `TURSO_AUTH_TOKEN` | your Turso auth token |
| `PYTHON_VERSION` | `3.12.8` — pin this; some deploy targets default to a very new Python that isn't yet compatible with gevent/eventlet |

Using a real Turso database means there's no persistent-disk concern like
there was with SQLite on Render's ephemeral filesystem — the data lives on
Turso regardless of what happens to the Render instance.

### About the production web server
`python app.py` (using Flask-SocketIO's built-in `socketio.run`) is fine for
local dev but isn't meant for production. For Render, use Gunicorn with an
async worker so WebSocket connections work correctly:

```
pip install gevent gevent-websocket gunicorn
```

add all three to `requirements.txt`, then set the Render start command to:
```
gunicorn -k geventwebsocket.gunicorn.workers.GeventWebSocketWorker -w 1 app:app
```
(Keep `-w 1` — Flask-SocketIO's in-memory broadcast doesn't share state
across multiple worker processes. For more than one worker/instance you'd
need a message queue backend, e.g. Redis, which Flask-SocketIO supports via
`message_queue=`.)

## Suggested next steps
1. Add job search/filtering pagination if the board grows.
2. Scope WebSocket broadcasts with Socket.IO "rooms" so, e.g., only a job's
   employer receives `application:new` for that job.
3. Consider Turso's embedded replicas (a local file kept in sync with the
   remote database) if you need lower-latency reads at scale.
