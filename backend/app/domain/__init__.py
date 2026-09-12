"""Domain layer — Fluxframe's business rules.

ALLOWED imports:  the Python standard library, and other app.domain modules.

FORBIDDEN imports: FastAPI, Pydantic, SQLAlchemy, httpx, structlog, settings,
and every other layer of this application.

The test for whether code belongs here: could it run inside a unit test with
no network, no database and no configuration? If not, it belongs in
app.application (coordination) or app.infrastructure (I/O).

Phase 0 contains only the shared error base. The leads domain — entities,
enums, scoring, lifecycle, events — arrives in Phase 1 and Phase 2.
"""
