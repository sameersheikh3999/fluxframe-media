"""Providers that FastAPI's Depends() resolves — the composition root.

Each function answers one question: "when something asks for X, what does it
actually get?"

Note the pattern used throughout. A provider's return type is the PORT while the
value it constructs is the ADAPTER:

    def get_clock() -> Clock:        # the port
        return SystemClock()         # the adapter

mypy checks Protocol conformance at exactly these lines and nowhere else. If
someone changes `SystemClock.now()` to return a string, the error surfaces here,
in the wiring, rather than at runtime in production.

Long-lived resources (the database engine, the shared HTTP client) are created
once in the application lifespan and read off `request.app.state`. Creating them
per request would exhaust the database connection limit and throw away every TLS
handshake.
"""

from functools import lru_cache
from typing import Annotated

import httpx
from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.ports.ai_run_recorder import AiRunRecorder
from app.application.ports.clock import Clock
from app.application.ports.crm_client import CrmClient
from app.application.ports.outbox_store import OutboxStore
from app.application.ports.read_models import LeadReadModel, OutboxReadModel
from app.application.ports.readiness_probe import ReadinessProbe
from app.application.ports.sales_brief_generator import SalesBriefGenerator
from app.application.ports.unit_of_work import UnitOfWork
from app.application.services.crm_sync_service import CrmSyncService
from app.application.services.demo_lead_service import DemoLeadService
from app.application.services.lead_query_service import LeadQueryService
from app.application.services.lead_service import LeadService
from app.application.services.outbox_dispatcher import OutboxDispatcher
from app.application.services.sales_brief_service import SalesBriefService
from app.application.services.system_service import SystemService
from app.config.settings import Settings
from app.dependencies.resources import AppResources
from app.infrastructure.ai.anthropic_client import (
    AnthropicSalesBriefGenerator,
    NullSalesBriefGenerator,
)
from app.infrastructure.clock import SystemClock
from app.infrastructure.database.ai_runs import SqlAlchemyAiRunRecorder
from app.infrastructure.database.outbox_store import SqlAlchemyOutboxStore
from app.infrastructure.database.read_models import (
    SqlAlchemyLeadReadModel,
    SqlAlchemyOutboxReadModel,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.infrastructure.hubspot.client import HubSpotClient, NullCrmClient
from app.infrastructure.readiness.database_probe import (
    AiConfigurationProbe,
    CrmConfigurationProbe,
    DatabaseReadinessProbe,
)
from app.infrastructure.readiness.not_configured_probe import NotConfiguredProbe
from app.workers.handlers import build_handlers


def get_app_settings(request: Request) -> Settings:
    """The settings THIS application was built with.

    Deliberately reads `app.state.settings` rather than calling the module-level
    `get_settings()` singleton. `create_app(settings)` accepts an explicit
    Settings object, and if dependencies quietly went to the singleton instead,
    that argument would be a lie — the app would be configured one way and its
    endpoints would behave another.

    That is not hypothetical: it let the internal-access guard read an empty
    secret from the ambient environment while the application had been built
    with one, so the dashboard endpoints answered without authentication. The
    test suite caught it; the fix is to make the composition point authoritative.
    """
    settings: Settings = request.app.state.settings
    return settings


SettingsDep = Annotated[Settings, Depends(get_app_settings)]


@lru_cache
def get_clock() -> Clock:
    """The application's source of time. Stateless, so one instance is plenty."""
    return SystemClock()


ClockDep = Annotated[Clock, Depends(get_clock)]


# --- resources created once in the lifespan ---------------------------------
#
# These read off app.state rather than constructing anything. `AppResources` in
# app/main.py owns their lifecycle.


def get_resources(request: Request) -> AppResources:
    """The process-wide resources built in the lifespan.

    Typed explicitly because `request.app.state` is `Any`, and an `Any` leaking
    in here would silently switch off type checking for every provider below —
    including the port/adapter conformance checks this file exists to perform.
    """
    resources: AppResources = request.app.state.resources
    return resources


def _require_session_factory(request: Request) -> async_sessionmaker[AsyncSession]:
    """The session factory, or a clear 503 when no database is configured.

    Running with no DATABASE_URL is a supported mode: the marketing site, the
    health checks and the API docs all work. What must not happen is an
    AttributeError surfacing from deep inside a repository, so this turns the
    missing dependency into an honest "this feature needs a database" response.
    """
    factory = get_resources(request).session_factory
    if factory is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=(
                "No database is configured. Set DATABASE_URL to enable lead "
                "capture and the dashboard."
            ),
        )
    return factory


def get_unit_of_work(request: Request) -> UnitOfWork:
    """A fresh Unit of Work per request.

    New each time because an `AsyncSession` is not safe to share across
    concurrent tasks. The session factory behind it IS shared, so the connection
    pool is reused.
    """
    return SqlAlchemyUnitOfWork(_require_session_factory(request))


UnitOfWorkDep = Annotated[UnitOfWork, Depends(get_unit_of_work)]


def get_crm_client(request: Request) -> CrmClient:
    return get_resources(request).crm_client


def get_sales_brief_generator(request: Request) -> SalesBriefGenerator:
    return get_resources(request).brief_generator


def get_outbox_store(request: Request) -> OutboxStore:
    return SqlAlchemyOutboxStore(_require_session_factory(request))


def get_lead_read_model(request: Request) -> LeadReadModel:
    return SqlAlchemyLeadReadModel(_require_session_factory(request))


def get_outbox_read_model(request: Request) -> OutboxReadModel:
    return SqlAlchemyOutboxReadModel(_require_session_factory(request))


