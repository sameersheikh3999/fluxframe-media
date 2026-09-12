"""End-to-end integration tests against a real database.

Everything above this file used fakes. These use the actual SQLAlchemy
repositories, the actual Unit of Work and a real (SQLite) database, because
there is a category of bug that only appears when a real transaction is
involved: a repository that forgets to stage a row, a mapper that loses a field,
a unique constraint that does not fire.

Most importantly, this is where the outbox invariant is proven for real rather
than against an in-memory imitation of a transaction.
"""

from uuid import uuid4

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.application.dto.leads import AttributionCommand, CaptureLeadCommand
from app.application.errors import LeadNotFoundError
from app.application.services.crm_sync_service import CrmSyncService
from app.application.services.lead_query_service import LeadQueryService
from app.application.services.lead_service import LeadService
from app.application.services.outbox_dispatcher import OutboxDispatcher
from app.domain.leads.enums import (
    ContentVolume,
    CrmSyncStatus,
    Industry,
    LeadSource,
    LeadStatus,
    MarketingBudget,
    MonthlyRevenue,
    PrimaryGoal,
    StartTimeline,
)
from app.infrastructure.database.models import LeadModel, OutboxEventModel
from app.infrastructure.database.outbox_store import SqlAlchemyOutboxStore
from app.infrastructure.database.read_models import (
    SqlAlchemyLeadReadModel,
    SqlAlchemyOutboxReadModel,
)
from app.infrastructure.database.unit_of_work import SqlAlchemyUnitOfWork
from app.workers.handlers import build_handlers
from tests.fakes import PERMANENT, TRANSIENT, FakeCrmClient, FrozenClock

pytestmark = pytest.mark.integration

Factory = async_sessionmaker[AsyncSession]


def command(key: str = "int-key-1", **overrides: object) -> CaptureLeadCommand:
    defaults: dict[str, object] = {
        "idempotency_key": key,
        "first_name": "Sarah",
        "last_name": "Morgan",
        "email": "sarah@example.com",
        "company_name": "Bloom Skin Clinic",
        "website": "https://bloom.example.com",
        "phone": "+44 7700 900123",
        "industry": Industry.BEAUTY,
        "monthly_revenue": MonthlyRevenue.FROM_100K_TO_500K,
        "monthly_marketing_budget": MarketingBudget.OVER_10K,
        "content_volume": ContentVolume.THIRTY_PLUS,
        "primary_goal": PrimaryGoal.LEAD_GENERATION,
        "start_timeline": StartTimeline.IMMEDIATELY,
        "message": "New clinic opening in six weeks.",
        "source": LeadSource.WEBSITE,
        "attribution": AttributionCommand(utm_source="google", utm_medium="cpc"),
    }
    defaults.update(overrides)
    return CaptureLeadCommand(**defaults)  # type: ignore[arg-type]


@pytest.fixture
def lead_service(session_factory: Factory) -> LeadService:
    return LeadService(uow=SqlAlchemyUnitOfWork(session_factory), clock=FrozenClock())


# --- persistence ------------------------------------------------------------


async def test_a_captured_lead_is_really_in_the_database(
    lead_service: LeadService, session_factory: Factory
) -> None:
    result = await lead_service.capture_lead(command())

    async with session_factory() as session:
        row = await session.get(LeadModel, result.id)

    assert row is not None
    assert row.email == "sarah@example.com"
    assert row.lead_score == 100
    assert row.lead_temperature == "hot"
    assert row.status == "new"
    assert row.hubspot_sync_status == "pending"


async def test_the_score_breakdown_survives_a_round_trip(
    lead_service: LeadService, session_factory: Factory
) -> None:
    """It is stored as JSON(B), and it is the answer to "why 87?"."""
    result = await lead_service.capture_lead(command())

    async with session_factory() as session:
        row = await session.get(LeadModel, result.id)

    assert row is not None
    breakdown = row.score_breakdown
    assert breakdown is not None
    assert breakdown["final_score"] == 100
    assert len(breakdown["components"]) == 5


async def test_attribution_is_stored(lead_service: LeadService, session_factory: Factory) -> None:
    result = await lead_service.capture_lead(command())
    async with session_factory() as session:
        row = await session.get(LeadModel, result.id)
    assert row is not None
    assert row.utm_source == "google"
    assert row.utm_medium == "cpc"


# --- THE outbox invariant ---------------------------------------------------


async def test_the_lead_and_its_outbox_event_are_committed_together(
    lead_service: LeadService, session_factory: Factory
) -> None:
    """Against a real transaction, not a fake one.

    If these two ever stopped sharing a transaction, a crash in between would
    lose the CRM sync silently and permanently.
    """
    result = await lead_service.capture_lead(command())

    async with session_factory() as session:
        lead = await session.get(LeadModel, result.id)
        events = (
            (
                await session.execute(
                    select(OutboxEventModel).where(OutboxEventModel.aggregate_id == result.id)
                )
            )
            .scalars()
            .all()
        )

    assert lead is not None
    assert {event.event_type for event in events} == {"LeadCaptured", "LeadMarkedHot"}
    assert all(event.status == "pending" for event in events)


