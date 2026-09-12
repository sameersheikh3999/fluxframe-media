# 0004 — The application layer owns the transaction boundary

**Status:** Accepted · 2026-09-12
**Declared:** Phase 0 (`app/application/ports/unit_of_work.py`)
**First implemented:** Phase 1

## Context

From Phase 3, capturing a lead must write three rows atomically:

```
leads             the lead itself
lead_activities   the audit trail entry
outbox_events     the intent to call HubSpot
```

All three, or none. There is no ordering of "commit the lead" and "call HubSpot"
that is safe — a crash between them either loses the CRM sync silently and
permanently, or creates a HubSpot contact for a lead that does not exist. The
transactional outbox resolves this by making the *intent* to call HubSpot part
of the same PostgreSQL transaction as the data.

That only works if something can express "these three writes share one
transaction". A service holding three independent repositories cannot: nothing
in the type system says they share a session. It is a convention, and
conventions get broken at 11pm.

## Decision

`app/application/ports/unit_of_work.py` declares a `UnitOfWork` Protocol — an
async context manager with `commit()` and `rollback()`. Repositories are
attributes on it, added in the phase that introduces each one.
`SqlAlchemyUnitOfWork` (Phase 1) owns exactly one `AsyncSession` and hands that
same session to every repository it exposes.

```python
async with uow:
    await uow.leads.add(lead)
    await uow.activities.add(activity)
    await uow.outbox.add(event)
    await uow.commit()
```

Leaving the context manager without committing rolls back. That is the safe
default: a use case which raises halfway through cannot leave a partial write.

## What problem does this solve?

It makes the transaction boundary a **visible, typed, testable** part of the use
case rather than an invisible property of the framework — and it does so without
`app.application` importing SQLAlchemy.

## What simpler alternative exists?

A request-scoped `AsyncSession` provided by `Depends`, with middleware
committing at the end of the request. Less code, and extremely common in FastAPI
codebases.

Rejected for two reasons:

1. **The boundary becomes invisible.** It lives in middleware, not in the use
   case. Reading `capture_lead()` would not tell you where the transaction
   begins or ends — and that is the single most important thing about it.
2. **Phase 4 cannot express what it needs.** The demo generator creates up to ten
   leads in one HTTP request, and each must be its own transaction: lead seven
   failing must not roll back leads one through six. One session per request
   makes that awkward; one unit of work per lead makes it obvious.

## What tradeoff are we accepting?

An indirection that is genuinely unnecessary in Phase 1, where a single service
writes to a single table. The value appears in Phase 3 and is unambiguous by
Phase 4.

We also accept that `unit_of_work.py` is, in Phase 0, a file with no
implementation and no caller. That is deliberate: writing the contract down now
is what stops Phase 1 from quietly reaching for a raw `AsyncSession` and then
having to be unpicked.

## What changes at 10x / 100x?

Nothing. A unit of work is a transaction, and transactions are the database's
problem. If contention on `outbox_events` ever became real, the fix is
`FOR UPDATE SKIP LOCKED` in the dispatcher (already planned for Phase 5), not a
different transaction model.

## How do I verify it?

From Phase 1, there is a test asserting that a failure after the lead write and
before `commit()` leaves **no** lead row. From Phase 3, an equivalent test
asserts the lead and the outbox row appear together or not at all.
