# Architecture

Fluxframe Media is a **modular monolith**: one deployable backend, one database,
with the internal boundaries a service split would need already drawn.

```
Browser
   │
   ▼
Next.js (Vercel)  ──── public pages render statically
   │
   │ REST/JSON
   ▼
FastAPI (Railway)
   │
   ├── api/            inbound adapter — HTTP in, HTTP out
   ├── application/    use cases + ports
   ├── domain/         business rules, pure Python
   └── infrastructure/ outbound adapters — database, HubSpot, events
   │
   ▼
PostgreSQL (Neon)
```

## The dependency rule

```
          ┌────────────────────────────────────────┐
          │ api/  schemas/  dependencies/  main.py │  inbound adapters
          └───────────────┬────────────────────────┘
                          │ imports ↓
          ┌───────────────▼────────────────────────┐
          │ application/  services, ports, dto     │  use cases
          └───────────────┬────────────────────────┘
                          │ imports ↓
          ┌───────────────▼────────────────────────┐
          │ domain/  entities, rules, events       │  business rules
          └────────────────────────────────────────┘
                          ▲
                          │ implements ports, imports domain
          ┌───────────────┴────────────────────────┐
          │ infrastructure/  db, hubspot, events   │  outbound adapters
          └────────────────────────────────────────┘
```

Dependencies point **inward**. The domain knows nothing about anything.
Infrastructure knows about the domain and the ports; nothing knows about
infrastructure except the composition root.

This is not a guideline. It is six contracts in `backend/.importlinter`,
checked by `uv run lint-imports` in CI:

| Contract | What it forbids |
|---|---|
| Layered architecture | any import pointing "upward" through the stack |
| Domain purity | `app.domain` importing FastAPI, Pydantic, structlog, or any other layer |
| Application independence | `app.application` importing infrastructure, transport or config |
| API uses ports | a router importing an adapter **directly** (the indirect path through `app.dependencies` is the intended wiring) |
| Infrastructure is an adapter | an adapter calling a service, a router or the composition root |
| Schemas are transport only | a Pydantic schema importing anything but `app.domain` |

Try it: add `from app.infrastructure.clock import SystemClock` to
`backend/app/api/v1/health.py` and run `uv run lint-imports`. It fails and names
the exact line.

## The four layers

### 1. `api/` — inbound adapter

Receives HTTP. Validates transport-level input with Pydantic. Calls **one**
application service method. Maps the returned DTO onto a response schema.

Contains no business rules, no SQL, no third-party HTTP calls.

The honesty test: could you delete `app/api/` and drive the same use cases from
a CLI in an afternoon? If not, logic has leaked into it.

### 2. `application/` — use cases

One service method per use case. It coordinates domain objects and ports, and it
owns the transaction boundary. It is handed everything it needs through its
constructor and never constructs an adapter itself.

`ports/` holds `typing.Protocol` classes describing what the application needs
from the outside world. `dto/` holds plain dataclasses — deliberately not
Pydantic models, because Pydantic is a serialisation tool and serialisation is a
transport concern.

### 3. `domain/` — business rules

Pure Python. Standard library only. If it cannot run in a unit test with no
network, no database and no configuration, it does not belong here.

Phase 0 contains only `DomainError`. Lead entities, enums, scoring and lifecycle
arrive in Phases 1 and 2.

### 4. `infrastructure/` — outbound adapters

Talks to PostgreSQL, HubSpot and (later) event consumers and AI providers. Each
adapter satisfies a port **structurally**: it does not subclass or import the
Protocol. mypy verifies the claim where the two are wired together.

An adapter is passive. It never calls a service.

## Cross-cutting: `observability/`

`app.observability` sits outside the layer stack on purpose. Logging really is
cross-cutting — the HTTP adapter logs, and Phase 5's background dispatcher will
too. Filing it under infrastructure would have meant punching a hole in the
"API must not import infrastructure" rule on day one, and a rule with an
exception stops being a rule.

What is *not* relaxed: `app.domain` and `app.application` must not import it
either. Domain code does not log. It returns results and raises errors, and the
caller decides what is worth recording. That is what keeps domain functions
testable with zero setup.

## Composition root

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

## What exists today

Phase 0 ships health endpoints and nothing else. The one working example of the
full flow is:

```
GET /api/v1/health
  api/v1/health.py          router
  → dependencies/services.py  composition root assembles SystemService
  → application/services/system_service.py    the use case
  → application/ports/clock.py                the port it depends on
  ← infrastructure/clock.py                   the adapter that satisfies it
```

There is no business logic in it, which is the point: it demonstrates the
dependency rule with nothing to distract from the dependency rule.

## Deliberately not built yet

Database, migrations, Lead domain, HubSpot, outbox, demo generator, dashboard,
AI. Each arrives in the phase that needs it — see
[implementation-plan.md](implementation-plan.md). Empty packages waiting for
future features are speculative structure, and speculative structure ages into
lies about what the system does.
