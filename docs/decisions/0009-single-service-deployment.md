# 0009 — Single-service deployment, with Next.js in front

**Status:** Accepted · 2026-09-12
**Supersedes:** the deployment shape described in
[0005](0005-frontend-backend-boundary.md) — *not* its architectural reasoning,
which still holds.
**Implemented:** `Dockerfile`, `railway.toml`, `scripts/start-combined.sh`,
`frontend/next.config.ts`

## Context

The original deployment ran two Railway services from one repository: one for
the FastAPI backend, one for the Next.js frontend. That is the textbook shape
and it works.

In practice it produced friction that the textbook does not mention:

- Two services to configure, each with its own Root Directory and variables.
- A **circular setup problem**: the backend needs `FRONTEND_ORIGINS`, which is
  the frontend's URL, which does not exist until the frontend is deployed. So
  the first deploy is always wrong and has to be fixed and redeployed.
- `NEXT_PUBLIC_API_URL` is baked in at **build** time. Setting it after a build
  silently has no effect, and the symptom — a production site calling
  `http://localhost:8000` — gives no clue why.
- Every browser request to the API is cross-origin, so CORS has to be correct
  in a place separate from where the error appears.

## Decision

Package both processes into **one container, on one Railway service, behind one
domain**, with **Next.js as the front door**:

```
Internet ──► Next.js (binds $PORT)
               ├── serves the site and the dashboard
               └── rewrites /api/v1/*, /docs, /openapi.json, /health
                      │
                      ▼
                   FastAPI (127.0.0.1:8000, never publicly exposed)
                      │
                      ▼
                   PostgreSQL
```

The two-service Dockerfiles in `backend/` and `frontend/` are kept and still
work. Switching back is a Railway settings change, not a code change.

## Why Next.js in front rather than FastAPI

FastAPI could have served the built frontend and proxied nothing. It would then
be responsible for serving every `.js`, `.woff2` and image, which it has no
business doing — and Next.js needs a live Node process anyway for Server
Components, the dashboard's `force-dynamic` rendering and the `/api/internal/*`
route handler. Static export is not an option without gutting the architecture.

Next.js is already an HTTP server that does static assets, streaming SSR and
rewrites well. Handing it the front door costs one config block.

## What this buys

**CORS disappears entirely.** The browser and the API share an origin. No
preflight, no `FRONTEND_ORIGINS` to keep in sync, no "works in curl, blocked in
the browser".

**`NEXT_PUBLIC_API_URL` is no longer needed.** Left unset, `env.apiUrl` is an
empty string and the browser posts to `/api/v1/leads` — a relative path. The
most common Railway mistake is simply not reachable.

**Server-side rendering skips a hop.** `serverApiUrl()` returns
`http://127.0.0.1:8000`, so a dashboard Server Component talks straight to the
FastAPI process beside it rather than going out through the load balancer and
back in.

**One meaningful health check.** `/health` is proxied through to FastAPI, so a
single check proves *both* processes are alive. A check that only proved
Next.js was up would report healthy while every API call 502'd.

**One domain, one certificate, one set of variables, no circular setup.**

## What this costs — stated plainly

**Two processes in one container.** They cannot be scaled independently. If the
API needs more capacity you also replicate the static site, which is waste.

**Shared fate.** `scripts/start-combined.sh` uses `wait -n`, so if either
process exits the container exits and Railway restarts it. That is deliberate —
the alternative is a live frontend 502-ing every API call while the platform
reports the service as healthy, which is the worst failure mode available
because nothing alerts and nothing restarts. But it does mean a backend crash
takes the marketing site down with it.

**A larger image.** Python plus Node plus both dependency trees. Mitigated by
Next.js `output: "standalone"`, which traces only the modules actually imported.

**Less honest separation.** The *architecture* is unchanged — the frontend still
holds no business logic and no secrets — but the deployment no longer
demonstrates that they are independently deployable.

## What simpler alternative exists?

Two services, which is what this replaces. It is simpler per-service and more
complex per-project. For a portfolio application with one operator, one domain
and one bill, the trade favours one service.

## What changes at 10x?

Nothing. One container handles far more than a lead form produces.

## What changes at 100x?

Split them. The code already supports it: set `NEXT_PUBLIC_API_URL` to the
backend's public URL, point Root Directory at `backend` and `frontend`, and the
same source deploys as two services. The rewrites simply stop firing.

That reversibility is the reason `env.apiUrl` is *allowed* to be empty rather
than being deleted outright — one value selects the deployment shape.

## How do I verify it?

Locally, without Docker:

```bash
# terminal 1 — backend on a private port
cd backend && uv run uvicorn app.main:app --host 127.0.0.1 --port 8010

# terminal 2 — frontend proxying to it
cd frontend && npm run build
BACKEND_INTERNAL_URL=http://127.0.0.1:8010 PORT=3100 npm run start
```

Then everything should answer on **one origin**:

```bash
curl http://localhost:3100/health            # {"status":"ok"}  (proxied)
curl http://localhost:3100/api/v1/health     # 200              (proxied)
curl http://localhost:3100/docs              # 200              (proxied)
curl http://localhost:3100/                  # the marketing site
```

And no absolute API host should appear in the built bundle:

```bash
grep -r "api/v1/leads" frontend/.next/static/chunks/ | grep -o 'http[^"]*'
# no output = the browser is using a relative path
```
