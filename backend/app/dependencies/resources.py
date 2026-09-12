"""Process-wide resources, created once in the application lifespan.

Lives in its own module rather than in `main.py` so that both `main` (which
builds it) and `dependencies/services.py` (which reads it) can import the type
without a circular import.

Typing this properly matters more than it looks. `request.app.state` is `Any`,
so without a declared type every provider that reaches through it silently
returns `Any` — and `Any` propagating through the composition root is exactly
where a port/adapter mismatch would stop being caught by mypy.
"""

from dataclasses import dataclass

import httpx
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.application.ports.crm_client import CrmClient
from app.application.ports.sales_brief_generator import SalesBriefGenerator


@dataclass
class AppResources:
    """Everything shared across requests for the life of the process.

    Creating these per request would exhaust the database connection limit and
    throw away every TLS handshake.

    `engine` and `session_factory` are None when DATABASE_URL is unset. That is
    a supported mode: the API still starts, still serves health checks and still
    documents itself, and every database-backed feature reports itself as
    unavailable rather than crashing the process.
    """

    engine: AsyncEngine | None
    session_factory: async_sessionmaker[AsyncSession] | None
    http_client: httpx.AsyncClient
    crm_client: CrmClient
    brief_generator: SalesBriefGenerator
    #: Typed loosely to avoid importing the worker here. main.py owns its
    #: lifecycle and nothing else needs to touch it.
    outbox_worker: object | None = None