def get_ai_run_recorder(request: Request) -> AiRunRecorder:
    return SqlAlchemyAiRunRecorder(_require_session_factory(request))


# --- services ----------------------------------------------------------------


def get_lead_service(uow: UnitOfWorkDep, clock: ClockDep) -> LeadService:
    return LeadService(uow=uow, clock=clock)


LeadServiceDep = Annotated[LeadService, Depends(get_lead_service)]


def get_lead_query_service(
    leads: Annotated[LeadReadModel, Depends(get_lead_read_model)],
    outbox: Annotated[OutboxReadModel, Depends(get_outbox_read_model)],
) -> LeadQueryService:
    return LeadQueryService(leads=leads, outbox=outbox)


LeadQueryServiceDep = Annotated[LeadQueryService, Depends(get_lead_query_service)]


def get_demo_lead_service(settings: SettingsDep, lead_service: LeadServiceDep) -> DemoLeadService:
    return DemoLeadService(
        lead_service=lead_service,
        enabled=settings.enable_demo_generator,
        max_batch_size=settings.demo_max_batch_size,
    )


DemoLeadServiceDep = Annotated[DemoLeadService, Depends(get_demo_lead_service)]


def get_crm_sync_service(
    settings: SettingsDep,
    uow: UnitOfWorkDep,
    clock: ClockDep,
    crm: Annotated[CrmClient, Depends(get_crm_client)],
) -> CrmSyncService:
    return CrmSyncService(
        uow=uow,
        crm_client=crm,
        clock=clock,
        sync_demo_leads=settings.hubspot_sync_demo_leads,
    )


def get_sales_brief_service(
    uow: UnitOfWorkDep,
    clock: ClockDep,
    generator: Annotated[SalesBriefGenerator, Depends(get_sales_brief_generator)],
    recorder: Annotated[AiRunRecorder, Depends(get_ai_run_recorder)],
) -> SalesBriefService:
    return SalesBriefService(uow=uow, generator=generator, recorder=recorder, clock=clock)


SalesBriefServiceDep = Annotated[SalesBriefService, Depends(get_sales_brief_service)]


def get_outbox_dispatcher(
    settings: SettingsDep,
    clock: ClockDep,
    store: Annotated[OutboxStore, Depends(get_outbox_store)],
    crm_sync: Annotated[CrmSyncService, Depends(get_crm_sync_service)],
) -> OutboxDispatcher:
    return OutboxDispatcher(
        store=store,
        handlers=build_handlers(crm_sync),
        clock=clock,
        batch_size=settings.outbox_batch_size,
        max_attempts=settings.outbox_max_attempts,
        stalled_after_seconds=settings.outbox_stalled_after_seconds,
    )


OutboxDispatcherDep = Annotated[OutboxDispatcher, Depends(get_outbox_dispatcher)]


# --- system ------------------------------------------------------------------


def get_readiness_probes(request: Request, settings: SettingsDep) -> list[ReadinessProbe]:
    """Every external dependency whose availability we report on.

    The database probe is real when a database is configured, and honestly
    reports "not configured" when it is not — which is a supported mode, and
    exactly what a first Railway deploy looks like before you add Postgres.
    """
    resources = get_resources(request)
    probes: list[ReadinessProbe] = []

    if resources.engine is not None:
        probes.append(DatabaseReadinessProbe(resources.engine))
    else:
        probes.append(
            NotConfiguredProbe(
                name="database",
                detail="DATABASE_URL is not set; lead capture is unavailable.",
            )
        )

    probes.append(CrmConfigurationProbe(configured=settings.has_crm))
    probes.append(AiConfigurationProbe(configured=settings.has_ai))
    return probes


def get_system_service(
    settings: SettingsDep,
    clock: ClockDep,
    probes: Annotated[list[ReadinessProbe], Depends(get_readiness_probes)],
) -> SystemService:
    """Assemble SystemService from its ports and the deployment settings.

    The service receives three plain strings rather than the Settings object,
    which keeps app.application free of any knowledge that a settings system
    exists at all.
    """
    return SystemService(
        clock=clock,
        probes=probes,
        service_name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment.value,
    )


SystemServiceDep = Annotated[SystemService, Depends(get_system_service)]


def build_crm_client(settings: Settings, http_client: httpx.AsyncClient) -> CrmClient:
    """Choose the CRM adapter for this deployment.

    Called from the lifespan rather than per request, because the HubSpot client
    wraps a shared httpx.AsyncClient whose connection pool should outlive a
    single request.

    A deployment with no HUBSPOT_ACCESS_TOKEN gets NullCrmClient, which reports
    `is_configured = False`. That is a supported production mode, not a stub:
    CrmSyncService reads that property and marks syncs `skipped`.
    """
    if not settings.has_crm:
        return NullCrmClient()
    return HubSpotClient(
        access_token=settings.hubspot_access_token,
        http_client=http_client,
        base_url=settings.hubspot_base_url,
    )


def build_brief_generator(
    settings: Settings, http_client: httpx.AsyncClient
) -> SalesBriefGenerator:
    """Choose the AI adapter for this deployment.

    No ANTHROPIC_API_KEY means NullSalesBriefGenerator, which refuses clearly
    rather than fabricating a brief. An invented brief would be worse than none,
    because a salesperson would act on it.
    """
    if not settings.has_ai:
        return NullSalesBriefGenerator()
    return AnthropicSalesBriefGenerator(
        api_key=settings.anthropic_api_key,
        http_client=http_client,
        model=settings.ai_model,
        max_tokens=settings.ai_max_tokens,
    )
