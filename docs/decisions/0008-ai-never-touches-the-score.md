# 0008 — The AI interprets text; it never changes the score

**Status:** Accepted · 2026-09-12
**Implemented:** `app/application/services/sales_brief_service.py`,
`app/infrastructure/ai/`

## Context

Phase 6 adds a language model to a system that already scores leads. The obvious
and wrong move is to let it score them — an LLM can read the whole enquiry, so
surely it produces a better number than five weighted dimensions.

## Decision

A hard split, enforced by where the code lives.

**Deterministic and authoritative:** the score. A pure function in
`domain/leads/scoring.py`, rules as versioned data, breakdown persisted. No LLM
anywhere near it.

**AI and advisory:** the sales brief. Pain points, urgency, which service to lead
with, an opening line. Shown **alongside** the score, never instead of it, and it
writes to the activity timeline rather than to any scoring field.

The prompt is given the score as *context*, with an explicit instruction that it
is authoritative and not the model's to dispute — so the narrative agrees with
the number a salesperson can already see.

## Why

**A score must be explainable.** "Why did this lead score 87?" has an exact
answer: five components, listed, with reasons, stored as JSON. "The model felt it
was an 87" is not an answer, and it is the answer a salesperson will need when
they ask why a lead they liked was rated cold.

**A score must be reproducible.** The same inputs produce the same score today
and in a year. A model version bump would silently re-rate the pipeline
overnight, and nobody would know which change caused it.

**A score must be auditable.** A weight change is a diff, reviewable in a pull
request, versioned by `SCORING_VERSION`. A prompt change is a diff too — but its
*effect* is not, and the two are not comparable.

**But rules genuinely cannot read.** "New location opening in six weeks and our
current agency has not delivered in two months" contains urgency, a deadline and
a competitive opening. No weighted dimension extracts that. This is exactly what
a language model is good at, and it is the only thing it is asked to do here.

## Implementation constraints

**Structured output via tool use, not JSON in prose.** The model is given a tool
with a JSON Schema and `tool_choice` forces the call. Asking for JSON in prose
means parsing, repair, and a class of failure that appears in production.

**Validated anyway.** Every field is checked before it becomes a `SalesBrief`:
missing key, empty string, invented enum value, empty list — each raises
`AiResponseError`. The schema constrains the model; this constrains reality. Both
are cheap, and never trusting a shape you did not verify is the whole discipline.

**Refuses rather than fabricates.** With no `ANTHROPIC_API_KEY`,
`NullSalesBriefGenerator` raises a clear error naming the variable. It does not
invent a plausible brief — a fabricated brief is worse than none, because a
salesperson would act on it.

**The model sees a narrow request.** `SalesBriefRequest` enumerates exactly what
it gets. Not the whole `Lead`: no idempotency key, no CRM id, no internal sync
errors.

**Everything is measured.** `ai_runs` records latency, token counts, an estimated
cost and the `prompt_version` on every call, success or failure. An AI feature you
cannot measure is one you cannot improve or budget for. `human_rating` is present
and deliberately unused — it is the hook for a thumbs up/down control, which is
what turns a pile of runs into an evaluation set.

## What tradeoff are we accepting?

The score ignores the free-text message entirely. A prospect who writes something
revealing but answers the dropdowns modestly is under-scored by the rules — and
the brief is exactly what surfaces that to a human, who then decides.

That is the right division of labour: the deterministic system ranks the queue,
the AI adds context, the human decides.

## What would change this decision?

A hybrid, if there were ever evidence for it: the LLM proposes an *adjustment*
within a bounded range, recorded as a separate, clearly-labelled component of the
breakdown, with the deterministic base still visible.

That needs an evaluation set to justify — which is what `ai_runs` and
`human_rating` are quietly accumulating the raw material for. Not before.

## How do I verify it?

`tests/unit/infrastructure/test_anthropic_client.py` covers every bad-output
case: prose instead of a tool call, missing fields, empty lists, invented enum
values, provider errors, timeouts.

For the separation itself: generate a brief on a lead and confirm `score`,
`temperature` and `score_version` are unchanged. The brief is written as an
activity; nothing in `SalesBriefService` can reach a scoring field.
