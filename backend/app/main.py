"""Application composition.

This module is the assembly point and nothing else: it reads settings, sets up
logging, mounts middleware and routers, and registers error handlers. It holds
no logic of its own.

``create_app()`` is a factory rather than a module-level ``app = FastAPI()``
because a factory can be called more than once with different settings — which
is exactly what a test suite wants.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.errors import register_exception_handlers
from app.api.middleware import RequestContextMiddleware
from app.api.v1.router import api_v1_router
from app.config.settings import Settings, get_settings
from app.observability.logging import configure_logging, get_logger

_logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Startup and shutdown.

    Phase 0 only logs. This is where later phases acquire and release the
    resources that must outlive a single request:

        Phase 1  the SQLAlchemy async engine and its connection pool
        Phase 3  a shared httpx.AsyncClient for HubSpot
        Phase 5  the outbox dispatcher background task

    Creating those per request would exhaust the database's connection limit
    and throw away every TLS handshake, so they belong here.
    """
    settings: Settings = app.state.settings
    _logger.info(
        "application_startup",
        service=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )
    yield
    _logger.info("application_shutdown", service=settings.app_name)


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
            "Phase 0 exposes health endpoints only; business functionality "
            "arrives from Phase 1 onward."
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
        allow_headers=["Content-Type", "Authorization", "X-Request-ID", "Idempotency-Key"],
        expose_headers=["X-Request-ID"],
        max_age=600,
    )
    app.add_middleware(RequestContextMiddleware)

    register_exception_handlers(app)
    app.include_router(api_v1_router, prefix=settings.api_v1_prefix)

    return app


app = create_app()
