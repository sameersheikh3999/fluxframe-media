"""API layer — the inbound HTTP adapter.

ALLOWED imports:  app.schemas, app.dependencies, app.application, app.domain,
                  app.observability, FastAPI.

FORBIDDEN imports: app.infrastructure (enforced by .importlinter, contract 4).

A router function does three things and no more:

    1. accept a validated Pydantic schema
    2. call one application service method
    3. map the returned DTO onto a Pydantic response schema

It contains no business rules, no SQL and no HTTP calls to third parties. The
test for whether this layer is honest: could you delete app/api/ and drive the
same use cases from a CLI in an afternoon? If not, logic has leaked into it.
"""