async def test_a_rejected_lead_leaves_no_trace(
    lead_service: LeadService, session_factory: Factory
) -> None:
    """Rollback works for real: no lead, no activity, no event."""
    with pytest.raises(Exception):  # noqa: B017
        await lead_service.capture_lead(command(first_name="  "))

    async with session_factory() as session:
        leads = (await session.execute(select(LeadModel))).scalars().all()
        events = (await session.execute(select(OutboxEventModel))).scalars().all()

    assert leads == []
    assert events == []


async def test_the_correlation_id_reaches_the_outbox_row(
    lead_service: LeadService, session_factory: Factory
) -> None:
    result = await lead_service.capture_lead(command(), correlation_id="req-xyz")

    async with session_factory() as session:
        event = (
            (
                await session.execute(
                    select(OutboxEventModel).where(OutboxEventModel.aggregate_id == result.id)
                )
            )
            .scalars()
            .first()
        )

    assert event is not None
    assert event.correlation_id == "req-xyz"


# --- idempotency against a real unique constraint ---------------------------


async def test_a_duplicate_key_creates_exactly_one_row(
    lead_service: LeadService, session_factory: Factory
) -> None:
    first = await lead_service.capture_lead(command(key="dup"))
    second = await lead_service.capture_lead(command(key="dup"))

    assert first.id == second.id
    assert second.was_duplicate is True

    async with session_factory() as session:
        leads = (await session.execute(select(LeadModel))).scalars().all()
    assert len(leads) == 1


async def test_the_same_email_twice_with_different_keys_is_two_leads(
    lead_service: LeadService, session_factory: Factory
) -> None:
    """Email is deliberately not unique: a genuine re-enquiry months later is a
    new lead, not a constraint violation."""
    await lead_service.capture_lead(command(key="a"))
    await lead_service.capture_lead(command(key="b"))

    async with session_factory() as session:
        leads = (await session.execute(select(LeadModel))).scalars().all()
    assert len(leads) == 2


# --- lifecycle --------------------------------------------------------------


async def test_a_status_change_persists_and_is_logged(
    lead_service: LeadService, session_factory: Factory
) -> None:
    result = await lead_service.capture_lead(command())
    await lead_service.transition_status(result.id, LeadStatus.QUALIFIED, actor="user:sam")

    read_model = SqlAlchemyLeadReadModel(session_factory)
    detail = await read_model.get_detail(result.id)

    assert detail is not None
    assert detail.status == "qualified"
    assert any(a.activity_type == "status_changed" for a in detail.activities)
    assert detail.allowed_next_statuses  # the domain decides the next buttons


async def test_a_missing_lead_raises_rather_than_returning_none(
    session_factory: Factory,
) -> None:
    query = LeadQueryService(
        leads=SqlAlchemyLeadReadModel(session_factory),
        outbox=SqlAlchemyOutboxReadModel(session_factory),
    )
    with pytest.raises(LeadNotFoundError):
        await query.get_lead(uuid4())


# --- dispatch through to the CRM --------------------------------------------


def make_dispatcher(
    session_factory: Factory, crm: FakeCrmClient, *, max_attempts: int = 6
) -> OutboxDispatcher:
    sync = CrmSyncService(
        uow=SqlAlchemyUnitOfWork(session_factory),
        crm_client=crm,
        clock=FrozenClock(),
        sync_demo_leads=False,
    )
    return OutboxDispatcher(
        store=SqlAlchemyOutboxStore(session_factory),
        handlers=build_handlers(sync),
        clock=FrozenClock(),
        max_attempts=max_attempts,
    )


async def test_dispatching_syncs_the_lead_and_records_the_contact_id(
    lead_service: LeadService, session_factory: Factory
) -> None:
    """The full path: capture -> outbox -> dispatcher -> CRM -> lead updated."""
    result = await lead_service.capture_lead(command())
    crm = FakeCrmClient()

    report = await make_dispatcher(session_factory, crm).dispatch_once()

    assert report.processed >= 1
    assert len(crm.calls) == 1
    assert crm.calls[0].email == "sarah@example.com"
    assert crm.calls[0].lead_score == 100

    async with session_factory() as session:
        row = await session.get(LeadModel, result.id)
    assert row is not None
    assert row.hubspot_sync_status == CrmSyncStatus.SYNCED.value
    assert row.hubspot_contact_id == "hs-1"


async def test_dispatching_twice_does_not_call_the_crm_twice(
    lead_service: LeadService, session_factory: Factory
) -> None:
    """At-least-once delivery plus an idempotent consumer.

    The second pass finds `hubspot_contact_id` already set and short-circuits,
    which is the defence against a replayed or redelivered event creating a
    duplicate contact.
    """
    await lead_service.capture_lead(command())
    crm = FakeCrmClient()
    dispatcher = make_dispatcher(session_factory, crm)

    await dispatcher.dispatch_once()
    # Replay the same event deliberately.
    async with session_factory() as session:
        events = (
            (
                await session.execute(
                    select(OutboxEventModel).where(OutboxEventModel.event_type == "LeadCaptured")
                )
            )
            .scalars()
            .all()
        )
    for event in events:
        await dispatcher.replay(event.id)
    await dispatcher.dispatch_once()

    assert len(crm.calls) == 1


