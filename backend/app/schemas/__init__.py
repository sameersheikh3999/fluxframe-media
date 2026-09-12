"""Pydantic schemas — the wire format, and nothing else.

A schema describes what JSON looks like going in or coming out. It is the
public contract of the HTTP API, it is what FastAPI turns into the OpenAPI
document at /openapi.json, and from Phase 2 it is what generates the frontend's
TypeScript types.

It is NOT the domain entity and NOT the database row. Those are separate objects
that happen to look similar today. They diverge the first time the API needs a
field the business rules do not care about (a pagination cursor), or the
database grows a column the API must never expose (`hubspot_sync_error`).

Schemas may import app.domain (so enum values have one source of truth) and
nothing else from this application — see .importlinter, contract 6.
"""
