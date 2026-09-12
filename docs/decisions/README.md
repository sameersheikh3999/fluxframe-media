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
| [0006](0006-transactional-outbox.md) | Transactional outbox on PostgreSQL, with no broker | Accepted |
| [0007](0007-idempotency-strategy.md) | Client-generated idempotency key plus a unique index | Accepted |
| [0008](0008-ai-never-touches-the-score.md) | The AI interprets text; it never changes the score | Accepted |
| [0009](0009-single-service-deployment.md) | Single-service deployment, with Next.js in front | Accepted |

## Smaller decisions, recorded in the code

Not everything warrants an ADR. These are documented where they apply, in a
comment next to the line they explain:

- **VARCHAR, not native PostgreSQL enums** — `infrastructure/database/models.py`.
  Native enums need `ALTER TYPE … ADD VALUE` to evolve and cannot drop values,
  and the industry list will change.
- **Email is indexed but not unique** — same file. A genuine re-enquiry is a new
  lead, not a constraint violation.
- **Status and temperature are independent** — `domain/leads/enums.py`.
  Temperature is a model output; status records what a human did. Conflating them
  means re-scoring rewrites sales history.
- **Rate limiting is in-process, not shared** — `api/rate_limit.py`. Redis would
  buy precision a portfolio site does not need.
- **SQLite in the test suite** — `docs/testing.md`. Deliberate, narrow, and its
  limits are stated rather than hidden.
- **`workers/` is not `infrastructure/`** — `workers/__init__.py`. Driving
  adapters call into the application; driven adapters are called by it.
