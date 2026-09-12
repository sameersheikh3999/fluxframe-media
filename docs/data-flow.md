# Data flow

How a request actually travels through the system.

## 1. A visitor submits the form

```
/book-call  (Next.js Client Component)
   │  Zod validates for UX — inline errors, no round trip
   │  idempotency_key generated ONCE on mount (crypto.randomUUID)
   │  utm_* / referrer / landing_page read from sessionStorage
   ▼
POST http://api…/api/v1/leads          ← direct, browser to FastAPI
   │  CORS: origin must be in FRONTEND_ORIGINS
   │  Header: Idempotency-Key
   │
   ▼ [middleware] api/middleware.py
   │  X-Request-ID accepted from the caller, or minted
   │  bound to a ContextVar and to the structlog context
   │
   ▼ [rate limit] api/rate_limit.py
   │  per-IP fixed window; 429 with Retry-After if exceeded
   │
   ▼ [router] api/v1/leads.py
   │  Pydantic LeadCreateRequest validates TRANSPORT:
   │    is this a well-formed email, is this string a permitted enum value
   │  → builds CaptureLeadCommand (an application DTO)
   │
   ▼ [use case] application/services/lead_service.py
   │
   │  async with uow:
   │    1. uow.leads.find_by_idempotency_key(key)
   │         found?  → return it, 200, write nothing. Done.
   │    2. Lead.capture(...)        ← the DOMAIN constructs and validates
   │    3.   └─ score_lead(...)     ← pure function, five dimensions
   │    4.   └─ collects LeadCaptured (+ LeadMarkedHot if it scored 80+)
   │    5. uow.leads.add(lead)
   │    6. uow.activities.add(captured); uow.activities.add(scored)
   │    7. uow.outbox.add(event) for each collected event
   │    8. await uow.commit()       ← ALL OF IT, OR NONE OF IT
   │
   ▼ [router] maps LeadCaptureResult → LeadCreateResponse
   ▼ 201 {"id": …, "created_at": …, "message": "Thanks — …"}
   │
   ▼ router.push('/thank-you')
```

Note what the endpoint does **not** do: no scoring, no SQL, no HubSpot call, no
`if budget == …`. It translates HTTP into a command and a DTO back into HTTP.

Note also what the visitor receives: an id and a timestamp. No score, no
temperature, no breakdown. A prospect must not learn the system rated them COLD,
and exposing the scoring internals would let anyone reverse-engineer the rules.

## 2. The CRM sync happens afterwards, independently

```
[background] workers/outbox_worker.py — every 5 seconds
   │
   ▼ OutboxDispatcher.dispatch_once()
   │
   │  a. reclaim_stalled()   rows a dead worker left marked `processing`
   │  b. claim_batch()       UPDATE … WHERE status IN ('pending','failed')
   │                           AND next_attempt_at <= now()
   │                         FOR UPDATE SKIP LOCKED
   │                         ← two replicas never get the same row
   │  c. route on event_type → handler
   │
   ▼ workers/handlers.py → CrmSyncService.sync_lead(lead_id)
   │
   │  · CRM not configured, or a demo lead?  → mark `skipped`, done
   │  · already has a crm_contact_id?        → nothing to do, done
   │  · otherwise: build CrmContactUpsert and CLOSE THE TRANSACTION
   │
   ▼ [adapter] infrastructure/hubspot/client.py
   │  POST /crm/v3/objects/contacts/batch/upsert  idProperty=email
   │  ← the network call happens OUTSIDE any database transaction
   │
   ▼ classify the response
        2xx              → mark_processed. Lead gets crm_contact_id.
        429 / 5xx / net  → CrmTransientError → retry with backoff + jitter
        400 / 401 / 403  → CrmPermanentError → dead-letter immediately
        attempts > max   → dead-letter
```

Three decisions in that diagram are worth stating plainly.

**The HTTP call is outside the transaction.** Holding a database transaction open
across a multi-second HTTP request ties up a connection from a small pool and
turns a slow CRM into a database incident.

**A 401 dead-letters rather than retrying.** Retrying a wrong token forever hides
a configuration bug behind a queue that quietly grows. Dead-lettering surfaces it
on the dashboard, where someone can act on it.

**Backoff is jittered.** Without jitter, a thousand events that failed during the
same outage all retry at the same instant and recreate the outage.

## 3. Why the outbox exists at all

