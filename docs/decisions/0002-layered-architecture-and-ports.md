# 0002 — Layered architecture with Protocol-based ports

**Status:** Accepted · 2026-09-12

## Context

Business rules that matter to Fluxframe — lead scoring, lifecycle transitions,
and later the content production state machines — must be testable, reusable and
stable. In a conventional FastAPI application they end up inside request
handlers, where they are reachable only over HTTP and testable only with a
running database.

## Decision

Four layers with dependencies pointing inward: `api` → `application` → `domain`,
with `infrastructure` implementing ports declared by `application`. Ports are
`typing.Protocol` classes. Enforced by six `import-linter` contracts in CI.

Two consequences worth stating explicitly:

**The domain does not import Pydantic.** Domain entities are `@dataclass`.
Pydantic is a validation and serialisation library, which makes it a transport
concern. The moment a domain entity grows a `Field(alias=...)` for the sake of a
JSON payload, the domain has started caring about HTTP.

**`app.observability` sits outside the layer stack.** Logging is genuinely
cross-cutting. Filing it under `infrastructure` would have required an exception
to the "API must not import infrastructure" rule on day one, and a rule with an
exception is not a rule. It remains forbidden to `domain` and `application`.

## Why Protocol rather than ABC?

An ABC forces the adapter to import the application layer in order to inherit
from it. That edge is legal under the dependency rule, but it is an edge we do
not need — and it makes test doubles heavier, because a fake must inherit too.

With `Protocol`, `SystemClock` in `infrastructure/clock.py` satisfies
`Clock` in `application/ports/clock.py` without either file mentioning the other.
Conformance is checked by mypy at the one place they meet: the composition root.

**Tradeoff:** a signature mismatch surfaces as a mypy error rather than an
`ImportError`. That makes `uv run mypy app` a required gate, not an optional one.

## What simpler alternative exists?

Routers calling SQLAlchemy directly, which is what most FastAPI tutorials show.
For a CRUD app of five endpoints it is the right answer. It stops being the
right answer as soon as the same rule must run from an HTTP request, a
background worker and (Phase 6) an AI agent — because then "the rule" is a
request handler, and only HTTP can invoke it.

## What tradeoff are we accepting?

Concretely: more files, and explicit mapping between four representations of the
same concept (Pydantic schema, application DTO, domain entity, ORM model). They
look nearly identical today. The bet is that they diverge, and that when they do
the mapping is already there.

If the mapping ever becomes genuinely painful rather than merely tedious,
SQLAlchemy's imperative mapping is the escape hatch — but that should be a new
ADR, not a quiet Tuesday-night decision.

## How do I verify it?

```
cd backend && uv run lint-imports
```

Six contracts, zero broken. Adding
`from app.infrastructure.clock import SystemClock` to `app/api/v1/health.py`
breaks contract 4 and names the line.
