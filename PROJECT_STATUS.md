# Project status

Last updated: 2026-09-12

A working, deployable application. Every phase in the original plan through
Phase 6 is implemented and verified; Phases 7 and 8 are deliberately not
started.

---

## Completed phases

### Phase 0 — Architecture and scaffold ✅

Repository structure, FastAPI application factory, settings validated at
startup, structured logging with request-id propagation, CORS from
configuration, a shared error envelope, health endpoints, and six
`import-linter` contracts enforcing the dependency rule in CI.

### Phase 1 — First vertical slice ✅

- SQLAlchemy 2.0 async + psycopg 3; Alembic (synchronous) with a naming
  convention on the metadata from the first migration
- `leads`, `lead_activities`, `outbox_events`, `ai_runs` tables
- `Lead` aggregate with business validation, `Attribution` and `ContactDetails`
  value objects
- `SqlAlchemyUnitOfWork` — one session shared by three repositories, which is
  what makes the outbox invariant structural rather than conventional
- `LeadService.capture_lead()` with idempotency
- `POST /api/v1/leads`
- Real database readiness probe replacing the Phase 0 placeholder
- `/book-call` form (React Hook Form + Zod) and `/thank-you`

### Phase 2 — Lead scoring ✅

- Pure scoring function; weights as versioned data summing to exactly 100
- HOT / WARM / COLD classification, clamped 0–100
- The budget-vs-volume coherence penalty (−10)
- `score_breakdown` persisted as JSON, so "why 87?" stays answerable
- `LeadQueryService` + read models, separate from the write path
- `/dashboard/leads` and `/dashboard/leads/[id]` as Server Components
- `INTERNAL_API_SECRET` guarding every internal endpoint

### Phase 3 — HubSpot integration ✅

- `CrmClient` port; HubSpot adapter with an anti-corruption mapper
- Idempotent upsert keyed on email (`batch/upsert` with `idProperty`)
- Transient vs permanent error classification driving the retry policy
- `outbox_events` written in the **same transaction** as the lead
- `scripts/hubspot_bootstrap.py` — idempotent custom-property creation
- Runs correctly with no token: syncs are marked `skipped`, nothing fails

### Phase 4 — Synthetic demo leads ✅

- Coherent personas: a temperature is chosen, answers are drawn from
  temperature-specific pools, and the **real scorer** must agree or the persona
  is resampled
- `/demo` page with count, quality, scenario and industry controls
- Uses the same `LeadService` as the public form — no bulk insert
- Every address `@example.com`; every lead `is_demo=true`
- Calibration test over 1000 personas asserting the distribution holds

### Phase 5 — Reliability ✅

- Background outbox worker in the FastAPI lifespan
- `FOR UPDATE SKIP LOCKED` claiming — safe with multiple replicas
- Exponential backoff with full jitter, `Retry-After` honoured, capped at 1h
- Dead-lettering after max attempts, with a replay endpoint
- Stalled-row reclamation for workers that die mid-delivery
- Per-IP rate limiting on the public endpoint
- `POST /api/v1/admin/outbox/dispatch` to force a pass

### Phase 6 — AI sales brief ✅

- `SalesBriefGenerator` port; Anthropic adapter using tool-use structured output
- Every field validated before it crosses into the application — an invented
  enum value or an empty list raises rather than propagating
- Prompts versioned in their own module (`PROMPT_VERSION` on every run)
- `ai_runs` records latency, tokens and estimated cost for every call
- The AI **never** touches the deterministic score
- Runs correctly with no key: a clear 503, never a fabricated brief

---

## Not started (deliberately)

**Phase 7 — Closed Won → client onboarding.** No `clients` or `deals` tables
exist. Speculative schema is the most expensive kind to remove, and nothing
needs them yet.

**Phase 8 — Agency content operations.** Strategy → Script → Shoot → Editing →
QC → Approval → Publishing → Performance, as state machines. The lifecycle
pattern in `domain/leads/lifecycle.py` is the template these will follow.

---

## What you must configure yourself

Nothing below blocks deployment. Each one enables a feature; without it that
feature reports itself unavailable and everything else works.

| Credential | Enables | Without it |
|---|---|---|
| `DATABASE_URL` | lead capture, dashboard, demo | API boots, health checks pass, database features return a clear 503 |
| `INTERNAL_API_SECRET` | dashboard, demo, admin | required in production — the app refuses to boot |
| `HUBSPOT_ACCESS_TOKEN` | CRM sync | syncs marked `skipped`; leads still captured |
| `ANTHROPIC_API_KEY` | AI sales briefs | endpoint returns 503 with the variable name; no brief invented |

**HubSpot needs one extra step.** Custom properties do not create themselves —
run `backend/scripts/hubspot_bootstrap.py` once per portal before enabling the
token, or every sync fails with a 400 for an unknown property.

---

## Verification performed

| Check | Result |
|---|---|
| `ruff check` / `ruff format --check` | clean, 114 files |
| `mypy app` (strict) | clean, 90 source files |
| `lint-imports` | 6 contracts kept, 0 broken |
| `pytest` | **227 passed** |
| Alembic migration | renders valid PostgreSQL DDL offline, partial index included |
| `npm run lint` / `npm run build` / `tsc --noEmit` | all clean |
| Backend boot | starts with and without a database configured |
| `GET /health` | `{"status":"ok"}` |
| `GET /api/v1/health/ready` | database `ok`, integrations honestly `not_configured` |
| `POST /api/v1/leads` | 201, scored 100/hot, breakdown persisted, UTMs stored |
| Replay same idempotency key | 200 and the same id — one lead, not two |
| Demo generator | 10 coherent leads created through the real service |
| Outbox dispatch | 13 events claimed, 10 processed, 3 skipped, 0 dead |
| All 9 frontend routes | HTTP 200 |
| Dashboard | renders real captured and generated leads |

### Not verified locally, and why

- **PostgreSQL-specific behaviour.** `FOR UPDATE SKIP LOCKED`, the partial index
  and JSONB operators are exercised by code paths the SQLite test suite runs,
  but SQLite ignores row locking. The migration was verified by rendering its
  SQL; the locking semantics need a real PostgreSQL instance, which the first
  Railway deploy provides.
- **A live HubSpot round trip.** Every response shape and failure mode is tested
  with `respx`, but no request has been made to a real portal — that needs your
  token.
- **A live Anthropic call.** Same: the adapter is fully tested against mocked
  responses, including malformed output, but needs your key for a real call.

---

## Known limitations

- **Rate limiting is per-instance.** Two Railway replicas means double the
  effective limit. A shared limiter needs Redis, which is a lot of
  infrastructure for precision a portfolio site does not need.
- **Frontend types are hand-written.** `frontend/src/types/lead.ts` mirrors the
  Pydantic schemas by hand. The mechanical fix is `openapi-typescript` generating
  them from `/openapi.json`; worth doing once the contract stops moving.
- **No end-to-end browser tests.** The API contract is covered by backend tests;
  the form's behaviour in a real browser is not. One Playwright smoke test is
  the obvious next addition.
- **Basic auth, not real authentication.** One operator, no user accounts. An
  identity system for one person is how portfolio projects die before shipping.
