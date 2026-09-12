# Deployment

Step-by-step instructions are in the [README](../README.md#deploying-to-railway).
This document covers the reasoning behind the shape.

## The shape

```
GitHub repository (one repo, one push)
        │
        ├──► Railway service "backend"    root directory: backend/
        │       Dockerfile · /health check · alembic on pre-deploy
        │
        ├──► Railway service "frontend"   root directory: frontend/
        │       Dockerfile · Next.js standalone output
        │
        └──► Railway PostgreSQL plugin
                referenced as ${{Postgres.DATABASE_URL}}
```

## Why two services, not one

The backend and the frontend are two processes with genuinely different needs.
Combining them means running a process supervisor inside one container to
pretend otherwise, and then debugging that supervisor at 2am.

They also scale differently. The marketing site is static and cacheable; the API
holds database connections and runs a background worker. Replicating the API
replicates the dispatcher too — which is safe, because `FOR UPDATE SKIP LOCKED`
handles it — but replicating static pages to get more API capacity is waste.

The cost is two services to configure and one forward reference between them:
`FRONTEND_ORIGINS` needs the frontend's URL, which does not exist until the
frontend is deployed. The README calls that out explicitly, because it is the
step most likely to be missed and the symptom (a CORS error in the browser
console, with the API working perfectly when tested with curl) is confusing.

## Why Dockerfiles rather than Nixpacks

Railway's automatic detection would probably work. An explicit build you can read
beats a build system inferring one — particularly for a uv project, where
auto-detection has historically been inconsistent, and particularly when the
failure mode is a deploy that builds successfully and then cannot start.

Both images are multi-stage and run as a non-root user. Both cache their
dependency layer separately from application code, so a code change does not
reinstall the world.

## Things that will bite you exactly once

**`NEXT_PUBLIC_*` is inlined at build time.** Next.js substitutes these during
`npm run build`, not at startup. Setting one after the build has no effect until
you redeploy. If the deployed site calls `http://localhost:8000`, this is why.

**The container must bind `0.0.0.0`, not localhost.** Railway routes to the
container's external interface. A process bound to `127.0.0.1` starts perfectly,
logs nothing unusual, and fails every health check. Both Dockerfiles set this
explicitly — the backend via `--host 0.0.0.0`, the frontend via
`HOSTNAME=0.0.0.0`.

**Migrations run as a pre-deploy command, not on startup.** With more than one
replica, startup migrations race each other. A pre-deploy command runs once, and
a failing migration becomes a failed deploy you can read rather than a crash
loop you have to diagnose.

**The health check must not touch the database.** `/health` returns
`{"status":"ok"}` and performs no I/O. A liveness probe that queries the database
restarts healthy containers during a database blip, turning a small outage into a
crash loop. `/api/v1/health/ready` is the one that probes dependencies — it is
for humans and dashboards, not for restart policies.

**Reference the database, do not paste it.** `DATABASE_URL=${{Postgres.DATABASE_URL}}`
means Railway updates it if the database moves. A pasted string does not.

## Neon instead of Railway PostgreSQL

Also supported. Two adjustments:

- Use the **pooled** endpoint for `DATABASE_URL` and the **direct** endpoint for
  `DATABASE_MIGRATION_URL`. Migrations through a transaction-mode pooler
  misbehave.
- The engine already sets `prepare_threshold=None`, which is required behind
  pgbouncer. Without it you get intermittent
  `prepared statement "_pg3_0" already exists` errors that read like a Postgres
  bug and are configuration.

Neon's free tier auto-suspends, so expect a slow first query after idle.
`pool_pre_ping=True` makes the dropped connection invisible rather than an error.

## Vercel instead of Railway for the frontend

Import the repository, set **Root Directory** to `frontend`, add the same four
variables. Vercel gives every preview deployment a unique hostname, so set
`FRONTEND_ORIGIN_REGEX` on the backend rather than trying to list them:

```
FRONTEND_ORIGIN_REGEX=^https://fluxframe-media-[a-z0-9-]+\.vercel\.app$
```

That regex permits any preview of that project — acceptable, because only you
can create one, and vastly better than `*`. `FRONTEND_ORIGINS=*` makes the app
refuse to start in production, on purpose: a service with a wildcard CORS origin
looks perfectly healthy while letting any site on the internet call your API.

## Scaling, when it is actually needed

**At 10x:** nothing structural. Add a backend replica — the outbox dispatcher is
already safe to run in several processes.

**At 100x:** move the dispatcher into its own Railway service reading the same
database. Because it reaches the rest of the system through ports, that is a
deployment change and not a rewrite — which is the entire argument for drawing
the boundaries early.

Redis, Celery and a message broker start earning their operational cost when you
need sub-second fan-out, scheduled jobs, or throughput a PostgreSQL table cannot
carry. Measure first; write the ADR when the day comes.
