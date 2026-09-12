"""Application layer — Fluxframe's use cases.

ALLOWED imports:  the standard library, app.domain, and other app.application
                  modules.

FORBIDDEN imports: app.infrastructure, app.api, app.schemas, app.config,
                   FastAPI, Pydantic, SQLAlchemy, httpx.

A service here reads like a transaction script: it coordinates domain objects
and ports, and it owns the transaction boundary. It never constructs a database
session or an HTTP client — it is handed something that satisfies a Protocol
in app.application.ports, and it does not care what.

Sub-packages:
    dto/      plain dataclasses crossing the application boundary
    ports/    Protocols describing what the application needs from the outside
    services/ the use cases themselves
"""
