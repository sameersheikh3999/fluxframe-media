# 0007 — Idempotency: a client-generated key and a unique index

**Status:** Accepted · 2026-09-12
**Implemented:** `leads.idempotency_key` (UNIQUE), `LeadService.capture_lead`,
`BookCallForm`

## Context

Five different things can cause the same lead to be submitted twice, and they
are not the same problem:

1. A visitor double-clicks Submit.
2. The network stalls and the browser retries.
3. The outbox redelivers a `LeadCaptured` event.
4. A worker dies mid-delivery and its row is reclaimed.
5. A dead-lettered event is replayed by an operator.

Treating all five with one mechanism produces something that handles none of
them well.

## Decision

**Different mechanisms for different problems**, each at the layer that owns it.

| Scenario | Mechanism |
|---|---|
| Double-click, browser retry | Client generates `idempotency_key` **once per form mount**; both requests carry it. UNIQUE index on `leads.idempotency_key`. |
| Two requests race | The unique index is the arbiter. `IntegrityError` on that constraint becomes a domain-meaningful `IdempotencyConflictError`, not a 500. |
| HubSpot call redelivered | HubSpot `batch/upsert` with `idProperty=email` — natively create-or-update. Plus `crm_contact_id` short-circuits the second call. |
| Worker died mid-delivery | Row stuck in `processing` is reclaimed after a timeout. Safe because the consumer is idempotent. |
| Operator replays a dead letter | Same as above. |

## API semantics

- First request → **201** with the new lead.
- Replay with the same key → **200** with the identical body.

Both succeed from the visitor's point of view — a double-click must never show an
error — but the status code tells an API consumer whether anything was created.

## Why client-generated, not server-derived

The obvious alternative is hashing the payload. It fails on a real case: someone
submits, realises they typed the wrong budget, corrects it and submits again
within the window. A content hash sees two different payloads and creates two
leads; a per-mount key sees one form session and correctly creates one lead,
updated.

A key generated **once per form mount** — not per submit — is what makes that
work. `useState(() => crypto.randomUUID())` rather than `useRef`, so React never
reads it during render and `randomUUID()` is not re-run on every keystroke.

## Why the header AND the body field

`Idempotency-Key` is the HTTP-native spelling and what an API consumer expects.
The body field survives proxies that strip unknown headers, and it keeps the
contract visible in the OpenAPI schema. The header wins when both are present.

## Why email is NOT unique

Someone enquiring again six months later is a **new lead**, not a constraint
violation. Making email unique would silently swallow a genuine second enquiry —
exactly the lead you most want to know about.

Repeat submissions are a *signal*, not an error. `count_recent_by_email` exists
to surface "third submission from this address today" on the dashboard, where a
human can judge it.

## What tradeoff are we accepting?

**The fast path is a read before a write.** `find_by_idempotency_key` runs on
every submission. One indexed lookup against a form post is not a cost worth
optimising, and the unique index is the real guarantee — the lookup only avoids
relying on an exception for the common case.

**No stored responses.** A generic idempotency layer would store the full
response body against the key with a TTL, so a replay returns byte-identical
output. This returns the lead's id and creation time, which is all the endpoint
produces. One unique column on one table covers the actual risk; the upgrade
path exists if a second write endpoint ever needs it.

## What changes at 10x / 100x?

Nothing. A unique index is the database's problem and it is good at it.

## How do I verify it?

```bash
cd backend
uv run pytest -k idempot -v
```

- `test_the_same_key_twice_creates_one_lead`
- `test_a_replay_writes_no_second_outbox_event` — otherwise a double-click makes
  two HubSpot contacts
- `test_a_replay_does_not_commit`
- `test_the_second_identical_submission_returns_200_not_an_error`
- `test_a_duplicate_key_creates_exactly_one_row` — against a real unique index
- `test_the_same_email_twice_with_different_keys_is_two_leads`

By hand: run the same `curl` from
[local-development.md](../local-development.md) twice. First 201, then 200, same
id.
