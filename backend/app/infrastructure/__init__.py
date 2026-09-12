"""Infrastructure layer — the adapters that actually talk to the outside world.

ALLOWED imports:  the standard library, third-party clients (SQLAlchemy, httpx,
                  ...), app.domain, app.application.ports, app.application.dto,
                  app.config, app.observability.

FORBIDDEN imports: app.api, app.schemas, app.application.services,
                   app.dependencies, app.main.

An adapter is passive. It implements a port and waits to be called. It never
reaches back up to invoke a use case — if you find yourself wanting to, the
thing you are building is an inbound adapter (like a router or a worker loop)
and belongs elsewhere.

Phase 0 contains a clock and a placeholder readiness probe. The database,
HubSpot and outbox adapters arrive in Phases 1, 3 and 5.
"""
