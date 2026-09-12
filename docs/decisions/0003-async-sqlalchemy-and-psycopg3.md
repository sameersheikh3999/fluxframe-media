# 0003 — Async SQLAlchemy 2.x with psycopg 3, and synchronous Alembic

**Status:** Accepted · 2026-09-12
**Implemented:** Phase 1 — this ADR records the decision ahead of the code.

## Context

FastAPI supports both synchronous and asynchronous handlers. The choice affects
the database engine, the session type, the shape of every test fixture and the
Alembic setup, and it is expensive to reverse once there are fifty call sites.

## Decision

Asynchronous SQLAlchemy 2.x on the request path, using the psycopg 3 driver.
Alembic migrations run synchronously.

## Why — stated honestly

**Synchronous SQLAlchemy would be entirely adequate for the traffic this
application will ever see.** A lead capture form produces tens of requests per
day. FastAPI runs a plain `def` endpoint in a worker thread perfectly
competently, and sync SQLAlchemy is easier to reason about, easier to test and
free of async-session sharp edges.

We are not choosing async for performance. We are choosing it because of what
this backend is going to contain:

- **Phase 3** — HubSpot calls over httpx
- **Phase 5** — an outbox dispatcher fanning out concurrent outbound HTTP while
  reading and writing the database
- **Phase 6** — LLM calls, which are the slowest I/O in the system by an order
  of magnitude

Those are genuinely concurrency-shaped workloads. Running a synchronous database
layer underneath them means bridging threadpools into an event loop at every
boundary, which is more total complexity than adopting async now.

This reasoning is recorded plainly because "we chose async for the background
processing we know is coming, not for throughput we do not have" is both true
and a better answer than pretending Phase 1 needs it.

## Why psycopg 3 specifically

psycopg 3 provides synchronous and asynchronous drivers from one package behind
one URL scheme. `postgresql+psycopg://…` works with both `create_async_engine`
and `create_engine`.

The practical payoff: Alembic can stay fully synchronous — a simpler `env.py`,
no async migration template — against the identical `DATABASE_URL`. One
dependency, both modes, and migrations that are easier to reason about at
3am than the async template.

asyncpg is the faster driver on paper. It cannot do this, and raw driver
throughput is not remotely the constraint here.

## What tradeoff are we accepting?

- Async session sharp edges. Lazy loading does not work; relationships must be
  loaded explicitly with `selectinload`. Getting this wrong produces a
  `MissingGreenlet` error that reads like a library bug and is not.
- Async test fixtures, which are fussier than synchronous ones.
- A genuine obligation to understand `AsyncSession` lifecycle and transaction
  boundaries rather than copying a snippet. That explanation is owed at the
  start of Phase 1.

## Neon-specific consequences (Phase 1)

- Runtime uses Neon's **pooled** endpoint; Alembic uses the **direct** endpoint.
  Migrations through pgbouncer are a bad time.
- The pooler runs in transaction mode, so psycopg's prepared-statement cache
  must be disabled (`prepare_threshold=None`). Skipping this yields intermittent
  `prepared statement "_pg3_0" already exists` errors that look like a Postgres
  bug and are configuration.
- Neon's free tier auto-suspends, so `pool_pre_ping=True` and an expectation of
  a slow first query after idle.

## What changes at 10x / 100x?

At 10x, nothing. At 100x, the connection pool becomes the thing to tune, and the
dispatcher moves to its own process with its own pool. Neither requires
revisiting this decision.
