# Architecture

Fluxframe Media is a **modular monolith**: one deployable backend, one database,
with the internal boundaries a service split would need already drawn.

```
Browser
   │
   ▼
Next.js (Railway or Vercel)
   │   public pages render statically; the dashboard renders server-side
   │
   │ REST/JSON
   ▼
FastAPI (Railway)
   │
   ├── api/            inbound HTTP adapter
   ├── application/    use cases + ports
   ├── domain/         business rules, pure Python
   ├── infrastructure/ outbound adapters — database, HubSpot, AI
   └── workers/        the outbox dispatcher loop
   │
   ▼
PostgreSQL ─────► HubSpot · Anthropic  (asynchronously, after the response)
```

## The dependency rule

```
          ┌────────────────────────────────────────┐
          │ api/  schemas/  main.py                │  driving adapters
          └───────────────┬────────────────────────┘
                          │ imports ↓
          ┌───────────────▼────────────────────────┐
          │ dependencies/   the composition root    │
          └───────────────┬────────────────────────┘
                          │ imports ↓
          ┌───────────────▼────────────────────────┐
          │ workers/   the outbox loop and handlers │
          └───────────────┬────────────────────────┘
                          │ imports ↓
          ┌───────────────▼────────────────────────┐
          │ application/  services · ports · dto    │  use cases
          └───────────────┬────────────────────────┘
                          │ imports ↓
          ┌───────────────▼────────────────────────┐
          │ domain/  entities · rules · events      │  business rules
          └────────────────────────────────────────┘
                          ▲
                          │ implements ports, imports domain
          ┌───────────────┴────────────────────────┐
          │ infrastructure/  db · hubspot · ai      │  driven adapters
          └────────────────────────────────────────┘
```

Dependencies point **inward**. The domain knows nothing about anything.
Infrastructure knows about the domain and the ports; nothing knows about
infrastructure except the composition root.

This is not a guideline. It is six contracts in `backend/.importlinter`, checked
by `uv run lint-imports` in CI:

| Contract | What it forbids |
|---|---|
| Layered architecture | any import pointing "upward" through the stack |
| Domain purity | `app.domain` importing FastAPI, Pydantic, SQLAlchemy, structlog, or any other layer |
| Application independence | `app.application` importing infrastructure, transport or config |
| API uses ports | a router importing an adapter **directly** (the indirect path through `app.dependencies` is the intended wiring) |
| Infrastructure is an adapter | an adapter calling a service, a router, a worker or the composition root |
| Schemas are transport only | a Pydantic schema reaching a service, a port or an adapter |

Try it: add `from app.infrastructure.clock import SystemClock` to
`backend/app/api/v1/health.py` and run `uv run lint-imports`. It fails and names
the exact line.

### Driving versus driven adapters

The distinction that keeps the arrows honest:

- **Driving** adapters call *into* the application. `api/` (HTTP requests) and
  `workers/` (elapsed time) are both driving adapters.
- **Driven** adapters are things the application calls *out* to. `infrastructure/`
  holds those: the database, HubSpot, the model provider.

Filing the outbox worker under `infrastructure` would mean infrastructure
importing a service, which is exactly the inversion these contracts exist to
prevent. `lint-imports` caught precisely that when those files were first written
in the wrong place.

## The four layers

### 1. `api/` — the inbound adapter

Receives HTTP. Validates transport-level input with Pydantic. Calls **one**
application service method. Maps the returned DTO onto a response schema.

No business rules, no SQL, no third-party HTTP calls. The honesty test: could you
delete `app/api/` and drive the same use cases from a CLI in an afternoon?

Also here: request-id middleware, the shared error envelope, and per-IP rate
limiting on the public endpoint.

### 2. `application/` — the use cases

One service method per use case. It coordinates domain objects and ports, and it
owns the transaction boundary. It is handed everything it needs through its
constructor and never constructs an adapter itself.

`ports/` holds `typing.Protocol` classes describing what the application needs
from the outside world: a `LeadRepository`, a `CrmClient`, a `Clock`, a
`SalesBriefGenerator`. `dto/` holds plain dataclasses — deliberately not Pydantic
models, because Pydantic is a serialisation tool and serialisation is transport.

Read `LeadService.capture_lead()` as a transaction script: every line is either a
domain call or a repository call, and the transaction boundary is visible on the
page.