async def test_a_transient_crm_failure_leaves_the_event_retryable(
    lead_service: LeadService, session_factory: Factory
) -> None:
    result = await lead_service.capture_lead(command())
    crm = FakeCrmClient(fail_with=TRANSIENT)

    report = await make_dispatcher(session_factory, crm).dispatch_once()

    assert report.failed >= 1
    assert report.dead_lettered == 0

    async with session_factory() as session:
        row = await session.get(LeadModel, result.id)
        events = (
            (
                await session.execute(
                    select(OutboxEventModel).where(OutboxEventModel.event_type == "LeadCaptured")
                )
            )
            .scalars()
            .all()
        )

    assert row is not None
    assert row.hubspot_sync_status == CrmSyncStatus.FAILED.value
    assert events[0].status == "failed"  # queued for another attempt


async def test_a_permanent_crm_failure_dead_letters(
    lead_service: LeadService, session_factory: Factory
) -> None:
    await lead_service.capture_lead(command())
    crm = FakeCrmClient(fail_with=PERMANENT)

    report = await make_dispatcher(session_factory, crm).dispatch_once()

    assert report.dead_lettered >= 1

    async with session_factory() as session:
        events = (
            (
                await session.execute(
                    select(OutboxEventModel).where(OutboxEventModel.event_type == "LeadCaptured")
                )
            )
            .scalars()
            .all()
        )
    assert events[0].status == "dead"


async def test_an_unconfigured_crm_marks_the_sync_skipped_not_failed(
    lead_service: LeadService, session_factory: Factory
) -> None:
    """Running with no HubSpot token is a supported mode, not a fault."""
    result = await lead_service.capture_lead(command())
    crm = FakeCrmClient(configured=False)

    await make_dispatcher(session_factory, crm).dispatch_once()

    async with session_factory() as session:
        row = await session.get(LeadModel, result.id)
    assert row is not None
    assert row.hubspot_sync_status == CrmSyncStatus.SKIPPED.value
    assert crm.calls == []


async def test_demo_leads_are_not_synced_to_the_crm_by_default(
    lead_service: LeadService, session_factory: Factory
) -> None:
    """Ten synthetic contacts per click would pollute a real HubSpot portal."""
    result = await lead_service.capture_lead(
        command(is_demo=True, source=LeadSource.DEMO_GENERATOR)
    )
    crm = FakeCrmClient()

    await make_dispatcher(session_factory, crm).dispatch_once()

    async with session_factory() as session:
        row = await session.get(LeadModel, result.id)
    assert row is not None
    assert row.hubspot_sync_status == CrmSyncStatus.SKIPPED.value
    assert crm.calls == []


# --- dashboard read model ---------------------------------------------------


async def test_the_dashboard_stats_count_correctly(
    lead_service: LeadService, session_factory: Factory
) -> None:
    await lead_service.capture_lead(command(key="hot-1"))
    await lead_service.capture_lead(
        command(
            key="cold-1",
            monthly_marketing_budget=MarketingBudget.UNDER_2K,
            content_volume=ContentVolume.FOUR,
            start_timeline=StartTimeline.RESEARCHING,
            primary_goal=PrimaryGoal.SOCIAL_GROWTH,
            industry=Industry.RESTAURANT,
        )
    )

    stats = await SqlAlchemyLeadReadModel(session_factory).stats()

    assert stats.total_leads == 2
    assert stats.hot_leads == 1
    assert stats.cold_leads == 1
    assert stats.crm_sync_pending == 2


async def test_filtering_and_pagination(
    lead_service: LeadService, session_factory: Factory
) -> None:
    for index in range(5):
        await lead_service.capture_lead(
            command(key=f"page-{index}", email=f"lead{index}@example.com")
        )

    from app.application.dto.leads import LeadFilters

    read_model = SqlAlchemyLeadReadModel(session_factory)
    page = await read_model.list_leads(LeadFilters(), limit=2, offset=0)

    assert page.total == 5
    assert len(page.items) == 2
    assert page.has_more is True

    hot_only = await read_model.list_leads(LeadFilters(temperature="hot"), limit=10, offset=0)
    assert hot_only.total == 5

    none_match = await read_model.list_leads(LeadFilters(temperature="cold"), limit=10, offset=0)
    assert none_match.total == 0


async def test_search_matches_company_and_email(
    lead_service: LeadService, session_factory: Factory
) -> None:
    await lead_service.capture_lead(command(key="s1", company_name="Northgate Dental"))
    await lead_service.capture_lead(
        command(key="s2", company_name="Iron Forge Gym", email="gym@example.com")
    )

    from app.application.dto.leads import LeadFilters

    read_model = SqlAlchemyLeadReadModel(session_factory)
    found = await read_model.list_leads(LeadFilters(search="northgate"), limit=10, offset=0)
    assert found.total == 1
    assert found.items[0].company_name == "Northgate Dental"
