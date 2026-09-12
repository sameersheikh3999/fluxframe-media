# Data flow

## What exists today: `GET /api/v1/health`

This is the only request path in Phase 0. It carries no business logic, which
makes it a clean illustration of the layering.

```
curl http://localhost:8000/api/v1/health
   │
   ▼
[middleware] app/api/middleware.py
   RequestContextMiddleware
   · takes X-Request-ID from the caller, or mints one
   · binds it to a ContextVar and to the structlog context
   · starts a timer
   │
   ▼
[router] app/api/v1/health.py  ──  def health(service: SystemServiceDep)
   │
   │  SystemServiceDep is Annotated[SystemService, Depends(get_system_service)].
   │  FastAPI resolves that provider before the function body runs.
   │
   ▼
[composition root] app/dependencies/services.py  ──  get_system_service(...)
   · resolves get_settings()          → Settings
   · resolves get_clock()             → SystemClock  (as a Clock)
   · resolves get_readiness_probes()  → [NotConfiguredProbe]  (as ReadinessProbe)
   · constructs SystemService(clock=..., probes=..., service_name=..., ...)
   │
   ▼
[use case] app/application/services/system_service.py  ──  service.health()
   · calls self._clock.now()   ← the port, not datetime.now()
   · returns HealthReport, a dataclass from app/application/dto/system.py
   │
   ▼
[router] maps HealthReport → HealthResponse (app/schemas/health.py)
   │
   ▼
[middleware] logs one structured line, sets X-Request-ID on the response
   │
   ▼
200  {"status":"ok","service":"Fluxframe Media API","version":"0.1.0",
      "environment":"local","checked_at":"2026-09-12T…Z"}
```

Three objects represent "the health of the service", and that is deliberate:

| Object | Layer | Purpose |
|---|---|---|
| `HealthReport` | application (dataclass) | what the use case returns |
| `HealthResponse` | schemas (Pydantic) | what the JSON looks like |
| — | domain | nothing: service health is not a business concept |

They look nearly identical today. They diverge the first time the API needs a
field the use case does not have, or the use case gains one the API must not
expose. Keeping them separate now costs a six-line mapping; merging them costs
a refactor later.

## What Phase 1 will look like

Recorded here so the shape is agreed before it is built. **Not implemented.**

```
/book-call form  (Next.js client component)
   │  validates with Zod for UX only
   │  attaches an idempotency_key generated once per form mount
   │  attaches utm_* / referrer / landing_page
   ▼
POST http://localhost:8000/api/v1/leads          ← direct, browser to FastAPI
   │
   ▼ app/api/v1/leads.py
   Pydantic LeadCreateRequest validates TRANSPORT: types, enum membership, email
   → builds CaptureLeadCommand (an application DTO)
   │
   ▼ LeadService.capture_lead(command)
   1. uow.leads.find_by_idempotency_key(key) → if found, return it (200, no new write)
   2. Lead.capture(...)            domain constructs the aggregate
   3. score_lead(lead)             pure domain function              (Phase 2)
   4. lead.apply_score(result)
   5. uow.leads.add(lead)
   6. uow.activities.add(...)
   7. uow.outbox.add(LeadCaptured(...))                              (Phase 3)
   8. await uow.commit()           ← 5, 6 and 7 in ONE transaction
   │
   ▼ returns a LeadView DTO; the router maps it to LeadCreateResponse
   ▼ 201 {"id": ..., "lead_temperature": "HOT", "created_at": ...}
   │
   ▼ router.push('/thank-you')
```

Note what the endpoint does **not** do: no scoring, no SQL, no HubSpot call, no
`if budget == ...`. It translates HTTP into a command and a DTO back into HTTP.

## Why HubSpot is never on this path

From Phase 3, the visitor's request finishes as soon as the transaction commits.
The HubSpot call happens afterwards, driven by the outbox row written inside
that same transaction. If HubSpot is down, slow, or the token has expired, lead
capture still succeeds.

The invariant that makes this safe:

```
BEGIN;
  INSERT INTO leads            (...);
  INSERT INTO lead_activities  (...);
  INSERT INTO outbox_events    (type='LeadCaptured', status='pending', ...);
COMMIT;            ← all three, or none
```

Committing the lead first and writing the outbox row second would mean a crash
in between leaves a lead HubSpot never hears about — silently, and forever.
That is the reason `UnitOfWork` exists, and it is why the port is declared in
Phase 0 even though its first adapter arrives in Phase 1.
