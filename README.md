# Fluxframe Media

> Content that moves businesses forward.

The operational backend of a fictional content and social media agency, built as
a **modular monolith** with explicit architectural boundaries — and built to be
explained, not just to run.

A visitor fills in a form. The lead is validated, scored by deterministic
business rules, stored, queued for CRM sync, and appears on an internal
dashboard with a full explanation of why it scored what it did. An optional AI
layer reads the prospect's own words and drafts a sales brief alongside — never
instead of — that score.

|  |  |
|---|---|
| **Frontend** | Next.js 16 · App Router · TypeScript strict · Tailwind v4 |
| **Backend** | Python 3.12 · FastAPI · Pydantic v2 · SQLAlchemy 2.0 async |
| **Database** | PostgreSQL (Railway or Neon) · Alembic migrations |
| **CRM** | HubSpot — optional, degrades cleanly |
| **AI** | Anthropic Claude — optional, degrades cleanly |
| **Deploy** | Railway — one service, one domain (two-service also supported) |

The backend is the application layer. Next.js renders and collects; it holds no
business logic, no database access and no secrets.

---

## What it actually does

**Lead capture** — a real form at `/book-call` posts to `POST /api/v1/leads`.
Double-clicking Submit produces exactly one lead, because the browser generates
an idempotency key once per form mount and the database has a unique index on it.

**Deterministic scoring** — five weighted dimensions summing to exactly 100
(budget 30, content volume 20, timeline 20, goal 15, industry fit 15), plus a
coherence penalty for a tiny budget paired with an industrial content volume.
Every point is explained and the explanation is **persisted**, so "why did this
lead score 87?" is still answerable after the rules change. No LLM anywhere near
it.

**Transactional outbox** — the lead, its audit-trail entry and the "tell HubSpot
about this" event are written in **one PostgreSQL transaction**. There is no
ordering of "commit locally" and "call a remote API" that is safe; putting the
intent in the same transaction as the data is the way out. A background
dispatcher then delivers with exponential backoff, jitter, `Retry-After`
support and dead-lettering.

**Synthetic demo leads** — `/demo` generates coherent personas that go through
the *same* `LeadService` as the public form. No bulk insert, no shortcut: a demo
batch genuinely exercises production code. Every address is `@example.com`.

**Sales dashboard** — `/dashboard/leads` with filters, pagination, the full score
breakdown, an activity timeline, UTM attribution and CRM sync state. Lifecycle
buttons are rendered from what the *domain* says is legal, so the UI cannot
offer a transition the entity would reject.

**AI sales brief** — structured output via tool use, validated field by field
before it crosses into the application. With no API key it says so clearly
rather than inventing one. Every call is recorded in `ai_runs` with latency,
tokens and cost estimate.

---

## Quick start

Runs with **no database server, no Docker, no accounts**.

```bash
# Backend — terminal 1
cd backend
uv sync
cp .env.example .env          # Windows: copy .env.example .env
uv run uvicorn app.main:app --reload --port 8000
```

```bash
# Frontend — terminal 2
cd frontend
npm install
cp .env.local.example .env.local
npm run dev
```

| | |
|---|---|
| Marketing site | http://localhost:3000 |
| Book a call | http://localhost:3000/book-call |
| Dashboard | http://localhost:3000/dashboard/leads |
| Demo generator | http://localhost:3000/demo |
| API docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

The default `DATABASE_URL` is a SQLite file and the schema is created
automatically on startup. Submit the form, then open the dashboard — the whole
pipeline works immediately. Switch `DATABASE_URL` to PostgreSQL and run
`uv run alembic upgrade head` when you want the real thing.

**Fastest way to see it working:** open `/demo`, generate 10 leads, then open
`/dashboard/leads`.

---

## Local development

### Prerequisites

