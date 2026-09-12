"""Driving adapters that are not HTTP.

`app.api` is the inbound adapter for web requests. This package is the inbound
adapter for *time*: a background loop that wakes up and drives use cases.

Both are "driving" adapters — they call into the application. That is why they
sit at the same layer, and why neither belongs in `app.infrastructure`, which
holds "driven" adapters: things the application calls OUT to (a database, a CRM,
a model provider).

Getting this distinction right is what keeps the dependency arrows honest. An
outbox worker filed under infrastructure would mean infrastructure importing a
service, which is the inversion the architecture exists to prevent — and
`lint-imports` caught exactly that when these files were first written in the
wrong place.
"""