These two orderings are both wrong, and there is no third:

```python
await uow.commit()            # lead saved ✓
await hubspot.upsert(lead)    # ← process dies HERE
# → lead exists, HubSpot never hears about it. Silently. Forever.
```

```python
await hubspot.upsert(lead)    # contact created in HubSpot ✓
await uow.commit()            # ← this fails
# → HubSpot has a contact for a lead you do not have. Worse.
```

You cannot atomically commit to two systems. The transactional outbox sidesteps
it by putting the *intention* to call HubSpot into the same PostgreSQL
transaction as the data — one database, so atomicity is free:

```sql
BEGIN;
  INSERT INTO leads            (...);
  INSERT INTO lead_activities  (...);
  INSERT INTO outbox_events    (type='LeadCaptured', status='pending', ...);
COMMIT;            -- all three, or none
```

The trade is **at-least-once** delivery, which is why every consumer is
idempotent. At-least-once + an idempotent consumer = effectively-once, with none
of the machinery exactly-once would need.

## 4. The dashboard reads a different path

```
GET /dashboard/leads  (Next.js Server Component, runs on the server)
   │
   ▼ lib/api-server.ts  — imports "server-only"
   │  attaches X-Internal-Secret
   │  ← the browser NEVER sees this header or this value
   ▼
GET /api/v1/dashboard/leads?temperature=hot&limit=25
   │
   ▼ Depends(require_internal_access)  — constant-time comparison
   │
   ▼ [read model] infrastructure/database/read_models.py
   │  flat rows + COUNT, filtered and paginated
   │  NOT rehydrated Lead aggregates
   ▼
HTML streamed to the browser
```

Reads and writes take different paths on purpose. A write loads one full
aggregate, applies a rule and saves it. A read wants fifty flat rows with a
count. Forcing both through one repository produces either half-built entities
or a dashboard that rehydrates fifty aggregates to render a table.

`LeadRepository` returns domain entities and lives on the Unit of Work.
`LeadReadModel` returns view DTOs and does not — reads need no transaction
boundary. That is the useful five percent of CQRS with none of the
infrastructure.

## 5. Client-side admin actions go through a proxy

The demo generator and the dashboard's status buttons are Client Components, so
they cannot hold the secret:

```
Browser ──POST /api/internal/demo/leads──► Next.js Route Handler
                                              │  path allowlist
                                              │  attaches X-Internal-Secret
                                              ▼
                                          POST /api/v1/demo/leads
```

The route handler is transport only: it checks the path against an allowlist,
attaches a header and forwards. A wildcard proxy without that allowlist would
make every backend endpoint reachable from a browser with a valid secret
attached.

## 6. The demo generator uses the same path as the form

```
Website form    ──┐
                  ├──► LeadService.capture_lead ──► domain ──► database
Demo generator  ──┘
```

That single shared arrow is the architectural rule. The tempting shortcut — a
bulk INSERT — would be faster and worthless: synthetic leads would exercise none
of the real application. They would not be scored by the real scorer, would not
write activity rows, and would not surface a bug in either.

The only differences are `is_demo=True`, `source=demo_generator` and an
`@example.com` address. One transaction per lead, so lead seven failing does not
roll back leads one to six.

## 7. The AI brief runs outside everything

```
POST /api/v1/dashboard/leads/{id}/sales-brief
   │
   ▼ SalesBriefService
   │  · reads the lead, closes the transaction
   │  · calls the port with a NARROW request — no idempotency key,
   │    no CRM id, no internal errors; the model sees only what it needs
   ▼ AnthropicSalesBriefGenerator
   │  tool-use structured output, tool_choice forced
   │  every field validated before it crosses back
   ▼ records an ai_runs row (latency, tokens, cost, prompt version)
   ▼ writes the brief as a timeline activity — so regenerating keeps the old one
```

The LLM call is outside the transaction for the same reason the HubSpot call is:
it can take ten seconds.

## Request ids tie it all together

The `X-Request-ID` accepted or minted in step 1 is bound to a ContextVar, stamped
on every log line, carried into the outbox row as `correlation_id`, and recorded
on the `ai_runs` row. So one id greps across:

```
the HTTP access log
  → every application log emitted while handling that request
  → the outbox event it produced
  → the HubSpot call made ten seconds later
  → the AI brief generated on that lead's behalf
```

Being able to follow one identifier across all of those is most of what
"observability" means in a system this size.
