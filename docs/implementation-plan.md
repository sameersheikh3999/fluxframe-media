# Implementation plan

Each phase has a definition of done. Phase N+1 does not start until Phase N's
gates are green and its documentation is written. Half-built phases are worse
than unbuilt ones.

---

## Phase 0 — Architecture and scaffold ✅ COMPLETE

Two runnable shells with every quality gate wired up and no business logic.

**Backend:** FastAPI app factory, settings validated at startup, structured
logging, request-id middleware, CORS from configuration, a shared error
envelope, `GET /api/v1/health` and `GET /api/v1/health/ready`, and one complete
vertical example of the dependency rule (router → composition root → service →
port → adapter).

**Frontend:** Next.js 16 App Router, TypeScript strict plus four extra
compiler checks, Tailwind v4 design tokens, a branded home page, and branded
placeholders for the other marketing routes.

**Gates:** ruff, ruff format, mypy strict, import-linter (6 contracts), pytest
(11 tests) · eslint, tsc, next build.

**Deliberately absent:** database, Alembic, Lead domain, HubSpot, outbox, demo
generator, dashboard, AI.

---

## Phase 1 — First vertical slice

The narrowest possible path from a form to a row in Postgres.

- Neon project; `dev`, `test` and `main` branches
- SQLAlchemy 2.0 async engine + psycopg 3; Alembic (synchronous) with a
  `naming_convention` on the metadata **from the first migration**
- `leads` and `lead_activities` tables
- `domain/leads/`: the `Lead` entity and its enums — no scoring yet
- `application/ports/lead_repository.py`; `UnitOfWork` gains `.leads` and
  `.activities`
- `infrastructure/database/`: engine, session, `SqlAlchemyUnitOfWork`,
  repositories, and the ORM↔domain mapper
- `LeadService.capture_lead()` with idempotency via a unique
  `idempotency_key` column
- `POST /api/v1/leads`
- The readiness probe becomes real: `SELECT 1`
- Frontend: `/book-call` form (React Hook Form + Zod), `/thank-you`
- Integration tests against a real Neon test branch

**Done when** a lead submitted at localhost:3000 appears in Neon, a double-click
creates exactly one row, and both `npm run build` and `uv run pytest` are green.

**To be explained when we get there:** `AsyncSession` lifecycle, where the
transaction begins and ends, and why lazy loading is forbidden in async
SQLAlchemy.

---

## Phase 2 — Lead scoring

- `domain/leads/scoring.py` — a pure function; rules as versioned data
- HOT / WARM / COLD, clamped 0–100, with the budget-vs-volume coherence penalty
- A persisted `score_breakdown` (JSONB) so "why 87?" is answerable
- Thorough unit tests, including the 49/50 and 79/80 boundaries
- `LeadQueryService` and `/api/v1/dashboard/leads`
- Frontend `/dashboard/leads` and `/dashboard/leads/[id]` as Server Components
- `INTERNAL_API_SECRET` guarding the dashboard endpoints
- `openapi-typescript` generating frontend types from the FastAPI schema

---

## Phase 3 — HubSpot integration

- `CrmClient` port; `infrastructure/hubspot/` client, mapper and error taxonomy
- `hubspot_bootstrap.py` creating custom properties idempotently
- `outbox_events` table; `LeadCaptured` written **in the same transaction** as
  the lead
- A manual dispatch endpoint — no background loop yet, so the mechanism is
  visible and debuggable
- Idempotent upsert keyed on email; transient vs permanent error classification
- ADRs: transactional outbox, idempotency strategy

---

## Phase 4 — Synthetic demo leads

- Coherent personas and the agreed distributions
- `/demo` page, hidden from navigation, behind the internal secret
- **Uses the same `LeadService` as the public form.** No direct inserts.
- Every record: `is_demo = true`, `source = demo_generator`, `@example.com`
- A calibration test: 1000 generated personas land near 20/45/35 HOT/WARM/COLD

---

## Phase 5 — Reliability

- Outbox dispatcher as an asyncio task in the lifespan, using
  `FOR UPDATE SKIP LOCKED`
- Exponential backoff with jitter; dead-letter status and a replay endpoint
- Rate limiting on the public endpoint
- Sync-failure visibility on the dashboard

---

## Phase 6 — AI sales brief

Only once the deterministic system works. An LLM interprets the free-text
`message` field: pain points, urgency, suggested service, a sales summary. It
does **not** touch the score. `ai_runs` records every call for evaluation.

---

## Phase 7 — Closed Won → client onboarding

---

## Phase 8 — Agency content operations

Strategy → Script → Shoot → Editing → QC → Approval → Publishing → Performance,
as explicit state machines in the domain.