| Tool | Version | Notes |
|---|---|---|
| Python | 3.12 | pinned in `backend/.python-version` |
| [uv](https://docs.astral.sh/uv/) | 0.5+ | manages the virtualenv and lockfile |
| Node | 20+ | 24 recommended |
| PostgreSQL | optional | SQLite works for local development |

`uv sync` creates `backend/.venv` and installs from `uv.lock` — no manual
`python -m venv`, no `pip install -r requirements.txt`. Run commands through
`uv run` and the right interpreter is used automatically.

### Using PostgreSQL locally

```bash
cd backend
# Railway, Neon, Supabase or a local server — any of these URL forms work:
#   postgres://…  postgresql://…  postgresql+psycopg://…
echo 'DATABASE_URL=postgresql+psycopg://user:pass@localhost:5432/fluxframe' >> .env
uv run alembic upgrade head
```

Automatic schema creation is **SQLite only**, on purpose. PostgreSQL always goes
through Alembic, because migrations are how a schema change is reviewed,
versioned and rolled back — and `create_all` silently does nothing to an
existing table whose columns have drifted.

### How the two halves talk locally

```
Browser ──POST /api/v1/leads──────────────► FastAPI :8000
  (direct; CORS allows http://localhost:3000)

Browser ──GET /dashboard/leads──► Next.js :3000 ──► FastAPI :8000
  (server-side, with X-Internal-Secret attached)
```

The public form calls the API **directly** — it needs no secret, and this proves
the API is a real public API. The dashboard and demo generator go through the
**Next.js server**, so `INTERNAL_API_SECRET` never reaches a browser.
`INTERNAL_API_SECRET` must be identical in `backend/.env` and
`frontend/.env.local`; if it is not, the dashboard shows a message saying
exactly that.

### Quality gates

Exactly what CI runs.

```bash
cd backend
uv run ruff check .            # lint
uv run ruff format --check .   # formatting
uv run mypy app                # strict type checking
uv run lint-imports            # the architecture contracts
uv run pytest                  # 227 tests

cd ../frontend
npm run lint
npm run build
npm run typecheck              # run build first on a fresh clone
```

`lint-imports` is the interesting one — it enforces the dependency rule. Add
`from app.infrastructure.clock import SystemClock` to `backend/app/api/v1/health.py`
and run it: the build fails with the exact file and line.

### Optional integrations

**HubSpot.** Create a Private App (Settings → Integrations → Private Apps) with
the `crm.objects.contacts.write` and `crm.schemas.contacts.write` scopes, then
create the custom properties once:

```bash
cd backend
HUBSPOT_ACCESS_TOKEN=pat-na1-… uv run python scripts/hubspot_bootstrap.py
```

Skipping this step means every sync fails with a 400 for an unknown property —
correctly classified as permanent, so it dead-letters rather than retrying
forever. Set the token in `.env` afterwards.

**AI briefs.** Set `ANTHROPIC_API_KEY` in `backend/.env`. Without it the endpoint
returns a clear 503 and the dashboard explains why.

---

## Deploying to Railway

**One service. One domain. One set of variables.**

Both the Next.js frontend and the FastAPI backend run in a single container,
with Next.js in front proxying `/api/v1/*` to the API beside it. Because they
share an origin, **CORS never applies** and there is no `NEXT_PUBLIC_API_URL` to
get wrong. See [ADR 0009](docs/decisions/0009-single-service-deployment.md) for
the trade-offs — and note that the two-service shape is still supported if you
want it later.

```
Internet ──► Next.js ($PORT) ──► FastAPI (127.0.0.1:8000) ──► PostgreSQL
              site + dashboard      never publicly exposed
```

### 1. Push to GitHub

```bash
git add -A
git commit -m "Fluxframe Media"
git branch -M main
git remote add origin git@github.com:<you>/fluxframe-media.git
git push -u origin main
```

### 2. Create the project and the database

Railway → **New Project → Deploy from GitHub repo**, select the repository.
Then **New → Database → Add PostgreSQL**.

### 3. Configure the service

Leave **Root Directory EMPTY** — the repo root. Railway reads `railway.toml`
and builds the root `Dockerfile`. The health check and the pre-deploy
`alembic upgrade head` come from that file; nothing to set by hand.

> If Railway ever says *"Railpack could not determine how to build the app"*,
> it means Root Directory is pointing at a folder with no `railway.toml`.

**Variables:**

| Variable | Value | Required |
|---|---|---|
| `DATABASE_URL` | `${{Postgres.DATABASE_URL}}` — *reference it, do not paste* | **yes** |
| `ENVIRONMENT` | `production` | **yes** |
| `INTERNAL_API_SECRET` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` | **yes** |
| `NEXT_PUBLIC_SITE_URL` | your public URL (fill in after step 4) | **yes** |
| `LOG_FORMAT` | `json` | recommended |
| `DASHBOARD_BASIC_AUTH_USER` | any username | recommended |
| `DASHBOARD_BASIC_AUTH_PASSWORD` | a strong password | recommended |
| `HUBSPOT_ACCESS_TOKEN` | HubSpot Private App token | optional |
| `ANTHROPIC_API_KEY` | Anthropic key, for AI briefs | optional |

Notably **not** needed: `NEXT_PUBLIC_API_URL` and `FRONTEND_ORIGINS`. Same
origin, so there is no cross-origin call to configure.

`ENVIRONMENT=production` makes the app **refuse to boot** without
`INTERNAL_API_SECRET`. That is a configuration bug worth crashing over.

### 4. Generate a domain

**Settings → Networking → Generate Domain.** Then set `NEXT_PUBLIC_SITE_URL` to
that URL and redeploy — it is baked in at build time, so it needs one rebuild to
take effect. Everything else works immediately.

### 5. Verify

```bash
curl https://<your-app>.up.railway.app/health
# {"status":"ok"}   <- proves BOTH processes are alive

curl https://<your-app>.up.railway.app/api/v1/health/ready
# database "ok"; hubspot and ai "not_configured" unless you set their keys
```

Then in a browser, on that one domain:

| Path | What you get |
|---|---|
| `/` | the marketing site |
| `/book-call` | submit the form → `/thank-you` |
| `/dashboard/leads` | your lead, scored, with the full breakdown |
| `/demo` | generate synthetic leads |
| `/docs` | the FastAPI Swagger explorer |

### 6. HubSpot (optional, after deploying)

Run `backend/scripts/hubspot_bootstrap.py` once against your portal, then set
`HUBSPOT_ACCESS_TOKEN`. Anything that dead-lettered while properties were
missing can be replayed:

```bash
curl -X POST -H "X-Internal-Secret: <secret>"   https://<your-app>.up.railway.app/api/v1/admin/outbox/<event_id>/replay
```

### Deploying as two services instead

Still fully supported, and better if you ever need to scale the halves
independently. Create two services from the same repo with **Root Directory**
set to `backend` and `frontend`; Railway then reads `backend/railway.toml` and
`frontend/railway.toml` and ignores the root one. You must then also set
`NEXT_PUBLIC_API_URL` (the backend's URL) and `FRONTEND_ORIGINS` (the
frontend's URL), because the calls become cross-origin. Details in
[docs/deployment.md](docs/deployment.md).

## Architecture

```
Browser
   │
   ▼
Next.js  ──────────────────────────────────► renders, collects, holds no logic
   │
   │ REST/JSON
   ▼
FastAPI
   ├── api/            HTTP in, HTTP out. No business rules.
   ├── application/    use cases, ports (Protocols), DTOs
   ├── domain/         the actual rules — pure Python, no framework, no I/O
   ├── infrastructure/ database, HubSpot, AI — implements the ports
   └── workers/        the outbox dispatcher loop
   │
   ▼
PostgreSQL ──────────► HubSpot, Anthropic (async, after the response)
```

Dependencies point **inward**. The domain knows nothing about anything.
Six contracts in `backend/.importlinter` make that a build failure rather than a
good intention.

Full detail: [docs/architecture.md](docs/architecture.md) ·
[docs/data-flow.md](docs/data-flow.md) ·
[ADRs](docs/decisions/)

### Repository layout

```
backend/app/
  api/              routers, middleware, error handlers, rate limiting
  schemas/          Pydantic — the wire format, and nothing else
  dependencies/     composition root: binds ports to adapters
  application/      services · ports · DTOs · demo personas
  domain/leads/     entities · enums · scoring · lifecycle · events
  infrastructure/   database · hubspot · ai · readiness probes
  workers/          outbox dispatcher and event handlers
  config/           settings, validated at startup
  observability/    structured logging and request context
backend/alembic/    migrations
backend/tests/      unit · integration · api

frontend/src/
  app/(marketing)/  public site — static Server Components
  app/(internal)/   dashboard and demo — server-rendered, secret stays server-side
  app/api/internal/ transport-only proxy for client-side admin actions
  components/       ui · marketing · leads · dashboard
  lib/              api-client (browser) · api-server (server-only)
  config/           brand, form options, validated env
  types/            the backend's response shapes
```

---

## Documentation

| | |
|---|---|
| [PROJECT_STATUS.md](PROJECT_STATUS.md) | what is built, what is not, what needs your credentials |
| [architecture.md](docs/architecture.md) | the layers, the dependency rule, and how it is enforced |
| [data-flow.md](docs/data-flow.md) | how a request travels through the system |
| [local-development.md](docs/local-development.md) | setup, commands, and the gotchas |
| [testing.md](docs/testing.md) | what is tested, how, and what is deliberately not |
| [deployment.md](docs/deployment.md) | Railway architecture in more depth |
| [implementation-plan.md](docs/implementation-plan.md) | the phases, and what remains |
| [decisions/](docs/decisions/) | ADRs — what was decided, and what was rejected |

---

## Security

- No secret is ever committed. `.gitignore` excludes every `.env` except the
  `*.example` templates, and CI fails the build if a `NEXT_PUBLIC_*` variable
  looks like a secret.
- `INTERNAL_API_SECRET` is compared in constant time and never reaches a
  browser: `lib/api-server.ts` imports `server-only`, so a Client Component
  importing it fails the build.
- Every input is validated by Pydantic at the edge and by the domain entity
  behind it — Pydantic checks the JSON is well formed, the domain checks the
  business rules, and the domain's check runs no matter who called.
- Unhandled exceptions return a generic 500 with a request id. No stack trace,
  no exception class, no table name reaches a client.
- The public endpoint is rate limited per IP.
- Production refuses to start with a wildcard CORS origin or without an internal
  secret.

---

Fluxframe Media is a fictional agency built as a portfolio project. Any case
study published here is labelled as an illustrative demo, and no testimonial on
the site describes a real client.
