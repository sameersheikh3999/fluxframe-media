"""Fluxframe Media backend — a modular monolith.

Layer map (see docs/architecture.md and ../.importlinter):

    app.main           composition of the ASGI application
    app.api            inbound HTTP adapter: translates requests into use cases
    app.schemas        Pydantic transport contracts (what JSON looks like)
    app.dependencies   composition root: binds ports to concrete adapters
    app.application    use cases (services), ports (Protocols), DTOs
    app.domain         business rules — pure Python, no framework, no I/O
    app.infrastructure outbound adapters that implement the ports
    app.config         settings, validated at startup
    app.observability  cross-cutting logging and request context
"""
