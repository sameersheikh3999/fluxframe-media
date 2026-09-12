# 0006 — The transactional outbox, on PostgreSQL, with no broker

**Status:** Accepted · 2026-09-12
**Implemented:** `app/infrastructure/database/outbox_store.py`,
`app/application/services/outbox_dispatcher.py`, `app/workers/outbox_worker.py`

## Context

Capturing a lead must eventually create a HubSpot contact. Those are two
different systems, and there is no ordering of "commit locally" and "call a
remote API" that is safe:

```python
await uow.commit()            # lead saved
await hubspot.upsert(lead)    # ← process dies here
# lead exists, HubSpot never hears about it. Silently. Forever.
```

```python
await hubspot.upsert(lead)    # contact created
await uow.commit()            # ← this fails
# HubSpot has a contact for a lead you do not have. Worse.
```

You cannot atomically commit to two systems without a distributed transaction,
and a distributed transaction across an HTTP API you do not control is not
available at any price.

## Decision

Write the *intention* to call HubSpot into the same PostgreSQL transaction as
the lead:

```sql
BEGIN;
  INSERT INTO leads            (...);
  INSERT INTO lead_activities  (...);
  INSERT INTO outbox_events    (type='LeadCaptured', status='pending', ...);
COMMIT;
```

One database, so atomicity is free. A background dispatcher then claims rows and
delivers them.

**No message broker.** The queue is a table. That is the whole point: inserting
into it is atomic with the business write that caused it, which no external
broker can offer, because a broker is a second system that cannot join your
transaction.

## What problem does this solve?

Side effects that survive crashes, restarts and third-party outages, without the
visitor ever waiting for the third party.

## Why this rather than the alternatives?

**Call HubSpot inline, before responding.** Couples the visitor's experience to
HubSpot's uptime and latency, and loses the lead entirely if HubSpot 500s at the
wrong moment. The form is the business; it cannot depend on a CRM.

**`BackgroundTasks` after the commit.** Better, and still wrong: the task lives
in process memory. A restart mid-flight loses it, there is no retry, no
visibility and no record that it was ever supposed to happen.

**Celery or a broker.** Solves delivery well and does not solve the actual
problem — enqueueing to Redis is not atomic with the PostgreSQL commit, so the
exact failure we started with reappears one layer along. Plus a new service, a
new failure mode and a new bill.

## Implementation notes worth knowing

**`FOR UPDATE SKIP LOCKED`** is what makes the claim safe under horizontal
scaling. PostgreSQL locks the selected rows and silently skips any another
transaction already holds, so two Railway replicas polling the same table never
receive the same event. It is a built-in work-queue primitive and it is good to
thousands of events per second.

**Attempts increment at claim time, not on failure.** A worker that dies
mid-delivery still burns an attempt; otherwise a crash-looping consumer retries
forever without ever reaching `max_attempts`.

**Full jitter on the backoff.** Without it, a thousand events that failed during
one outage all retry at the same instant and recreate the outage.

**Unknown exceptions are treated as transient.** Optimism is the safer default: a
genuine bug still dead-letters after `max_attempts`, whereas treating unknowns as
permanent would drop recoverable work on the first blip.

**`Retry-After` wins when the provider sends one.** Retrying sooner than a rate
limiter asked turns a short throttle into a long one.

## What tradeoff are we accepting?

**At-least-once delivery.** Every consumer must be idempotent. The HubSpot
adapter achieves that by upserting on email rather than blind-creating, and
`CrmSyncService` short-circuits when the lead already has a contact id.
At-least-once + an idempotent consumer = effectively-once, with none of the
machinery exactly-once would require.

**Eventual consistency.** A lead is in HubSpot within seconds, not instantly.
For a CRM sync that is not a real cost.

**Polling latency.** Five seconds by default. The cheap upgrade, before anyone
reaches for Redis, is PostgreSQL `LISTEN`/`NOTIFY` to wake the poller instantly,
with polling kept as the safety net — near-zero added complexity, no new
infrastructure.

## What changes at 10x?

Nothing. Poll faster if you care, or add a replica — `SKIP LOCKED` already makes
that safe.

## What changes at 100x?

Move the dispatcher into its own Railway service reading the same database.
Because it reaches the rest of the system through ports, that is a deployment
change rather than a rewrite — which is the argument for having drawn the
boundaries early.

A broker starts earning its cost when you need sub-second fan-out, scheduled
jobs, or throughput a PostgreSQL table cannot carry. Measure first, then write
the ADR that supersedes this one.

## How do I verify it?

`tests/integration/test_lead_flow.py`:

- `test_the_lead_and_its_outbox_event_are_committed_together`
- `test_a_rejected_lead_leaves_no_trace`
- `test_dispatching_twice_does_not_call_the_crm_twice`
- `test_a_transient_crm_failure_leaves_the_event_retryable`
- `test_a_permanent_crm_failure_dead_letters`

and `tests/unit/application/test_outbox_dispatcher.py` for the full retry policy.
