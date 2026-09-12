# Architecture decision records

One file per decision that was genuinely contested — where a reasonable engineer
could have chosen otherwise. Each records the alternatives and the tradeoff we
accepted, so that a year from now the reasoning is recoverable rather than
reconstructed.

ADRs are immutable. A decision that changes gets a new ADR that supersedes the
old one; the old file stays, marked superseded.

| # | Decision | Status |
|---|---|---|
| [0001](0001-modular-monolith.md) | Modular monolith, not microservices | Accepted |
| [0002](0002-layered-architecture-and-ports.md) | Layered architecture with Protocol-based ports | Accepted |
| [0003](0003-async-sqlalchemy-and-psycopg3.md) | Async SQLAlchemy + psycopg 3, synchronous Alembic | Accepted |
| [0004](0004-unit-of-work-owns-the-transaction.md) | The application layer owns the transaction boundary | Accepted |
| [0005](0005-frontend-backend-boundary.md) | Public form calls FastAPI directly; internal pages go through the Next.js server | Accepted |

Decisions not yet made, and therefore not recorded: the transactional outbox
design (Phase 3), the idempotency strategy (Phase 1/3), and enum storage in
Postgres (Phase 1). Writing those ADRs before writing the code they describe
would be documenting a guess.
