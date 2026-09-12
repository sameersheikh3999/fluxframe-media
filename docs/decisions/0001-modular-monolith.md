# 0001 — Modular monolith, not microservices

**Status:** Accepted · 2026-09-12

## Context

Fluxframe Media is intended to grow from lead capture into an agency operating
system: sales, onboarding, strategy, scripting, production, QC, publishing,
performance. That is a lot of surface area, and the obvious failure mode is one
`main.py` that nobody can reason about by month three.

The equally obvious overreaction is to split it into services.

## Decision

One deployable FastAPI application, one PostgreSQL database, with strict
internal module boundaries enforced by `import-linter`.

## What problem does this solve?

Keeping lead capture, CRM sync and future content operations from becoming
mutually entangled, without paying for a distributed system.

## Why this rather than the alternatives?

**One flat application.** Faster for a week. Unexplainable by month two, and the
first time scoring logic needs to be reused by a background worker it has to be
extracted from a request handler anyway.

**Microservices.** Solves an organisational problem — many teams deploying
independently — that a solo developer does not have. It would buy network
partitions, distributed transactions, service discovery and a tracing
requirement, in exchange for nothing.

Module boundaries give roughly 90% of the isolation benefit at none of the
operational cost.

## What tradeoff are we accepting?

Boundaries are enforced by linting rather than by the network. A lazy import
inside a function body could still cross a layer, and only CI would catch it —
which is precisely why `lint-imports` is a required gate rather than a habit.

We also accept a single deployment unit: one bad migration takes everything
down together.

## What changes at 10x usage?

Nothing structural. Add a Railway replica. PostgreSQL on Neon is nowhere near
its limits at the volume a lead form produces.

## What changes at 100x usage?

Still one codebase, but the Phase 5 outbox dispatcher moves into its own Railway
process reading the same database. Because it already talks to the rest of the
system through ports, that is a deployment change and not a rewrite.

That is the real argument for drawing the boundaries now: they are what make the
split cheap *if* it is ever needed, and cost almost nothing if it is not.
