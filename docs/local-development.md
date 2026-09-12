# Local development

No Docker, no database server, no accounts. Clone and run.

## Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12 | pinned in `backend/.python-version` |
| [uv](https://docs.astral.sh/uv/) | 0.5+ | manages the virtualenv and lockfile |
| Node | 20+ | 24 recommended |
| npm | 10+ | |

## One-time setup

```bash
cd backend
uv sync                        # creates .venv, installs from uv.lock
cp .env.example .env           # Windows: copy .env.example .env

cd ../frontend
npm install
cp .env.local.example .env.local
```

The default `DATABASE_URL` is a SQLite file. The schema is created automatically
on startup, so there is nothing else to do.

## Running

Two terminals.

```bash
# Terminal 1 — backend
cd backend
uv run uvicorn app.main:app --reload --port 8000
```

```bash
# Terminal 2 — frontend
cd frontend
npm run dev
```

| | |
|---|---|
| Marketing site | http://localhost:3000 |
| Book a call | http://localhost:3000/book-call |
| Dashboard | http://localhost:3000/dashboard/leads |
| Demo generator | http://localhost:3000/demo |
| API docs | http://localhost:8000/docs |
| Liveness | http://localhost:8000/health |
| Readiness | http://localhost:8000/api/v1/health/ready |

**Fastest way to see everything working:** open `/demo`, generate 10 leads, then
open `/dashboard/leads` and click into one.

## Switching to PostgreSQL

```bash
cd backend
# Any of these URL forms works — they are normalised to psycopg async:
#   postgres://…  postgresql://…  postgresql+psycopg://…
# In .env:
#   DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/fluxframe
uv run alembic upgrade head
```

Automatic schema creation is **SQLite only**, deliberately. PostgreSQL always
goes through Alembic, because migrations are how a schema change is reviewed,
versioned and rolled back — and `create_all` silently does nothing to an existing
table whose columns have drifted, which is exactly the failure you do not want in
production.

### Alembic commands

```bash
uv run alembic upgrade head             # apply
uv run alembic upgrade head --sql       # render the SQL WITHOUT connecting
uv run alembic downgrade -1             # roll back one
uv run alembic revision --autogenerate -m "add x"   # needs a live database
uv run alembic current                  # what is applied
```

`--sql` is worth knowing: it renders exactly what a migration will do with no
database attached. Good habit before touching production, and it is what CI uses
to check the migration still renders.

## Quality gates

Exactly what CI runs.

```bash
cd backend
uv run ruff check .
uv run ruff format --check .
uv run mypy app
uv run lint-imports
uv run pytest

cd ../frontend
npm run lint
npm run build
npm run typecheck
```

### `lint-imports` is the interesting one

It enforces the architecture. To watch it work, add this to
`backend/app/api/v1/health.py`:

```python
from app.infrastructure.clock import SystemClock
```

then run `uv run lint-imports`:

```
API must not import infrastructure directly BROKEN
-   app.api.v1.health -> app.infrastructure.clock (l.25)
```

File, target and line number. Remove the line and it passes again.

## Optional integrations

Both are genuinely optional. Without either credential the application runs
completely, and `/api/v1/health/ready` reports honestly which integrations are
configured.

### HubSpot

```bash
cd backend
HUBSPOT_ACCESS_TOKEN=pat-na1-… uv run python scripts/hubspot_bootstrap.py
```

Run this **once per portal**, before setting the token in `.env`. HubSpot custom
properties do not create themselves, and a portal without them rejects every sync
with a 400 — correctly classified as permanent, so those events dead-letter
rather than retrying forever.

Private App scopes needed: `crm.objects.contacts.write` and
`crm.schemas.contacts.write`.

With no token, syncs are marked `skipped` and everything else works.

### AI sales briefs

Set `ANTHROPIC_API_KEY` in `backend/.env`. Without it the endpoint returns a
clear 503 naming the variable, and the dashboard explains why the button will not
work. It never invents a brief.

## Poking at the running system

```bash
# Health
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/health/ready | python -m json.tool

# Capture a lead
curl -X POST http://localhost:8000/api/v1/leads \
  -H "Content-Type: application/json" \
  -H "Idempotency-Key: manual-test-001" \
  -d '{"idempotency_key":"manual-test-001","first_name":"Sam","last_name":"Tester",
       "email":"sam@example.com","company_name":"Test Co","industry":"dental",
       "monthly_revenue":"100k_500k","monthly_marketing_budget":"10k_plus",
       "content_volume":"30_plus","primary_goal":"lead_generation",
       "start_timeline":"immediately"}'

# Run the SAME command again — 200, same id, one lead. That is idempotency.

# Internal endpoints need the secret from .env
S="X-Internal-Secret: local-dev-secret"
curl -H "$S" http://localhost:8000/api/v1/dashboard/stats | python -m json.tool
curl -X POST -H "$S" -H "Content-Type: application/json" \
  -d '{"count":5,"quality":"mostly_hot"}' \
  http://localhost:8000/api/v1/demo/leads
curl -X POST -H "$S" http://localhost:8000/api/v1/admin/outbox/dispatch
```

### Inspecting the database

No `psql` required for SQLite:

```bash
cd backend
uv run python -c "
import sqlite3
db = sqlite3.connect('fluxframe-dev.db')
for row in db.execute('SELECT company_name, lead_score, lead_temperature, hubspot_sync_status FROM leads ORDER BY created_at DESC LIMIT 10'):
    print(row)
"
```

For PostgreSQL, use your provider's web SQL editor, or install a client
(`uv tool install pgcli`).

## Gotchas

**Run `npm run build` before `tsc --noEmit` on a fresh clone.** Next.js generates
route type definitions into `.next/types/`. On a clean checkout those do not
exist, and `tsc` reports missing modules for routes that are perfectly fine.

**`INTERNAL_API_SECRET` must match on both sides.** If the dashboard says the
backend rejected the secret, that is what happened. It is in both
`backend/.env` and `frontend/.env.local`.

**Port 3000 already in use.** A previous `next dev` is still running. Next will
tell you the PID: `taskkill /PID <pid> /F` on Windows, `kill <pid>` elsewhere.

**Line endings.** `.gitattributes` normalises everything to LF. You may be on
Windows; CI and Railway are Linux.

**The Python pin.** `py -3` may resolve to a newer Python. `uv run` respects
`backend/.python-version` and uses 3.12 — always go through `uv run`.

**Delete the dev database to start clean.** `rm backend/fluxframe-dev.db` and
restart; the schema is recreated on the next boot.

## Useful, not required

```bash
uv run ruff check . --fix       # auto-fix lint
uv run ruff format .            # format
uv run pytest -m unit           # the fast loop: no I/O at all
uv run pytest --lf              # re-run last failures
uv run pytest -q -k scoring     # one area
npm run dev -- --port 3001      # a different frontend port
```
