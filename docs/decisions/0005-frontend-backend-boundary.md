# 0005 — Public form calls FastAPI directly; internal pages go through the Next.js server

**Status:** Accepted · 2026-09-12
**Implemented:** Phase 1 (public path) and Phase 2 (internal path)

## Context

The frontend needs to reach the backend in two quite different situations:

1. A visitor submits the lead form. No secret is involved.
2. An operator opens `/dashboard/leads` or `/demo`. These must be protected by a
   shared secret that must never reach a browser.

Next.js can do either: the browser can call FastAPI directly, or a Server
Component / Route Handler can call it server-side.

## Decision

**Both, split by whether a secret is involved.**

| Path | Who calls FastAPI | Why |
|---|---|---|
| `/book-call` form | the browser, directly | no secret; proves the API is a real public API |
| `/dashboard/leads` | the Vercel server (Server Component) | `INTERNAL_API_SECRET` stays server-side |
| `/demo` | the Vercel server (Route Handler) | same |

The public path uses CORS with an explicit origin allowlist. The internal path
needs no CORS at all, because it is server-to-server.

**The hard rule:** a Route Handler used this way is transport-only. It attaches
a header and forwards. If one ever exceeds about thirty lines, business logic
has started migrating into Next.js and must be moved back.

## Why not pick one uniformly?

**Everything direct from the browser.** Any admin secret would have to be a
`NEXT_PUBLIC_*` variable, which means it is compiled into the JavaScript bundle
and readable by anyone with devtools. Not acceptable.

**Everything through a Next.js BFF.** Uniform, and CORS disappears entirely. But
it puts an always-on proxy in front of the public form — an extra hop and an
extra Vercel invocation on the one request that matters most — and, more
importantly for this project, a proxy layer is exactly where "just a little
transform" logic starts to accumulate. The stated goal is that Next.js contains
no business logic. Removing the temptation is cheaper than resisting it.

## What tradeoff are we accepting?

Two client modules instead of one (`lib/api-client.ts` for the browser,
`lib/api-server.ts` for the server), and CORS configuration that has to be
correct in production.

On CORS specifically: Vercel gives every preview deployment a unique hostname,
so previews cannot be enumerated. Production will use an explicit origin list
plus `allow_origin_regex` for preview URLs. That regex permits any preview of
this Vercel project — acceptable, because only the project owner can create one,
and vastly better than `*`. `FRONTEND_ORIGINS` containing `*` in production
already refuses to boot (`app/config/settings.py`).

## What changes at 10x / 100x?

Nothing about the boundary. At high volume the public endpoint gains rate
limiting (Phase 5) and possibly a CDN-level rule, neither of which changes who
calls whom.
