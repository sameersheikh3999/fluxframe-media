"""Application composition.

This module is the assembly point and nothing else: it reads settings, sets up
logging, creates the resources that must outlive a request, mounts middleware
and routers, and registers error handlers. It holds no business logic.

`create_app()` is a factory rather than a module-level `app = FastAPI()` because
a factory can be called more than once with different settings — which is
exactly what the test suite wants.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.v1.router import api_v1_router
from app.application.ports.crm_client import CrmClient
from app.application.services.crm_sync_service import CrmSyncService
from app.application.services.outbox_dispatcher import OutboxDispatcher
from app.config.settings import Settings, get_settings
from app.dependencies.resources import AppResources
from app.dependencies.services import (
    build_brief_generator,
    build_crm_client,
    get_clock,
)
from app.infrastructure.database.engine import (
    create_engine_from_url,
    create_session_factory,
    normalise_database_url,
)
from app.infrastructure.database.outbox_store import SqlAlchemyOutboxStore
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.observability.logging import configure_logging, get_logger
from app.workers.handlers import build_handlers
from app.workers.outbox_worker import OutboxWorker

_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown.

    The application starts successfully even with no DATABASE_URL, no HubSpot
    token and no AI key. Each missing credential disables its feature and is
    reported honestly by /api/v1/health/ready. That is what makes a first
    Railway deploy possible before any integration is wired up — and it means a
    misconfigured integration degrades one feature rather than taking the whole
    site down.
    """
    settings: Settings = app.state.settings

    # One HTTP client for every outbound call (HubSpot, Anthropic), so
    # connections and TLS sessions are pooled across requests.
    http_client = httpx.AsyncClient(
        timeout=httpx.Timeout(
            max(settings.hubspot_timeout_seconds, settings.ai_timeout_seconds),
            connect=10.0,
        ),
        limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
    )

    engine: AsyncEngine | None = None
    session_factory: async_sessionmaker[AsyncSession] | None = None
    if settings.has_database:
        engine = create_engine_from_url(
            normalise_database_url(settings.database_url),
            echo=settings.database_echo,
            pool_size=settings.database_pool_size,
            max_overflow=settings.database_max_overflow,
        )
        session_factory = create_session_factory(engine)
        await _ensure_sqlite_schema(engine)
    else:
        _logger.warning(
            "database_not_configured",
            detail="DATABASE_URL is empty; lead capture and the dashboard are disabled.",
        )

    crm_client = build_crm_client(settings, http_client)
    brief_generator = build_brief_generator(settings, http_client)

    worker: OutboxWorker | None = None
    if session_factory is not None and settings.outbox_dispatcher_enabled:
        worker = _build_outbox_worker(settings, session_factory, crm_client)
        worker.start()

    app.state.resources = AppResources(
        engine=engine,
        session_factory=session_factory,
        http_client=http_client,
        crm_client=crm_client,
        brief_generator=brief_generator,
        outbox_worker=worker,
    )

    _logger.info(
        "application_startup",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
        database=settings.has_database,
        crm=settings.has_crm,
        ai=settings.has_ai,
        outbox_worker=worker is not None,
    )

    try:
        yield
    finally:
        if worker is not None:
            await worker.stop()
        await http_client.aclose()
        if engine is not None:
            await engine.dispose()
        _logger.info("application_shutdown", service=settings.app_name)


async def _ensure_sqlite_schema(engine: AsyncEngine) -> None:
    """Create the schema automatically — but ONLY on SQLite.

    This exists so someone can clone the repository and run the backend with no
    database server, no Docker and no credentials: point DATABASE_URL at a
    SQLite file and the tables appear.

    It is guarded on the dialect on purpose. PostgreSQL — every real deployment —
    must go through Alembic, because migrations are how a schema change is
    reviewed, versioned and rolled back. `create_all` silently does nothing to
    an existing table whose columns have drifted, which is exactly the failure
    you do not want in production.
    """
    if engine.dialect.name != "sqlite":
        return

    # Imported here rather than at module scope: importing the models registers
    # them on Base.metadata, and that side effect belongs next to the one place
    # that depends on it.
    from app.infrastructure.database import models  # noqa: F401
    from app.infrastructure.database.base import Base

    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    _logger.info(
        "sqlite_schema_ensured",
        detail="Development mode. PostgreSQL deployments use Alembic migrations.",
    )


def _build_outbox_worker(
    settings: Settings,
    session_factory: async_sessionmaker[AsyncSession],
    crm_client: CrmClient,
) -> OutboxWorker:
    """Assemble the background dispatcher.

    Built here rather than through `Depends` because it has no request to hang
    off — it is driven by elapsed time, not by HTTP. It gets its own UnitOfWork,
    which is correct: its transactions are independent of any request's.
    """
    crm_sync = CrmSyncService(
        uow=SqlAlchemyUnitOfWork(session_factory),
        crm_client=crm_client,
        clock=get_clock(),
        sync_demo_leads=settings.hubspot_sync_demo_leads,
    )
    dispatcher = OutboxDispatcher(
        store=SqlAlchemyOutboxStore(session_factory),
        handlers=build_handlers(crm_sync),
        clock=get_clock(),
        batch_size=settings.outbox_batch_size,
        max_attempts=settings.outbox_max_attempts,
        stalled_after_seconds=settings.outbox_stalled_after_seconds,
    )
    return OutboxWorker(
        dispatcher=dispatcher,
        poll_interval_seconds=settings.outbox_poll_interval_seconds,
    )


def create_app(settings: Settings | None = None) -> FastAPI:
    """Build the ASGI application."""
    settings = settings or get_settings()
    configure_logging(level=settings.log_level, json_output=settings.log_as_json)

    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        summary="Backend for Fluxframe Media — lead capture, scoring and CRM sync.",
        description=(
            "A modular monolith following a ports-and-adapters layering.\n\n"
            "Public endpoints are CORS-allowlisted for the marketing site. "
            "Dashboard, demo and admin endpoints require the internal shared "
            "secret and are called only from the Next.js server."
        ),
        docs_url="/docs",
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.state.settings = settings

    # Order matters: middleware added last runs first. RequestContextMiddleware
    # is added after CORS so that it wraps the CORS handling too, which means
    # even a rejected preflight gets a request id and a log line.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_origin_regex=settings.frontend_origin_regex,
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=[
            "Content-Type",
            "Authorization",
            "X-Request-ID",
            "Idempotency-Key",
            "X-Internal-Secret",
        ],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    @app.get("/health", tags=["system"], summary="Platform health check")
    def platform_health() -> dict[str, str]:
        """The bare health check most platforms probe by default.

        Unauthenticated, dependency-free and always cheap. Railway's health
        check points here: it answers "is this process up", which is the only
        question a restart policy should act on.
        """
        return {"status": "ok"}

    @app.get("/", include_in_schema=False)
    def root() -> dict[str, str]:
        """A friendly landing response for anyone who opens the API host."""
        return {
            "service": settings.app_name,
            "version": settings.app_version,
            "docs": "/docs",
            "health": "/health",
        }

    return app


app = create_app()