### 3. `domain/` — the business rules

Pure Python, standard library only. If it cannot run in a unit test with no
network, no database and no configuration, it does not belong here.

- `scoring.py` — a pure function; rules as versioned data summing to exactly 100
- `lifecycle.py` — the transition table, as data
- `entities.py` — the `Lead` aggregate, which validates itself and collects
  events rather than dispatching them
- `events.py`, `activities.py`, `enums.py`, `errors.py`

The aggregate is the guarantee: a `Lead` cannot be put into an invalid state
through any code path, because `transition_to` consults the lifecycle table. The
API, the dashboard, a background worker and a future AI agent all get the same
answer.

### 4. `infrastructure/` — the outbound adapters

Talks to PostgreSQL, HubSpot and Anthropic. Each adapter satisfies a port
**structurally**: it does not subclass or import the Protocol. mypy verifies the
claim where the two are wired together.

An adapter is passive. It never calls a service.

Each one has a "not configured" counterpart — `NullCrmClient`,
`NullSalesBriefGenerator` — that reports `is_configured = False`. Those are not
stubs: running without a CRM or without AI is a supported production mode, and
this is how the application stays fully functional in it.

## Cross-cutting: `observability/`

`app.observability` sits outside the layer stack on purpose. Logging really is
cross-cutting — the HTTP adapter logs, and the background dispatcher does too.
Filing it under infrastructure would have meant punching a hole in the "API must
not import infrastructure" rule on day one, and a rule with an exception stops
being a rule.

What is *not* relaxed: `app.domain` and `app.application` must not import it
either. Domain code does not log. It returns results and raises errors, and the
caller decides what is worth recording — which is what keeps a scoring function
callable four thousand times in a test without flooding stdout.

## The composition root

`app/dependencies/` is the only package permitted to import both
`app.application` and `app.infrastructure`. It answers exactly one question:
*when something asks for a port, what does it actually get?*

```python
@lru_cache
def get_clock() -> Clock:        # the port
    return SystemClock()         # the adapter
```

That single line is where mypy checks Protocol conformance. Everything else in
the codebase names a port and receives whatever this package chose.

`get_app_settings` reads `request.app.state.settings` rather than the module-level
singleton, so `create_app(settings)` is genuinely authoritative. That is not
pedantry: when it did not, the internal-access guard read an empty secret from
the ambient environment while the app had been built with one, and the dashboard
answered without authentication. The test suite caught it.

## The two invariants worth understanding

### The transaction boundary

The lead, its audit-trail entry and the outbox event are written in **one**
transaction:

```python
async with uow:
    await uow.leads.add(lead)
    await uow.activities.add(activity)
    await uow.outbox.add(event)
    await uow.commit()          # all three, or none
```

`SqlAlchemyUnitOfWork` owns one `AsyncSession` and hands it to all three
repositories, which makes the sharing structural rather than a convention
someone breaks at 11pm.

### Delivery is at-least-once, and consumers are idempotent

The outbox guarantees the event is delivered at least once — a retry after a
timeout that actually succeeded, a reclaimed stalled row, a replayed dead letter.
So every consumer must be idempotent. The HubSpot adapter achieves that by
upserting on email rather than blind-creating, and `CrmSyncService` short-circuits
when the lead already has a contact id.

At-least-once delivery + an idempotent consumer = effectively-once, without any
of the machinery exactly-once delivery would require.

## Where the AI sits

```
API route → SalesBriefService → SalesBriefGenerator (port)
                                      │
                                      └─► AnthropicSalesBriefGenerator (adapter)
```

The service orchestrates; it does not prompt. There is no prompt text in it, no
JSON parsing, no model name, no retry logic. All of that lives in the adapter.

What the AI is allowed to do: interpret the prospect's free-text message.
What it is **not** allowed to do: change the score. Scoring is deterministic,
versioned and explainable. An LLM that could move a lead from WARM to HOT would
make the score unauditable, which is the opposite of what a sales team needs.

Every call is recorded in `ai_runs` with latency, tokens, estimated cost and the
prompt version — because an AI feature you cannot measure is one you cannot
improve.

## What is deliberately not built

No `clients` or `deals` tables. No content-production workflow. Those arrive in
Phases 7 and 8 (see [implementation-plan.md](implementation-plan.md)), and until
then they would be speculative schema — the most expensive kind to remove.
